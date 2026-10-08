"""Data migration 0023: re-key GPU usage rows whose username exceeds 30 chars."""

import hashlib
import importlib.util
from datetime import date
from decimal import Decimal
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.models.gpu_usage_record import GpuUsageRecord

LONG = "http://cilogon.org/serverE/users/546379"
TAIL = "logon.org/serverE/users/546379"
SHORT = "alice_nrp"
ERROR = "Re-keyed: Username exceeded the AMIE 30-character login limit"


def _migration():
    path = (
        Path(__file__).resolve().parent.parent
        / "migrations"
        / "versions"
        / "0023_gpu_usage_amie_login.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0023", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _local_id(site_project_id, usage_date, username):
    digest = hashlib.sha256(username.encode()).hexdigest()[:12]
    return f"nrp-gpu-{site_project_id}-{usage_date:%Y%m%d}-{digest}"


def _record(project, usage_date, username, **overrides):
    defaults = {
        "project_id": project.id,
        "usage_date": usage_date,
        "username": username,
        "attribution": GpuUsageRecord.ATTRIBUTION_PI,
        "gpu_hours": Decimal("2"),
        "charge": Decimal("2"),
        "local_record_id": _local_id(project.site_project_id, usage_date, username),
        "status": GpuUsageRecord.STATUS_SUBMITTED,
        "submitted_charge": Decimal("2"),
        "accounting_db_record_id": "acct-1",
        "attempts": 3,
    }
    defaults.update(overrides)
    return GpuUsageRecord(**defaults)


def _run_upgrade(db):
    db.commit()
    db.close()
    with db.get_bind().begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            _migration().upgrade()


def test_revision_ids():
    module = _migration()
    assert module.revision == "0023_gpu_usage_amie_login"
    assert module.down_revision == "0022_gpu_usage_records"


def test_long_username_rekeyed_to_pending(db, make_project):
    project = make_project(db, site_project_id="nrp-cis261590")
    day = date(2026, 10, 1)
    db.add(
        _record(
            project, day, LONG, loaded_at=None, submitted_at=None,
        )
    )
    db.flush()

    _run_upgrade(db)

    row = db.query(GpuUsageRecord).one()
    assert row.username == TAIL
    assert row.local_record_id == _local_id("nrp-cis261590", day, TAIL)
    assert row.status == "pending"
    assert row.submitted_charge is None
    assert row.submitted_at is None
    assert row.loaded_at is None
    assert row.accounting_db_record_id is None
    assert row.last_error == ERROR
    assert row.attempts == 3
    assert row.gpu_hours == Decimal("2")
    assert row.charge == Decimal("2")


def test_loaded_state_cleared_on_rekey(db, make_project):
    from datetime import UTC, datetime

    project = make_project(db, site_project_id="nrp-cis261590")
    stamp = datetime(2026, 10, 2, tzinfo=UTC)
    db.add(
        _record(
            project, date(2026, 10, 1), LONG,
            status=GpuUsageRecord.STATUS_LOADED, submitted_at=stamp, loaded_at=stamp,
        )
    )
    db.flush()

    _run_upgrade(db)

    row = db.query(GpuUsageRecord).one()
    assert row.status == "pending"
    assert row.submitted_at is None
    assert row.loaded_at is None


def test_short_username_row_untouched(db, make_project):
    project = make_project(db, site_project_id="nrp-cis261590")
    day = date(2026, 10, 1)
    db.add(
        _record(
            project, day, SHORT, status=GpuUsageRecord.STATUS_LOADED,
            last_error=None,
        )
    )
    db.add(_record(project, day, "a" * 30))
    db.flush()

    _run_upgrade(db)

    rows = {r.username: r for r in db.query(GpuUsageRecord).all()}
    assert set(rows) == {SHORT, "a" * 30}
    short = rows[SHORT]
    assert short.status == "loaded"
    assert short.last_error is None
    assert short.submitted_charge == Decimal("2")
    assert short.accounting_db_record_id == "acct-1"
    assert short.local_record_id == _local_id("nrp-cis261590", day, SHORT)
    assert rows["a" * 30].status == "submitted"


def test_collision_merges_into_existing_row(db, make_project):
    project = make_project(db, site_project_id="nrp-cis261590")
    day = date(2026, 10, 1)
    db.add(
        _record(
            project, day, TAIL, gpu_hours=Decimal("1.5"), charge=Decimal("1.5"),
            status=GpuUsageRecord.STATUS_LOADED, attempts=1,
        )
    )
    db.add(_record(project, day, LONG, gpu_hours=Decimal("2.25"), charge=Decimal("2.25")))
    db.flush()

    _run_upgrade(db)

    row = db.query(GpuUsageRecord).one()
    assert row.username == TAIL
    assert row.local_record_id == _local_id("nrp-cis261590", day, TAIL)
    assert row.gpu_hours == Decimal("3.75")
    assert row.charge == Decimal("3.75")
    assert row.status == "pending"
    assert row.submitted_charge is None
    assert row.accounting_db_record_id is None
    assert row.last_error == ERROR
    assert row.attempts == 1


def test_downgrade_is_noop():
    _migration().downgrade()
