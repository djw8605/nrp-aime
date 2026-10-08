"""Tests for the GPU usage ledger listing API (review ACCESS failures)."""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.api.gpu_usage import list_gpu_usage
from app.models.gpu_usage_record import GpuUsageRecord
from app.services.gpu_accounting.records import list_gpu_usage_records
from tests.gpu_accounting_support import gpu_project


def _add(db, project, day, username, status, *, error=None, hours="2.5", attempts=1):
    record = GpuUsageRecord(
        project_id=project.id,
        usage_date=day,
        username=username,
        attribution=GpuUsageRecord.ATTRIBUTION_MEMBER,
        gpu_hours=Decimal(hours),
        charge=Decimal(hours),
        local_record_id=f"{project.id}-{day}-{username}",
        status=status,
        last_error=error,
        attempts=attempts,
        submitted_at=datetime(2026, 10, 7, 12, tzinfo=UTC),
    )
    db.add(record)
    db.commit()
    return record


def _call(db, *, status=("failed",), project_id=None, limit=200):
    return list_gpu_usage(
        status=list(status), project_id=project_id, limit=limit, db=db
    )


def test_default_returns_only_failed_rows_with_error_and_project(db, make_project):
    project = gpu_project(db, make_project, name="Failing Project")
    _add(
        db, project, date(2026, 10, 1), "alice", GpuUsageRecord.STATUS_FAILED,
        error="Unknown username alice",
    )
    _add(db, project, date(2026, 10, 2), "alice", GpuUsageRecord.STATUS_LOADED)
    _add(db, project, date(2026, 10, 3), "alice", GpuUsageRecord.STATUS_PENDING)

    rows = _call(db)

    assert len(rows) == 1
    row = rows[0]
    assert row.status == "failed"
    assert row.last_error == "Unknown username alice"
    assert row.project_id == project.id
    assert row.project_name == "Failing Project"
    assert row.site_project_id == "p.gpu1"
    assert row.username == "alice"
    assert row.usage_date == date(2026, 10, 1)
    assert row.gpu_hours == 2.5
    assert row.charge == 2.5
    assert row.attempts == 1
    assert row.attribution == GpuUsageRecord.ATTRIBUTION_MEMBER
    assert row.local_record_id.endswith("alice")
    assert row.submitted_at is not None
    assert row.loaded_at is None


def test_status_list_filter(db, make_project):
    project = gpu_project(db, make_project)
    _add(db, project, date(2026, 10, 1), "a", GpuUsageRecord.STATUS_FAILED)
    _add(db, project, date(2026, 10, 2), "a", GpuUsageRecord.STATUS_PENDING)
    _add(db, project, date(2026, 10, 3), "a", GpuUsageRecord.STATUS_SUBMITTED)
    _add(db, project, date(2026, 10, 4), "a", GpuUsageRecord.STATUS_LOADED)

    rows = _call(db, status=("failed", "pending"))
    assert {r.status for r in rows} == {"failed", "pending"}

    rows = _call(db, status=("loaded",))
    assert [r.status for r in rows] == ["loaded"]


def test_empty_status_list_returns_all(db, make_project):
    project = gpu_project(db, make_project)
    _add(db, project, date(2026, 10, 1), "a", GpuUsageRecord.STATUS_FAILED)
    _add(db, project, date(2026, 10, 2), "a", GpuUsageRecord.STATUS_LOADED)

    assert len(_call(db, status=())) == 2


def test_project_filter(db, make_project):
    one = gpu_project(db, make_project)
    two = gpu_project(
        db, make_project, site_project_id="p.gpu2", kubernetes_namespace="ns-gpu2"
    )
    _add(db, one, date(2026, 10, 1), "a", GpuUsageRecord.STATUS_FAILED)
    _add(db, two, date(2026, 10, 1), "b", GpuUsageRecord.STATUS_FAILED)

    assert len(_call(db)) == 2
    rows = _call(db, project_id=two.id)
    assert [r.username for r in rows] == ["b"]


def test_limit_is_applied(db, make_project):
    project = gpu_project(db, make_project)
    for day in range(1, 6):
        _add(db, project, date(2026, 10, day), "a", GpuUsageRecord.STATUS_FAILED)

    rows = _call(db, limit=3)

    assert [r.usage_date.day for r in rows] == [5, 4, 3]


def test_service_clamps_oversized_limit(db, make_project):
    project = gpu_project(db, make_project)
    _add(db, project, date(2026, 10, 1), "a", GpuUsageRecord.STATUS_FAILED)

    rows = list_gpu_usage_records(
        db, statuses=None, project_id=None, limit=10_000_000
    )
    assert len(rows) == 1


def test_ordered_by_date_desc_then_username(db, make_project):
    project = gpu_project(db, make_project)
    _add(db, project, date(2026, 10, 1), "zed", GpuUsageRecord.STATUS_FAILED)
    _add(db, project, date(2026, 10, 2), "bob", GpuUsageRecord.STATUS_FAILED)
    _add(db, project, date(2026, 10, 2), "amy", GpuUsageRecord.STATUS_FAILED)

    rows = _call(db)

    assert [(r.usage_date.day, r.username) for r in rows] == [
        (2, "amy"),
        (2, "bob"),
        (1, "zed"),
    ]


def test_route_declares_repeatable_status_defaulting_to_failed():
    from fastapi import FastAPI

    from app.api.gpu_usage import router

    app = FastAPI()
    app.include_router(router, prefix="/gpu-usage")
    params = {
        p["name"]: p
        for p in app.openapi()["paths"]["/gpu-usage/"]["get"]["parameters"]
    }

    assert params["status"]["schema"]["type"] == "array"
    assert params["status"]["schema"]["default"] == ["failed"]
    assert params["limit"]["schema"]["maximum"] == 1000
