"""Tests for GPU accounting aggregates exposed by the projects API."""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.api.projects import list_projects
from app.models.gpu_usage_record import GpuUsageRecord
from app.services.gpu_accounting.summary import (
    gpu_accounting_summaries,
    gpu_accounting_totals,
)
from tests.gpu_accounting_support import gpu_project


def _add(db, project, day, username, hours, status, loaded_at=None):
    db.add(
        GpuUsageRecord(
            project_id=project.id,
            usage_date=day,
            username=username,
            attribution=GpuUsageRecord.ATTRIBUTION_MEMBER,
            gpu_hours=Decimal(hours),
            charge=Decimal(hours),
            local_record_id=f"{project.id}-{day}-{username}",
            status=status,
            attempts=1,
            loaded_at=loaded_at,
        )
    )
    db.commit()


def test_summaries_split_by_status(db, make_project):
    project = gpu_project(db, make_project)
    loaded_at = datetime(2026, 10, 7, 12, tzinfo=UTC)
    _add(db, project, date(2026, 10, 1), "a", "10", GpuUsageRecord.STATUS_LOADED, loaded_at)
    _add(db, project, date(2026, 10, 2), "a", "4", GpuUsageRecord.STATUS_SUBMITTED)
    _add(db, project, date(2026, 10, 3), "a", "2", GpuUsageRecord.STATUS_PENDING)
    _add(db, project, date(2026, 10, 4), "a", "1", GpuUsageRecord.STATUS_FAILED)

    summary = gpu_accounting_summaries(db, [project])[project.id]

    assert summary.gpu_hours_used == 17.0
    assert summary.su_loaded == 10.0
    assert summary.su_submitted == 4.0
    assert summary.su_pending == 2.0
    assert summary.su_failed == 1.0
    assert summary.failed_records == 1
    assert summary.usage_through == date(2026, 10, 4)
    assert summary.last_loaded_at.replace(tzinfo=UTC) == loaded_at


def test_gpu_project_without_records_gets_zero_summary(db, make_project):
    project = gpu_project(db, make_project)
    summary = gpu_accounting_summaries(db, [project])[project.id]
    assert summary.gpu_hours_used == 0.0
    assert summary.usage_through is None


def test_non_gpu_projects_have_no_summary(db, make_project):
    project = make_project(db, allocated_resource="nrp-classroom.access-ci.org")
    assert gpu_accounting_summaries(db, [project]) == {}


def test_totals(db, make_project):
    project = gpu_project(db, make_project)
    _add(db, project, date(2026, 10, 1), "a", "10", GpuUsageRecord.STATUS_LOADED)
    _add(db, project, date(2026, 10, 2), "a", "4", GpuUsageRecord.STATUS_SUBMITTED)

    assert gpu_accounting_totals(db) == (14.0, 10.0)


def test_list_projects_includes_gpu_accounting(db, make_project):
    gpu = gpu_project(db, make_project)
    other = make_project(db, allocated_resource="nrp-classroom.access-ci.org")
    _add(db, gpu, date(2026, 10, 1), "a", "5", GpuUsageRecord.STATUS_LOADED)

    projects = {p.id: p for p in list_projects(include_debug=False, db=db)}

    assert projects[gpu.id].gpu_accounting.su_loaded == 5.0
    assert projects[other.id].gpu_accounting is None
