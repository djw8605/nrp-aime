"""Operational observability and metrics service."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.amie_packet import AMIEPacket
from app.models.outbound_packet_log import OutboundPacketLog
from app.models.project import Project
from app.models.project_user import ProjectUser
from app.models.user import User
from app.models.worker_status import WorkerStatus
from app.services.alerts import AlertService


class ObservabilityService:
    """Builds operational metrics and health indicators."""

    @staticmethod
    def _iso_or_none(value: datetime | None) -> str | None:
        return value.astimezone(UTC).isoformat() if value else None

    @classmethod
    def worker_statuses(cls, db: Session) -> list[dict[str, Any]]:
        """Return worker status rows with heartbeat lag and freshness."""
        now = datetime.now(UTC)
        rows = db.query(WorkerStatus).order_by(WorkerStatus.worker_name.asc()).all()
        output: list[dict[str, Any]] = []
        for row in rows:
            lag_seconds = None
            if row.last_heartbeat is not None:
                lag_seconds = max(0, int((now - row.last_heartbeat).total_seconds()))
            payload = row.state_payload or {}
            output.append(
                {
                    "worker_name": row.worker_name,
                    "is_active": row.is_active,
                    "current_state": row.current_state,
                    "status_message": row.status_message,
                    "state_payload": payload,
                    "last_heartbeat": cls._iso_or_none(row.last_heartbeat),
                    "heartbeat_lag_seconds": lag_seconds,
                    "last_success_at": cls._iso_or_none(row.last_success_at),
                    "last_error_at": cls._iso_or_none(row.last_error_at),
                    "last_error_message": row.last_error_message,
                }
            )
        return output

    @classmethod
    def data_freshness(cls, db: Session) -> dict[str, Any]:
        """Compute latest successful poll/export/reconcile timestamps."""
        aime_worker = (
            db.query(WorkerStatus)
            .filter(WorkerStatus.worker_name == "aime-worker")
            .first()
        )
        usage_worker = (
            db.query(WorkerStatus)
            .filter(WorkerStatus.worker_name == "usage-worker")
            .first()
        )

        aime_payload = aime_worker.state_payload if aime_worker and aime_worker.state_payload else {}
        usage_payload = usage_worker.state_payload if usage_worker and usage_worker.state_payload else {}

        last_packet_poll_at = aime_payload.get("last_successful_poll_at")
        last_account_confirmation_sync_at = aime_payload.get(
            "last_successful_account_confirmation_sync_at"
        )
        last_usage_export_at = usage_payload.get("last_successful_usage_export_at")

        return {
            "last_successful_packet_poll_at": last_packet_poll_at,
            "last_successful_usage_export_at": last_usage_export_at,
            "last_successful_account_confirmation_sync_at": (
                last_account_confirmation_sync_at
            ),
            "aime_worker_last_success_at": cls._iso_or_none(
                aime_worker.last_success_at if aime_worker else None
            ),
            "usage_worker_last_success_at": cls._iso_or_none(
                usage_worker.last_success_at if usage_worker else None
            ),
        }

    @classmethod
    def error_budget_metrics(cls, db: Session) -> dict[str, Any]:
        """Return packet parse/unsupported/manual and outbound failure metrics."""
        total_packets = db.query(AMIEPacket).count()
        manual_ingest_count = (
            db.query(AMIEPacket)
            .filter(AMIEPacket.ingest_source == AMIEPacket.INGEST_SOURCE_MANUAL)
            .count()
        )
        unsupported_count = (
            db.query(AMIEPacket)
            .filter(
                AMIEPacket.processing_status == AMIEPacket.PROCESSING_STATUS_UNPROCESSED,
                AMIEPacket.processing_error.ilike("%Unsupported packet type%"),
            )
            .count()
        )
        parse_failure_rows = (
            db.query(AMIEPacket.packet_type, AMIEPacket.processing_error)
            .filter(
                AMIEPacket.processing_status.in_(
                    [
                        AMIEPacket.PROCESSING_STATUS_ERROR,
                        AMIEPacket.PROCESSING_STATUS_UNPROCESSED,
                    ]
                )
            )
            .all()
        )
        parse_failures_by_type: Counter[str] = Counter()
        for packet_type, error in parse_failure_rows:
            msg = (error or "").lower()
            if "validation" in msg or "parse" in msg or "unsupported packet type" in msg:
                parse_failures_by_type[str(packet_type or "unknown")] += 1

        outbound_failures = (
            db.query(OutboundPacketLog)
            .filter(
                OutboundPacketLog.status.in_(
                    [OutboundPacketLog.STATUS_FAILED, OutboundPacketLog.STATUS_LOCKED]
                )
            )
            .count()
        )
        unprocessed_count = (
            db.query(AMIEPacket)
            .filter(AMIEPacket.processing_status == AMIEPacket.PROCESSING_STATUS_UNPROCESSED)
            .count()
        )
        error_count = (
            db.query(AMIEPacket)
            .filter(AMIEPacket.processing_status == AMIEPacket.PROCESSING_STATUS_ERROR)
            .count()
        )

        return {
            "total_packets": total_packets,
            "manual_ingest_count": manual_ingest_count,
            "unsupported_packet_count": unsupported_count,
            "unprocessed_packet_count": unprocessed_count,
            "error_packet_count": error_count,
            "parse_failures_total": sum(parse_failures_by_type.values()),
            "parse_failures_by_type": dict(parse_failures_by_type),
            "outbound_failures": outbound_failures,
        }

    @staticmethod
    def lifecycle_funnel_metrics(db: Session) -> dict[str, Any]:
        """Return lifecycle funnel counts."""
        just_received = (
            db.query(ProjectUser)
            .filter(ProjectUser.account_state == ProjectUser.ACCOUNT_STATE_JUST_RECEIVED_PACKET)
            .count()
        )
        sent_email = (
            db.query(ProjectUser)
            .filter(ProjectUser.account_state == ProjectUser.ACCOUNT_STATE_SENT_EMAIL)
            .count()
        )
        account_made = (
            db.query(ProjectUser)
            .filter(ProjectUser.account_state == ProjectUser.ACCOUNT_STATE_ACCOUNT_MADE)
            .count()
        )
        confirmation_sent = (
            db.query(ProjectUser)
            .filter(ProjectUser.aime_confirmation_sent_at.is_not(None))
            .count()
        )
        return {
            "just_received_packet": just_received,
            "sent_email": sent_email,
            "account_made": account_made,
            "notify_account_create_sent": confirmation_sent,
        }

    @staticmethod
    def queue_latency_metrics(db: Session) -> dict[str, Any]:
        """Return queue and lifecycle latency metrics in seconds."""
        project_rows = (
            db.query(
                AMIEPacket.created_at.label("packet_received_at"),
                Project.created_at.label("project_created_at"),
            )
            .join(Project, Project.source_packet_rec_id == AMIEPacket.packet_rec_id)
            .all()
        )
        project_completion_latencies = [
            (row.project_created_at - row.packet_received_at).total_seconds()
            for row in project_rows
            if row.packet_received_at is not None and row.project_created_at is not None
            and row.project_created_at >= row.packet_received_at
        ]

        user_rows = (
            db.query(
                AMIEPacket.created_at.label("packet_received_at"),
                User.created_at.label("user_created_at"),
            )
            .join(ProjectUser, ProjectUser.source_packet_rec_id == AMIEPacket.packet_rec_id)
            .join(User, User.id == ProjectUser.user_id)
            .all()
        )
        user_completion_latencies = [
            (row.user_created_at - row.packet_received_at).total_seconds()
            for row in user_rows
            if row.packet_received_at is not None and row.user_created_at is not None
            and row.user_created_at >= row.packet_received_at
        ]

        rows = (
            db.query(
                AMIEPacket.created_at.label("packet_received_at"),
                ProjectUser.email_sent_at,
                ProjectUser.account_made_at,
                ProjectUser.aime_confirmation_sent_at,
            )
            .join(ProjectUser, ProjectUser.source_packet_rec_id == AMIEPacket.packet_rec_id)
            .all()
        )
        email_latencies: list[float] = []
        account_latencies: list[float] = []
        confirmation_latencies: list[float] = []
        for row in rows:
            if row.packet_received_at is None:
                continue
            if row.email_sent_at is not None:
                email_latencies.append(
                    (row.email_sent_at - row.packet_received_at).total_seconds()
                )
            if row.account_made_at is not None:
                account_latencies.append(
                    (row.account_made_at - row.packet_received_at).total_seconds()
                )
            if row.aime_confirmation_sent_at is not None:
                confirmation_latencies.append(
                    (row.aime_confirmation_sent_at - row.packet_received_at).total_seconds()
                )

        def _avg(values: list[float]) -> float:
            if not values:
                return 0.0
            return float(sum(values) / len(values))

        pending_email = (
            db.query(ProjectUser)
            .filter(
                and_(
                    ProjectUser.account_state == ProjectUser.ACCOUNT_STATE_JUST_RECEIVED_PACKET,
                    ProjectUser.email_sent_at.is_(None),
                )
            )
            .count()
        )
        pending_confirmation = (
            db.query(ProjectUser)
            .filter(
                and_(
                    ProjectUser.account_state == ProjectUser.ACCOUNT_STATE_ACCOUNT_MADE,
                    ProjectUser.aime_confirmation_sent_at.is_(None),
                )
            )
            .count()
        )
        return {
            "avg_seconds_to_project_completion": _avg(project_completion_latencies),
            "avg_seconds_to_user_completion": _avg(user_completion_latencies),
            "avg_seconds_to_email_sent": _avg(email_latencies),
            "avg_seconds_to_account_made": _avg(account_latencies),
            "avg_seconds_to_notify_account_create_sent": _avg(confirmation_latencies),
            "project_completion_samples": len(project_completion_latencies),
            "user_completion_samples": len(user_completion_latencies),
            "pending_email_queue": pending_email,
            "pending_confirmation_queue": pending_confirmation,
        }

    @classmethod
    def transaction_summary(cls, db: Session, transaction_id: int) -> dict[str, Any]:
        """Build transaction-centric packet view."""
        packets = (
            db.query(AMIEPacket)
            .filter(AMIEPacket.transaction_id == transaction_id)
            .order_by(AMIEPacket.created_at.asc())
            .all()
        )
        if not packets:
            return {
                "transaction_id": transaction_id,
                "packets": [],
                "packet_count": 0,
                "current_state": "not_found",
                "pending_actions": [],
                "reply_eligible": False,
            }

        latest = packets[-1]
        current_state = latest.transaction_state or latest.packet_state or "unknown"
        pending_actions: list[str] = []
        packet_types = {pkt.packet_type for pkt in packets}
        if "request_account_create" in packet_types:
            pending_actions.append("notify_account_create_if_account_made")
        if "request_project_create" in packet_types:
            pending_actions.append("review_project_create_completion")
            if "notify_project_create" not in packet_types:
                pending_actions.append("missing_notify_project_create")
            if "data_project_create" not in packet_types:
                pending_actions.append("missing_data_project_create")
            if "inform_transaction_complete" not in packet_types:
                pending_actions.append("missing_inform_transaction_complete")
        if "request_account_create" in packet_types:
            if "notify_account_create" not in packet_types:
                pending_actions.append("missing_notify_account_create")
            if "data_account_create" not in packet_types:
                pending_actions.append("missing_data_account_create")
            if "inform_transaction_complete" not in packet_types:
                pending_actions.append("missing_inform_transaction_complete")
        pending_actions = list(dict.fromkeys(pending_actions))

        reply_eligible = any(
            (pkt.packet_type or "").startswith("request_")
            and pkt.processing_status != AMIEPacket.PROCESSING_STATUS_PROCESSED
            for pkt in packets
        )

        return {
            "transaction_id": transaction_id,
            "trans_rec_id": latest.trans_rec_id,
            "packet_count": len(packets),
            "current_state": current_state,
            "pending_actions": pending_actions,
            "reply_eligible": reply_eligible,
            "packets": [
                {
                    "id": str(pkt.id),
                    "packet_rec_id": pkt.packet_rec_id,
                    "packet_type": pkt.packet_type,
                    "outgoing_flag": pkt.outgoing_flag,
                    "packet_state": pkt.packet_state,
                    "transaction_state": pkt.transaction_state,
                    "processing_status": pkt.processing_status,
                    "processing_error": pkt.processing_error,
                    "received_at": cls._iso_or_none(pkt.created_at),
                    "processed_at": cls._iso_or_none(pkt.processed_at),
                    "raw_packet": pkt.raw_packet,
                }
                for pkt in packets
            ],
        }

    @classmethod
    def evaluate_alerts(cls, db: Session) -> dict[str, Any]:
        """Evaluate alert conditions and dispatch hooks."""
        now = datetime.now(UTC)
        sent: list[dict[str, Any]] = []

        statuses = cls.worker_statuses(db)
        for status in statuses:
            lag = status.get("heartbeat_lag_seconds")
            if lag is None:
                continue
            if lag > settings.alert_worker_stale_seconds:
                sent.append(
                    AlertService.send(
                        db,
                        alert_key=f"worker_stale:{status['worker_name']}",
                        category="worker",
                        severity="error",
                        title=f"Worker stale: {status['worker_name']}",
                        message=f"Worker heartbeat lag is {lag}s",
                        payload=status,
                    )
                )
            else:
                AlertService.resolve(
                    db, alert_key=f"worker_stale:{status['worker_name']}"
                )

        budget = cls.error_budget_metrics(db)
        if budget["parse_failures_total"] >= settings.alert_parse_failures_threshold:
            sent.append(
                AlertService.send(
                    db,
                    alert_key="parse_failures_threshold",
                    category="parsing",
                    severity="warn",
                    title="Parse failures threshold exceeded",
                    message=(
                        f"Parse failures={budget['parse_failures_total']} "
                        f"(threshold={settings.alert_parse_failures_threshold})"
                    ),
                    payload=budget,
                )
            )
        else:
            AlertService.resolve(db, alert_key="parse_failures_threshold")

        return {"alerts_evaluated_at": now.isoformat(), "results": sent}

    @staticmethod
    def project_user_packet_alert_fields(packet: AMIEPacket) -> tuple[str, str] | None:
        """Return alert classification for new user account request packets."""
        packet_type = (packet.packet_type or "").strip().lower()
        if packet_type == "request_account_create":
            return ("user_packet", "New user account request received")
        return None
