"""Tests for submitting GPU usage to ACCESS and reconciling load status."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from amieclient.usage import ComputeUsageRecord, UsageLoadedRecord, UsageMessage
from amieclient.usage.message import UsageMessageError
from amieclient.usage.response import UsageStatusResource

from app.models.gpu_usage_record import GpuUsageRecord
from app.services.aime.usage_api import UsageApiError
from app.services.gpu_accounting.service import GpuAccountingService
from tests.gpu_accounting_support import (
    GPU,
    FakeAccountingClient,
    FakeUsageClient,
    gpu_project,
    usage_row,
)

ALICE = "http://cilogon.org/serverE/users/1001"


def _record(db, project, **overrides):
    defaults = {
        "project_id": project.id,
        "usage_date": date(2026, 10, 2),
        "username": "alice_nrp",
        "attribution": GpuUsageRecord.ATTRIBUTION_MEMBER,
        "gpu_hours": Decimal("2.5"),
        "charge": Decimal("2.5"),
        "local_record_id": f"nrp-gpu-p.gpu1-20261002-{overrides.get('username', 'alice_nrp')}",
        "status": GpuUsageRecord.STATUS_PENDING,
        "attempts": 0,
    }
    defaults.update(overrides)
    record = GpuUsageRecord(**defaults)
    db.add(record)
    db.commit()
    return record


def _submitted(db, project, charge="2.5", **overrides):
    return _record(
        db,
        project,
        status=GpuUsageRecord.STATUS_SUBMITTED,
        submitted_charge=Decimal(charge),
        submitted_at=datetime.now(UTC) - timedelta(hours=2),
        **overrides,
    )


def _loaded(record, charge=2.5, resource=GPU):
    return UsageLoadedRecord(
        accounting_db_record_id="134919900",
        local_record_id=record.local_record_id,
        resource=resource,
        submit_time="2026-10-02T00:00:00+00:00",
        loaded_time="2026-10-08T01:00:00+00:00",
        charge=charge,
    )


def _status_error(record, message):
    failed = ComputeUsageRecord(
        username=record.username,
        local_project_id="p.gpu1",
        local_record_id=record.local_record_id,
        resource=GPU,
        submit_time="2026-10-02T00:00:00Z",
        start_time="2026-10-02T00:00:00Z",
        end_time="2026-10-03T00:00:00Z",
        charge="2.5",
        node_count=1,
    )
    return UsageStatusResource(
        resource=GPU,
        loaded_record_count=0,
        failed_job_count=1,
        total_charge=0,
        errors=[UsageMessageError(message, UsageMessage([failed]))],
    )


def _service(usage=None):
    usage = usage or FakeUsageClient()
    return GpuAccountingService(
        accounting_client=FakeAccountingClient(date(2026, 10, 7)),
        usage_client=usage,
    ), usage


def test_submit_posts_compute_record(db, make_project):
    project = gpu_project(db, make_project)
    record = _record(db, project)
    service, usage = _service()

    assert service.submit_pending(db) == {"submitted": 1, "failed": 0}

    [[sent]] = usage.posts
    assert isinstance(sent, ComputeUsageRecord)
    assert sent.as_dict() == {
        "Username": "alice_nrp",
        "LocalProjectID": "p.gpu1",
        "LocalRecordID": record.local_record_id,
        "LocalReference": str(record.id),
        "Resource": GPU,
        "SubmitTime": "2026-10-02T00:00:00Z",
        "StartTime": "2026-10-02T00:00:00Z",
        "EndTime": "2026-10-03T00:00:00Z",
        "Charge": "2.500000",
        "Attributes": {"NodeCount": 1, "Queue": "gpu", "JobName": "nrp-gpu-daily"},
    }
    assert record.status == GpuUsageRecord.STATUS_SUBMITTED
    assert record.submitted_charge == Decimal("2.5")
    assert record.submitted_at is not None
    assert record.attempts == 1


def test_submit_batches_at_max_records(db, make_project, monkeypatch):
    from app.services.gpu_accounting import service as service_module

    monkeypatch.setattr(service_module, "MAX_RECORDS_PER_POST", 2)
    project = gpu_project(db, make_project)
    for i in range(5):
        _record(db, project, username=f"u{i}")
    service, usage = _service()

    assert service.submit_pending(db) == {"submitted": 5, "failed": 0}
    assert [len(batch) for batch in usage.posts] == [2, 2, 1]


def test_validation_failure_marks_failed_and_is_retried(db, make_project):
    project = gpu_project(db, make_project)
    record = _record(db, project)
    service, usage = _service()
    usage.validation_errors = {record.local_record_id: "Unknown user"}

    assert service.submit_pending(db) == {"submitted": 0, "failed": 1}
    assert record.status == GpuUsageRecord.STATUS_FAILED
    assert record.last_error == "Unknown user"

    usage.validation_errors = {}
    assert service.submit_pending(db) == {"submitted": 1, "failed": 0}
    assert record.status == GpuUsageRecord.STATUS_SUBMITTED
    assert record.attempts == 2


def test_api_error_marks_batch_failed(db, make_project):
    project = gpu_project(db, make_project)
    record = _record(db, project)
    service, usage = _service()
    usage.post_error = UsageApiError("ACCESS usage POST failed: Bad XA-SITE")

    assert service.submit_pending(db) == {"submitted": 0, "failed": 1}
    assert record.status == GpuUsageRecord.STATUS_FAILED
    assert "Bad XA-SITE" in record.last_error


def test_unsendable_records_are_skipped(db, make_project):
    project = gpu_project(db, make_project)
    _record(db, project, username="", attribution=GpuUsageRecord.ATTRIBUTION_PI)
    _record(db, project, username="zero", gpu_hours=Decimal("0"), charge=Decimal("0"))
    service, usage = _service()

    assert service.submit_pending(db) == {"submitted": 0, "failed": 0}
    assert usage.posts == []


def test_zeroed_previously_sent_record_is_resent(db, make_project):
    project = gpu_project(db, make_project)
    _record(db, project, gpu_hours=Decimal("0"), charge=Decimal("0"), submitted_charge=Decimal("2.5"))
    service, usage = _service()

    assert service.submit_pending(db) == {"submitted": 1, "failed": 0}
    assert usage.posts[0][0].charge == "0.000000"


def test_reconcile_marks_loaded_when_charge_matches(db, make_project):
    project = gpu_project(db, make_project)
    record = _submitted(db, project)
    service, usage = _service()
    usage.loaded_records = [_loaded(record)]

    assert service.reconcile(db) == {"loaded": 1, "load_failed": 0}
    assert record.status == GpuUsageRecord.STATUS_LOADED
    assert record.accounting_db_record_id == "134919900"
    assert record.loaded_at is not None


def test_reconcile_ignores_stale_charge_and_other_resources(db, make_project):
    project = gpu_project(db, make_project)
    record = _submitted(db, project, charge="3.0")
    service, usage = _service()
    usage.loaded_records = [_loaded(record, charge=2.5), _loaded(record, charge=3.0, resource="other")]

    assert service.reconcile(db) == {"loaded": 0, "load_failed": 0}
    assert record.status == GpuUsageRecord.STATUS_SUBMITTED


def test_reconcile_marks_status_errors_failed(db, make_project):
    project = gpu_project(db, make_project)
    record = _submitted(db, project)
    service, usage = _service()
    usage.status_resources = [
        _status_error(record, "Allocation could not be found for user alice_nrp")
    ]

    assert service.reconcile(db) == {"loaded": 0, "load_failed": 1}
    assert record.status == GpuUsageRecord.STATUS_FAILED
    assert "Allocation could not be found" in record.last_error


def test_reconcile_loaded_wins_and_status_failure_is_tolerated(db, make_project):
    project = gpu_project(db, make_project)
    record = _submitted(db, project)
    service, usage = _service()
    usage.loaded_records = [_loaded(record)]
    usage.status_error = UsageApiError("ACCESS usage/status failed: KeyError")

    assert service.reconcile(db) == {"loaded": 1, "load_failed": 0}
    assert record.status == GpuUsageRecord.STATUS_LOADED


def _cycle_service(db, make_project, make_user, make_project_user, usage):
    """Service whose accounting fake reports one member usage row on 2026-10-02."""
    project = gpu_project(db, make_project)
    alice = make_user(db, remote_site_login=ALICE)
    make_project_user(db, project, alice, remote_site_login="alice_nrp")
    accounting = FakeAccountingClient(date(2026, 10, 7), [usage_row(ALICE, date(2026, 10, 2), "2.5")])
    return GpuAccountingService(accounting_client=accounting, usage_client=usage)


def test_run_cycle_without_api_key_only_syncs(db, make_project, make_user, make_project_user):
    usage = FakeUsageClient(api_key="")
    service = _cycle_service(db, make_project, make_user, make_project_user, usage)

    counters = service.run_cycle(db)

    assert usage.posts == []
    assert counters["projects"] == 1
    assert counters["rows"] == 1
    assert counters["submitted"] == 0
    [record] = db.query(GpuUsageRecord).all()
    assert record.status == GpuUsageRecord.STATUS_PENDING


def test_run_cycle_submits_and_reconciles(db, make_project, make_user, make_project_user):
    usage = FakeUsageClient()
    service = _cycle_service(db, make_project, make_user, make_project_user, usage)

    counters = service.run_cycle(db)

    assert counters["submitted"] == 1
    assert len(usage.posts) == 1
    [record] = db.query(GpuUsageRecord).all()
    assert record.status == GpuUsageRecord.STATUS_SUBMITTED
