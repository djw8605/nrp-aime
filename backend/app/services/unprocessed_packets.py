"""Service methods for tracking packets that failed processing."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.amie_unprocessed_packet import AMIEUnprocessedPacket

logger = logging.getLogger(__name__)


class UnprocessedPacketService:
    """Persist and update unprocessed packet records."""

    @staticmethod
    def _json_default(value: Any) -> str:
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    @classmethod
    def _normalize_packet(cls, packet_payload: dict[str, Any]) -> dict[str, Any]:
        return json.loads(json.dumps(packet_payload, default=cls._json_default))

    @classmethod
    def _fingerprint(
        cls,
        packet_payload: dict[str, Any],
        failure_reason: str,
    ) -> str:
        header = packet_payload.get("header", {}) if isinstance(packet_payload, dict) else {}
        packet_rec_id = header.get("packet_rec_id")
        if packet_rec_id is not None:
            return f"{failure_reason}|packet_rec_id|{packet_rec_id}"
        normalized = cls._normalize_packet(packet_payload)
        serialized = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(f"{failure_reason}|{serialized}".encode("utf-8")).hexdigest()

    @staticmethod
    def _to_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def record_failure(
        cls,
        db: Session,
        *,
        packet_payload: dict[str, Any],
        failure_reason: str,
        error_message: str | None = None,
    ) -> AMIEUnprocessedPacket:
        """Record a failure (or bump attempt count if already known)."""
        fingerprint = cls._fingerprint(packet_payload, failure_reason)
        header = packet_payload.get("header", {}) if isinstance(packet_payload, dict) else {}
        now = datetime.now(UTC)

        existing = (
            db.query(AMIEUnprocessedPacket)
            .filter(AMIEUnprocessedPacket.packet_fingerprint == fingerprint)
            .first()
        )
        if existing is not None:
            existing.attempt_count += 1
            existing.last_seen_at = now
            existing.error_message = error_message or existing.error_message
            db.commit()
            return existing

        row = AMIEUnprocessedPacket(
            packet_fingerprint=fingerprint,
            packet_rec_id=cls._to_int(header.get("packet_rec_id")),
            trans_rec_id=cls._to_int(header.get("trans_rec_id")),
            transaction_id=cls._to_int(header.get("transaction_id")),
            packet_type=packet_payload.get("type"),
            failure_reason=failure_reason,
            error_message=error_message,
            raw_packet=cls._normalize_packet(packet_payload),
            attempt_count=1,
            is_resolved=False,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(row)
        db.commit()
        return row

    @staticmethod
    def safe_record_failure(
        db: Session,
        *,
        packet_payload: dict[str, Any],
        failure_reason: str,
        error_message: str | None = None,
    ) -> None:
        """Record failures without raising from worker loops."""
        try:
            UnprocessedPacketService.record_failure(
                db,
                packet_payload=packet_payload,
                failure_reason=failure_reason,
                error_message=error_message,
            )
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.exception(
                "Failed to persist unprocessed packet log reason=%s type=%s",
                failure_reason,
                packet_payload.get("type"),
            )
