"""Outbound packet tracking service."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.models.outbound_packet_log import OutboundPacketLog

logger = logging.getLogger(__name__)


class OutboundPacketService:
    """Tracks outbound AMIE packet send/ack/retry state."""

    @staticmethod
    def _to_dict(value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if hasattr(value, "as_dict"):
            try:
                return value.as_dict()
            except Exception:  # noqa: BLE001
                return {"raw": repr(value)}
        return {"raw": repr(value)}

    @classmethod
    def start_or_resume(
        cls,
        db: Session,
        *,
        event_type: str,
        source_packet_rec_id: int | None = None,
        source_trans_rec_id: int | None = None,
        source_transaction_id: int | None = None,
        project_user_id: uuid.UUID | None = None,
        payload: dict[str, Any] | None = None,
        worker_name: str | None = None,
    ) -> OutboundPacketLog:
        """Create or return an existing active outbound send row."""
        existing = None
        if project_user_id is not None:
            existing = (
                db.query(OutboundPacketLog)
                .filter(
                    OutboundPacketLog.project_user_id == project_user_id,
                    OutboundPacketLog.event_type == event_type,
                    OutboundPacketLog.status.in_(
                        [
                            OutboundPacketLog.STATUS_PENDING,
                            OutboundPacketLog.STATUS_RETRYING,
                            OutboundPacketLog.STATUS_LOCKED,
                        ]
                    ),
                )
                .order_by(OutboundPacketLog.created_at.desc())
                .first()
            )
        if existing is not None:
            if payload:
                existing.payload = payload
            return existing

        row = OutboundPacketLog(
            worker_name=worker_name,
            event_type=event_type,
            status=OutboundPacketLog.STATUS_PENDING,
            ack_status=OutboundPacketLog.ACK_UNKNOWN,
            source_packet_rec_id=source_packet_rec_id,
            source_trans_rec_id=source_trans_rec_id,
            source_transaction_id=source_transaction_id,
            project_user_id=project_user_id,
            payload=payload or {},
            max_retries=settings.amie_packet_reprocess_max_retries,
        )
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def is_locked(row: OutboundPacketLog) -> bool:
        """Return whether retries are currently locked out."""
        return bool(row.locked_until and row.locked_until > datetime.now(UTC))

    @classmethod
    def mark_sent(
        cls,
        db: Session,
        row: OutboundPacketLog,
        *,
        send_result: Any = None,
    ) -> OutboundPacketLog:
        """Mark outbound send as successful."""
        now = datetime.now(UTC)
        result_dict = cls._to_dict(send_result)
        header = result_dict.get("header", {}) if isinstance(result_dict, dict) else {}
        row.status = OutboundPacketLog.STATUS_SENT
        row.ack_status = (
            OutboundPacketLog.ACK_PENDING
            if header.get("packet_rec_id") is not None
            else OutboundPacketLog.ACK_UNKNOWN
        )
        row.outbound_packet_rec_id = header.get("packet_rec_id")
        row.outbound_transaction_id = header.get("transaction_id")
        row.last_attempt_at = now
        row.sent_at = now
        row.last_error = None
        row.locked_until = None
        row.next_retry_at = None
        row.response_payload = result_dict or None
        db.flush()
        return row

    @classmethod
    def mark_failed(
        cls,
        db: Session,
        row: OutboundPacketLog,
        *,
        error_message: str,
    ) -> OutboundPacketLog:
        """Increment retry and set failed/retrying/locked status."""
        now = datetime.now(UTC)
        row.retry_count += 1
        row.last_attempt_at = now
        row.last_error = error_message

        if row.retry_count >= row.max_retries:
            row.status = OutboundPacketLog.STATUS_LOCKED
            row.locked_until = now + timedelta(
                minutes=settings.amie_packet_reprocess_lockout_minutes
            )
            row.next_retry_at = row.locked_until
        else:
            row.status = OutboundPacketLog.STATUS_RETRYING
            row.next_retry_at = now + timedelta(minutes=1)
            row.locked_until = None

        db.flush()
        return row

    @staticmethod
    def mark_acked(db: Session, row: OutboundPacketLog, *, acked: bool = True) -> None:
        """Set ack state for outbound packet."""
        row.ack_status = (
            OutboundPacketLog.ACK_ACKED if acked else OutboundPacketLog.ACK_NOT_ACKED
        )
        if acked:
            row.acked_at = datetime.now(UTC)
        db.flush()

    @staticmethod
    def safe_mark_failed(
        db: Session,
        *,
        row: OutboundPacketLog | None,
        event_type: str,
        error_message: str,
        project_user_id: uuid.UUID | None = None,
    ) -> None:
        """Fail-safe error persistence for outbound packet events."""
        try:
            if row is None:
                row = OutboundPacketLog(
                    event_type=event_type,
                    status=OutboundPacketLog.STATUS_FAILED,
                    ack_status=OutboundPacketLog.ACK_UNKNOWN,
                    retry_count=1,
                    max_retries=settings.amie_packet_reprocess_max_retries,
                    last_error=error_message,
                    project_user_id=project_user_id,
                    last_attempt_at=datetime.now(UTC),
                )
                db.add(row)
            else:
                OutboundPacketService.mark_failed(
                    db, row, error_message=error_message
                )
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.exception("Failed to persist outbound packet failure state")
