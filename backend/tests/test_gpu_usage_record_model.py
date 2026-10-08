"""Tests for the GPU usage ledger model."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.gpu_usage_record import GpuUsageRecord


def _record(project, **overrides):
    defaults = {
        "project_id": project.id,
        "usage_date": date(2026, 10, 1),
        "username": "alice",
        "attribution": GpuUsageRecord.ATTRIBUTION_MEMBER,
        "gpu_hours": Decimal("1.5"),
        "charge": Decimal("1.5"),
        "local_record_id": "nrp-gpu-p1-20261001-abc",
    }
    defaults.update(overrides)
    return GpuUsageRecord(**defaults)


def test_record_defaults_to_pending(db, make_project):
    project = make_project(db)
    record = _record(project)
    db.add(record)
    db.flush()
    assert record.status == GpuUsageRecord.STATUS_PENDING
    assert record.attempts == 0
    assert record.submitted_charge is None


def test_project_date_username_is_unique(db, make_project):
    project = make_project(db)
    db.add(_record(project))
    db.flush()
    db.add(_record(project, local_record_id="nrp-gpu-p1-20261001-other"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_project_has_synced_through_column(db, make_project):
    project = make_project(db, gpu_usage_synced_through=date(2026, 10, 7))
    db.flush()
    assert project.gpu_usage_synced_through == date(2026, 10, 7)
