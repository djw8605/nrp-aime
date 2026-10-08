"""Aggregate the GPU usage ledger for API responses."""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.gpu_usage_record import GpuUsageRecord
from app.models.project import Project
from app.schemas.project import GpuAccountingSummary
from app.services.gpu_accounting.scope import is_gpu_project


def gpu_accounting_summaries(
    db: Session, projects: Iterable[Project]
) -> dict[uuid.UUID, GpuAccountingSummary]:
    """Return a summary per GPU project (non-GPU projects are omitted)."""
    summaries = {p.id: GpuAccountingSummary() for p in projects if is_gpu_project(p)}
    if not summaries:
        return {}

    rows = (
        db.query(
            GpuUsageRecord.project_id,
            GpuUsageRecord.status,
            func.coalesce(func.sum(GpuUsageRecord.gpu_hours), 0),
            func.coalesce(func.sum(GpuUsageRecord.charge), 0),
            func.count(GpuUsageRecord.id),
            func.max(GpuUsageRecord.usage_date),
            func.max(GpuUsageRecord.loaded_at),
        )
        .filter(GpuUsageRecord.project_id.in_(list(summaries)))
        .group_by(GpuUsageRecord.project_id, GpuUsageRecord.status)
        .all()
    )
    for project_id, status, hours, charge, count, max_date, max_loaded in rows:
        summary = summaries[project_id]
        summary.gpu_hours_used += float(hours or 0)
        charge = float(charge or 0)
        if status == GpuUsageRecord.STATUS_LOADED:
            summary.su_loaded += charge
        elif status == GpuUsageRecord.STATUS_SUBMITTED:
            summary.su_submitted += charge
        elif status == GpuUsageRecord.STATUS_FAILED:
            summary.su_failed += charge
            summary.failed_records += int(count or 0)
        else:
            summary.su_pending += charge
        if max_date is not None and (
            summary.usage_through is None or max_date > summary.usage_through
        ):
            summary.usage_through = max_date
        if max_loaded is not None and (
            summary.last_loaded_at is None or max_loaded > summary.last_loaded_at
        ):
            summary.last_loaded_at = max_loaded
    return summaries


def gpu_accounting_totals(db: Session) -> tuple[float, float]:
    """Return (total GPU SU used, total GPU SU loaded at ACCESS)."""
    used, loaded = db.query(
        func.coalesce(func.sum(GpuUsageRecord.charge), 0),
        func.coalesce(
            func.sum(
                case(
                    (
                        GpuUsageRecord.status == GpuUsageRecord.STATUS_LOADED,
                        GpuUsageRecord.charge,
                    ),
                    else_=0,
                )
            ),
            0,
        ),
    ).one()
    return float(used or 0), float(loaded or 0)
