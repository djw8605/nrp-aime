"""GPU usage ledger endpoints (review what was reported to ACCESS)."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.project import GpuUsageRecordRead
from app.services.gpu_accounting.records import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    list_gpu_usage_records,
)

router = APIRouter()


@router.get("/", response_model=list[GpuUsageRecordRead])
def list_gpu_usage(
    status: list[str] = Query(default=["failed"]),
    project_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    db: Session = Depends(get_db),
) -> list[GpuUsageRecordRead]:
    """Return GPU usage records filtered by status (default: failed)."""
    records = list_gpu_usage_records(
        db, statuses=status, project_id=project_id, limit=limit
    )
    return [
        GpuUsageRecordRead(
            id=r.id,
            project_id=r.project_id,
            project_name=r.project.name,
            site_project_id=r.project.site_project_id,
            usage_date=r.usage_date,
            username=r.username,
            attribution=r.attribution,
            gpu_hours=float(r.gpu_hours),
            charge=float(r.charge),
            status=r.status,
            last_error=r.last_error,
            attempts=r.attempts,
            submitted_at=r.submitted_at,
            loaded_at=r.loaded_at,
            local_record_id=r.local_record_id,
        )
        for r in records
    ]
