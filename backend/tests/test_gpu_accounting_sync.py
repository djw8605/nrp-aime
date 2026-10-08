"""Tests for syncing NRP accounting rows into the GPU usage ledger."""

import hashlib
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.models.gpu_usage_record import GpuUsageRecord
from app.services.gpu_accounting.service import PI_LOGIN_MISSING, GpuAccountingService
from app.services.nrp_accounting.client import NrpAccountingApiError
from tests.gpu_accounting_support import (
    FakeAccountingClient,
    FakeUsageClient,
    gpu_project,
    usage_row,
)

ALICE = "http://cilogon.org/serverE/users/1001"
SA = "system:serviceaccount:ns-gpu:runner"
LATEST = date(2026, 10, 7)


def _service(rows):
    accounting = FakeAccountingClient(LATEST, rows)
    return GpuAccountingService(accounting_client=accounting, usage_client=FakeUsageClient()), accounting


def _records(db):
    return db.query(GpuUsageRecord).order_by(GpuUsageRecord.usage_date, GpuUsageRecord.username).all()


def _add_alice(db, make_user, make_project_user, project):
    alice = make_user(db, remote_site_login=ALICE)
    make_project_user(db, project, alice, remote_site_login="alice_nrp")


def _add_pi(db, make_user, make_project_user, project, login="pi_nrp"):
    pi = make_user(db)
    make_project_user(db, project, pi, role="pi", remote_site_login=login)
    db.refresh(project)


def test_member_usage_creates_pending_record(db, make_project, make_user, make_project_user):
    project = gpu_project(db, make_project)
    _add_alice(db, make_user, make_project_user, project)
    service, _ = _service([usage_row(ALICE, date(2026, 10, 2), "2.5")])

    counters = service.sync_ledger(db)

    [record] = _records(db)
    assert record.username == "alice_nrp"
    assert record.attribution == GpuUsageRecord.ATTRIBUTION_MEMBER
    assert record.gpu_hours == Decimal("2.5")
    assert record.charge == Decimal("2.5")
    assert record.status == GpuUsageRecord.STATUS_PENDING
    expected_hash = hashlib.sha256(b"alice_nrp").hexdigest()[:12]
    assert record.local_record_id == f"nrp-gpu-p.gpu1-20261002-{expected_hash}"
    assert project.gpu_usage_synced_through == LATEST
    assert counters == {"projects": 1, "rows": 1, "dropped": 0, "records_changed": 1}


def test_non_member_person_is_dropped(db, make_project, make_user):
    gpu_project(db, make_project)
    make_user(db, remote_site_login=ALICE)
    service, _ = _service([usage_row(ALICE, date(2026, 10, 2), "2.5")])

    counters = service.sync_ledger(db)

    assert _records(db) == []
    assert counters["dropped"] == 1


def test_service_accounts_summed_onto_pi(db, make_project, make_user, make_project_user):
    project = gpu_project(db, make_project)
    _add_pi(db, make_user, make_project_user, project)
    service, _ = _service([
        usage_row(SA, date(2026, 10, 2), "1.25"),
        usage_row("system:serviceaccount:ns-gpu:other", date(2026, 10, 2), "0.75"),
    ])

    service.sync_ledger(db)

    [record] = _records(db)
    assert record.username == "pi_nrp"
    assert record.attribution == GpuUsageRecord.ATTRIBUTION_PI
    assert record.gpu_hours == Decimal("2.0")


def test_pi_without_login_is_pending_and_holds_watermark(db, make_project, make_user, make_project_user):
    project = gpu_project(db, make_project)
    _add_pi(db, make_user, make_project_user, project, login=None)
    service, _ = _service([usage_row(SA, date(2026, 10, 2), "3")])

    service.sync_ledger(db)

    [record] = _records(db)
    assert record.username == ""
    assert record.status == GpuUsageRecord.STATUS_PENDING
    assert record.last_error == PI_LOGIN_MISSING
    # Watermark is held at min(latest, 2026-10-02 + 7 days) so the next fetch
    # (watermark - 7 days, clipped to the project start) re-reads 2026-10-02.
    assert project.gpu_usage_synced_through == date(2026, 10, 7)
    service.accounting.latest = date(2026, 10, 20)
    service.sync_ledger(db)
    assert service.accounting.calls[-1][1] <= date(2026, 10, 2)
    assert project.gpu_usage_synced_through == date(2026, 10, 9)


def test_pending_pi_row_replaced_once_pi_has_login(db, make_project, make_user, make_project_user):
    project = gpu_project(db, make_project)
    _add_pi(db, make_user, make_project_user, project, login=None)
    service, _ = _service([usage_row(SA, date(2026, 10, 2), "3")])
    service.sync_ledger(db)

    project.project_users[0].remote_site_login = "pi_nrp"
    db.commit()
    service.sync_ledger(db)

    [record] = _records(db)
    assert record.username == "pi_nrp"
    assert record.last_error is None


def test_non_gpu_and_debug_projects_are_not_queried(db, make_project):
    gpu_project(db, make_project)
    gpu_project(db, make_project, kubernetes_namespace="ns-debug", site_project_id="p.dbg", tags=["debug"])
    make_project(db, allocated_resource="nrp-classroom.access-ci.org", site_project_id="p.cls", kubernetes_namespace="ns-cls")
    service, accounting = _service([])

    service.sync_ledger(db)

    assert accounting.calls == [(["ns-gpu"], date(2026, 10, 1), LATEST)]


def test_rows_outside_project_window_are_ignored(db, make_project, make_user, make_project_user):
    project = gpu_project(db, make_project, start_date=date(2026, 10, 3), end_date=date(2026, 10, 5))
    _add_alice(db, make_user, make_project_user, project)
    service, _ = _service([
        usage_row(ALICE, date(2026, 10, 2), "1"),
        usage_row(ALICE, date(2026, 10, 4), "1"),
        usage_row(ALICE, date(2026, 10, 6), "1"),
    ])

    service.sync_ledger(db)

    assert [r.usage_date for r in _records(db)] == [date(2026, 10, 4)]


def test_fetch_starts_at_watermark_minus_restatement(db, make_project):
    gpu_project(db, make_project, start_date=date(2026, 9, 1), gpu_usage_synced_through=date(2026, 10, 6))
    service, accounting = _service([])

    service.sync_ledger(db)

    assert accounting.calls == [(["ns-gpu"], date(2026, 9, 29), LATEST)]


def test_rerun_is_idempotent_and_restatement_resets_status(db, make_project, make_user, make_project_user):
    project = gpu_project(db, make_project)
    _add_alice(db, make_user, make_project_user, project)
    service, accounting = _service([usage_row(ALICE, date(2026, 10, 2), "2.5")])
    service.sync_ledger(db)
    [record] = _records(db)
    record.status = GpuUsageRecord.STATUS_SUBMITTED
    record.submitted_charge = Decimal("2.5")
    db.commit()

    assert service.sync_ledger(db)["records_changed"] == 0
    assert record.status == GpuUsageRecord.STATUS_SUBMITTED

    accounting.rows = [usage_row(ALICE, date(2026, 10, 2), "3.0")]
    assert service.sync_ledger(db)["records_changed"] == 1
    assert record.status == GpuUsageRecord.STATUS_PENDING
    assert record.gpu_hours == Decimal("3.0")


def test_vanished_usage_deletes_unsent_and_zeroes_sent(db, make_project, make_user, make_project_user):
    project = gpu_project(db, make_project)
    _add_alice(db, make_user, make_project_user, project)
    service, accounting = _service([
        usage_row(ALICE, date(2026, 10, 2), "1"),
        usage_row(ALICE, date(2026, 10, 3), "1"),
    ])
    service.sync_ledger(db)
    sent = next(r for r in _records(db) if r.usage_date == date(2026, 10, 3))
    sent.status = GpuUsageRecord.STATUS_LOADED
    sent.submitted_charge = Decimal("1")
    db.commit()

    accounting.rows = []
    service.sync_ledger(db)

    [remaining] = _records(db)
    assert remaining.usage_date == date(2026, 10, 3)
    assert remaining.gpu_hours == Decimal("0")
    assert remaining.status == GpuUsageRecord.STATUS_PENDING


def _records_for(db, project):
    return db.query(GpuUsageRecord).filter(GpuUsageRecord.project_id == project.id).all()


LOW_ID = uuid.UUID("a0000000-0000-0000-0000-000000000001")
HIGH_ID = uuid.UUID("b0000000-0000-0000-0000-000000000002")


def _add_sent_record(db, project, day, hours="2.5"):
    db.add(
        GpuUsageRecord(
            project_id=project.id,
            usage_date=day,
            username="alice_nrp",
            attribution=GpuUsageRecord.ATTRIBUTION_MEMBER,
            gpu_hours=Decimal(hours),
            charge=Decimal(hours),
            submitted_charge=Decimal(hours),
            local_record_id=GpuAccountingService.local_record_id(project, day, "alice_nrp"),
            status=GpuUsageRecord.STATUS_LOADED,
            attempts=1,
        )
    )


def _snapshot(db):
    return [(str(r.project_id), r.usage_date, r.status, r.gpu_hours) for r in _records(db)]


@pytest.mark.parametrize("holder_has_lower_id", [True, False])
def test_shared_namespace_row_stays_with_project_that_reported_it(
    db, make_project, make_user, make_project_user, holder_has_lower_id
):
    holder_id, new_id = (LOW_ID, HIGH_ID) if holder_has_lower_id else (HIGH_ID, LOW_ID)
    holder = gpu_project(
        db, make_project, id=holder_id, site_project_id="p.holder", gpu_usage_synced_through=date(2026, 10, 20)
    )
    new = gpu_project(db, make_project, id=new_id, site_project_id="p.new")
    alice = make_user(db, remote_site_login=ALICE)
    for project in (holder, new):
        make_project_user(db, project, alice, remote_site_login="alice_nrp")
    _add_sent_record(db, holder, date(2026, 10, 2))
    db.commit()
    service, accounting = _service([usage_row(ALICE, date(2026, 10, 2), "2.5")])
    accounting.latest = date(2026, 10, 20)

    service.sync_ledger(db)

    assert _records_for(db, new) == []
    [record] = _records_for(db, holder)
    assert record.status == GpuUsageRecord.STATUS_LOADED
    assert record.gpu_hours == Decimal("2.5")
    first = _snapshot(db)

    service.sync_ledger(db)
    assert _snapshot(db) == first


def test_shared_namespace_handoff_keeps_reported_dates_with_original_project(
    db, make_project, make_user, make_project_user
):
    project_a = gpu_project(
        db, make_project, id=HIGH_ID, site_project_id="p.a", gpu_usage_synced_through=date(2026, 10, 20)
    )
    project_b = gpu_project(db, make_project, id=LOW_ID, site_project_id="p.b", start_date=date(2026, 10, 10))
    alice = make_user(db, remote_site_login=ALICE)
    for project in (project_a, project_b):
        make_project_user(db, project, alice, remote_site_login="alice_nrp")
    for day in (10, 11, 12):
        _add_sent_record(db, project_a, date(2026, 10, day))
    db.commit()
    service, accounting = _service([
        usage_row(ALICE, date(2026, 10, 11), "2.5"),
        usage_row(ALICE, date(2026, 10, 15), "1"),
    ])
    accounting.latest = date(2026, 10, 20)

    service.sync_ledger(db)

    assert [r.usage_date for r in _records_for(db, project_a)] == [
        date(2026, 10, 10), date(2026, 10, 11), date(2026, 10, 12)
    ]
    assert [r.usage_date for r in _records_for(db, project_b)] == [date(2026, 10, 15)]
    first = _snapshot(db)

    service.sync_ledger(db)
    assert _snapshot(db) == first


def test_shared_namespace_later_start_owns_its_dates(db, make_project, make_user, make_project_user):
    project_a = gpu_project(db, make_project, site_project_id="p.a", gpu_usage_synced_through=date(2026, 10, 20))
    project_b = gpu_project(db, make_project, site_project_id="p.b", start_date=date(2026, 10, 10))
    alice = make_user(db, remote_site_login=ALICE)
    for project in (project_a, project_b):
        make_project_user(db, project, alice, remote_site_login="alice_nrp")
    db.commit()
    service, accounting = _service([
        usage_row(ALICE, date(2026, 10, 5), "1"),
        usage_row(ALICE, date(2026, 10, 12), "2"),
    ])
    accounting.latest = date(2026, 10, 20)

    service.sync_ledger(db)

    assert [r.usage_date for r in _records_for(db, project_b)] == [date(2026, 10, 12)]
    # 2026-10-05 belongs to A but is outside A's fetch range (10-13..): skipped, not given to B.
    assert _records_for(db, project_a) == []


def test_duplicate_site_project_id_excludes_both_projects(
    db, make_project, make_user, make_project_user, caplog
):
    first = gpu_project(db, make_project, site_project_id="p.dup", kubernetes_namespace="ns-a")
    second = gpu_project(db, make_project, site_project_id="p.dup", kubernetes_namespace="ns-b")
    other = gpu_project(db, make_project, site_project_id="p.ok", kubernetes_namespace="ns-ok")
    alice = make_user(db, remote_site_login=ALICE)
    for project in (first, second, other):
        make_project_user(db, project, alice, remote_site_login="alice_nrp")
    service, accounting = _service([
        usage_row(ALICE, date(2026, 10, 2), "1", namespace="ns-a"),
        usage_row(ALICE, date(2026, 10, 2), "2", namespace="ns-b"),
        usage_row(ALICE, date(2026, 10, 2), "3", namespace="ns-ok"),
    ])

    with caplog.at_level("ERROR"):
        counters = service.sync_ledger(db)

    assert _records_for(db, first) == []
    assert _records_for(db, second) == []
    assert [r.gpu_hours for r in _records_for(db, other)] == [Decimal("3")]
    assert first.gpu_usage_synced_through is None
    assert second.gpu_usage_synced_through is None
    assert counters["projects"] == 1
    assert accounting.calls == [(["ns-ok"], date(2026, 10, 1), LATEST)]
    message = " ".join(r.getMessage() for r in caplog.records if r.levelname == "ERROR")
    assert "p.dup" in message
    assert str(first.id) in message and str(second.id) in message


def test_shared_namespace_holder_keeps_dates_outside_its_new_window(
    db, make_project, make_user, make_project_user
):
    # project_a reported 10-05 earlier; its start date has since moved to 10-10.
    project_a = gpu_project(db, make_project, id=HIGH_ID, site_project_id="p.a", start_date=date(2026, 10, 10))
    project_b = gpu_project(db, make_project, id=LOW_ID, site_project_id="p.b", start_date=date(2026, 10, 1))
    alice = make_user(db, remote_site_login=ALICE)
    for project in (project_a, project_b):
        make_project_user(db, project, alice, remote_site_login="alice_nrp")
    _add_sent_record(db, project_a, date(2026, 10, 5))
    db.commit()
    service, accounting = _service([usage_row(ALICE, date(2026, 10, 5), "2.5")])
    accounting.latest = date(2026, 10, 20)

    service.sync_ledger(db)

    assert _records_for(db, project_b) == []
    [record] = _records_for(db, project_a)
    assert record.usage_date == date(2026, 10, 5)
    assert record.status == GpuUsageRecord.STATUS_LOADED


def test_shared_namespace_holder_keeps_dates_after_its_new_end(
    db, make_project, make_user, make_project_user
):
    # project_a reported 10-12 earlier; its end date has since moved to 10-08.
    project_a = gpu_project(
        db, make_project, id=HIGH_ID, site_project_id="p.a", start_date=date(2026, 10, 6), end_date=date(2026, 10, 8)
    )
    project_b = gpu_project(db, make_project, id=LOW_ID, site_project_id="p.b", start_date=date(2026, 10, 1))
    alice = make_user(db, remote_site_login=ALICE)
    for project in (project_a, project_b):
        make_project_user(db, project, alice, remote_site_login="alice_nrp")
    _add_sent_record(db, project_a, date(2026, 10, 12))
    db.commit()
    service, accounting = _service([usage_row(ALICE, date(2026, 10, 12), "2.5")])
    accounting.latest = date(2026, 10, 20)

    service.sync_ledger(db)

    assert _records_for(db, project_b) == []
    [record] = _records_for(db, project_a)
    assert record.usage_date == date(2026, 10, 12)
    assert record.gpu_hours == Decimal("2.5")


def test_accounting_api_failure_leaves_ledger_untouched(db, make_project, make_user, make_project_user):
    project = gpu_project(db, make_project, gpu_usage_synced_through=date(2026, 10, 3))
    _add_alice(db, make_user, make_project_user, project)
    _add_sent_record(db, project, date(2026, 10, 2))
    db.commit()
    service, accounting = _service([])
    accounting.gpu_usage_error = NrpAccountingApiError("query_resource_usage failed: 502")

    with pytest.raises(NrpAccountingApiError):
        service.sync_ledger(db)
    db.rollback()

    [record] = _records(db)
    assert record.gpu_hours == Decimal("2.5")
    assert record.status == GpuUsageRecord.STATUS_LOADED
    db.refresh(project)
    assert project.gpu_usage_synced_through == date(2026, 10, 3)


@pytest.mark.parametrize(
    ("old_row_sent", "expected_dates"),
    [
        (True, [date(2026, 10, 3)]),
        (False, [date(2026, 10, 2), date(2026, 10, 3)]),
    ],
)
def test_dates_reported_by_out_of_scope_project_are_not_reported_again(
    db, make_project, make_user, make_project_user, old_row_sent, expected_dates
):
    old = gpu_project(db, make_project, site_project_id="p.old")
    new = gpu_project(db, make_project, site_project_id="p.new")
    alice = make_user(db, remote_site_login=ALICE)
    make_project_user(db, new, alice, remote_site_login="alice_nrp")
    _add_sent_record(db, old, date(2026, 10, 2))
    if not old_row_sent:
        [row] = _records_for(db, old)
        row.submitted_charge = None
        row.status = GpuUsageRecord.STATUS_PENDING
    old.tags = ["debug"]  # leaves GPU export scope after (maybe) reporting
    db.commit()
    service, _ = _service([
        usage_row(ALICE, date(2026, 10, 2), "2.5"),
        usage_row(ALICE, date(2026, 10, 3), "1"),
    ])

    service.sync_ledger(db)

    assert [r.usage_date for r in _records_for(db, new)] == expected_dates
    assert [r.usage_date for r in _records_for(db, old)] == [date(2026, 10, 2)]
    first = _snapshot(db)

    service.sync_ledger(db)
    assert _snapshot(db) == first
