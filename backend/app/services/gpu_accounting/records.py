"""List GPU usage ledger rows (e.g. to review ACCESS failures in the web UI)."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session, joinedload

from app.models.gpu_usage_record import GpuUsageRecord

DEFAULT_LIMIT = 200
MAX_LIMIT = 1000


def list_gpu_usage_records(
    db: Session,
    *,
    statuses: list[str] | None = None,
    project_id: uuid.UUID | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[GpuUsageRecord]:
    """Return ledger rows, newest usage date first, then by username.

    ``statuses`` of None or empty applies no status filter. ``limit`` is
    clamped to ``[1, MAX_LIMIT]``.
    """
    query = db.query(GpuUsageRecord).options(joinedload(GpuUsageRecord.project))
    if statuses:
        query = query.filter(GpuUsageRecord.status.in_(statuses))
    if project_id is not None:
        query = query.filter(GpuUsageRecord.project_id == project_id)
    return (
        query.order_by(GpuUsageRecord.usage_date.desc(), GpuUsageRecord.username)
        .limit(max(1, min(limit, MAX_LIMIT)))
        .all()
    )
