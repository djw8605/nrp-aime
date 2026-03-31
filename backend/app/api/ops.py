"""Operational observability API endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.outbound_packet_log import OutboundPacketLog
from app.services.observability import ObservabilityService

router = APIRouter()


@router.get("/workers/status")
def get_worker_statuses(db: Session = Depends(get_db)) -> dict:
    """Return worker statuses with heartbeat lag and error/success timestamps."""
    return {"workers": ObservabilityService.worker_statuses(db)}


@router.get("/freshness")
def get_data_freshness(db: Session = Depends(get_db)) -> dict:
    """Return data freshness indicators for key integrations."""
    return ObservabilityService.data_freshness(db)


@router.get("/metrics/error-budget")
def get_error_budget_metrics(db: Session = Depends(get_db)) -> dict:
    """Return packet error-budget metrics."""
    return ObservabilityService.error_budget_metrics(db)


@router.get("/metrics/lifecycle-funnel")
def get_lifecycle_funnel_metrics(db: Session = Depends(get_db)) -> dict:
    """Return account lifecycle funnel metrics."""
    return ObservabilityService.lifecycle_funnel_metrics(db)


@router.get("/metrics/queue-latency")
def get_queue_latency_metrics(db: Session = Depends(get_db)) -> dict:
    """Return queue and end-to-end latency metrics."""
    return ObservabilityService.queue_latency_metrics(db)


@router.post("/alerts/evaluate")
def evaluate_alerts(db: Session = Depends(get_db)) -> dict:
    """Evaluate and send operational alerts to configured hooks."""
    return ObservabilityService.evaluate_alerts(db)


@router.get("/pending-actions")
def get_pending_actions(db: Session = Depends(get_db)) -> dict:
    """Return items that require admin attention."""
    return ObservabilityService.pending_actions(db)


@router.get("/outbound-packets")
def list_outbound_packet_logs(
    db: Session = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=2000),
) -> dict:
    """Return most recent outbound packet logs."""
    rows = (
        db.query(OutboundPacketLog)
        .order_by(OutboundPacketLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "id": str(row.id),
                "worker_name": row.worker_name,
                "event_type": row.event_type,
                "status": row.status,
                "ack_status": row.ack_status,
                "source_packet_rec_id": row.source_packet_rec_id,
                "source_trans_rec_id": row.source_trans_rec_id,
                "source_transaction_id": row.source_transaction_id,
                "outbound_packet_rec_id": row.outbound_packet_rec_id,
                "outbound_transaction_id": row.outbound_transaction_id,
                "project_user_id": str(row.project_user_id) if row.project_user_id else None,
                "retry_count": row.retry_count,
                "max_retries": row.max_retries,
                "locked_until": row.locked_until.isoformat() if row.locked_until else None,
                "next_retry_at": row.next_retry_at.isoformat() if row.next_retry_at else None,
                "last_attempt_at": row.last_attempt_at.isoformat() if row.last_attempt_at else None,
                "sent_at": row.sent_at.isoformat() if row.sent_at else None,
                "acked_at": row.acked_at.isoformat() if row.acked_at else None,
                "last_error": row.last_error,
                "payload": row.payload,
                "response_payload": row.response_payload,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ]
    }
