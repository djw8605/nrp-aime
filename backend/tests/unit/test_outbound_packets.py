"""
Unit tests for app/services/outbound_packets.py – OutboundPacketService.

Tests the full outbound packet state machine:
  pending → sent → acked
  pending → retrying (x N) → locked
  safe_mark_failed edge cases
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from app.models.outbound_packet_log import OutboundPacketLog
from app.services.outbound_packets import OutboundPacketService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _new_row(db, *, event_type="notify_account_create", project_user_id=None, **kwargs):
    """Create and flush a fresh OutboundPacketLog row."""
    from app.config import settings

    pu_id = project_user_id or uuid.uuid4()
    row = OutboundPacketLog(
        event_type=event_type,
        status=OutboundPacketLog.STATUS_PENDING,
        ack_status=OutboundPacketLog.ACK_UNKNOWN,
        source_packet_rec_id=kwargs.get("source_packet_rec_id", 1001),
        project_user_id=pu_id,
        payload=kwargs.get("payload", {}),
        max_retries=settings.amie_packet_reprocess_max_retries,
    )
    db.add(row)
    db.flush()
    return row


def _make_send_result(packet_rec_id=9999):
    """Simulate what amieclient.send_packet() returns."""

    class _FakeResult:
        def as_dict(self):
            return {"header": {"packet_rec_id": packet_rec_id}}

    return _FakeResult()


# ===========================================================================
# start_or_resume
# ===========================================================================

class TestStartOrResume:
    def test_creates_new_row_on_first_call(self, db):
        pu_id = uuid.uuid4()
        row = OutboundPacketService.start_or_resume(
            db,
            event_type="notify_account_create",
            project_user_id=pu_id,
            source_packet_rec_id=1001,
            payload={"key": "value"},
        )
        assert row.status == OutboundPacketLog.STATUS_PENDING
        assert row.ack_status == OutboundPacketLog.ACK_UNKNOWN
        assert row.project_user_id == pu_id
        assert row.payload == {"key": "value"}

    def test_returns_existing_pending_row(self, db):
        pu_id = uuid.uuid4()
        row1 = OutboundPacketService.start_or_resume(
            db, event_type="notify_account_create", project_user_id=pu_id
        )
        row2 = OutboundPacketService.start_or_resume(
            db, event_type="notify_account_create", project_user_id=pu_id
        )
        assert row1.id == row2.id

    def test_returns_existing_retrying_row(self, db):
        pu_id = uuid.uuid4()
        row = OutboundPacketService.start_or_resume(
            db, event_type="notify_account_create", project_user_id=pu_id
        )
        row.status = OutboundPacketLog.STATUS_RETRYING
        db.flush()

        row2 = OutboundPacketService.start_or_resume(
            db, event_type="notify_account_create", project_user_id=pu_id
        )
        assert row2.id == row.id

    def test_returns_existing_locked_row(self, db):
        pu_id = uuid.uuid4()
        row = OutboundPacketService.start_or_resume(
            db, event_type="notify_account_create", project_user_id=pu_id
        )
        row.status = OutboundPacketLog.STATUS_LOCKED
        db.flush()

        row2 = OutboundPacketService.start_or_resume(
            db, event_type="notify_account_create", project_user_id=pu_id
        )
        assert row2.id == row.id

    def test_creates_new_row_for_different_event_type(self, db):
        pu_id = uuid.uuid4()
        row1 = OutboundPacketService.start_or_resume(
            db, event_type="notify_account_create", project_user_id=pu_id
        )
        row2 = OutboundPacketService.start_or_resume(
            db, event_type="notify_project_create", project_user_id=pu_id
        )
        assert row1.id != row2.id

    def test_payload_updated_on_resume(self, db):
        pu_id = uuid.uuid4()
        OutboundPacketService.start_or_resume(
            db, event_type="notify_account_create", project_user_id=pu_id,
            payload={"v": 1},
        )
        row = OutboundPacketService.start_or_resume(
            db, event_type="notify_account_create", project_user_id=pu_id,
            payload={"v": 2},
        )
        assert row.payload == {"v": 2}

    def test_no_project_user_id_always_creates_new(self, db):
        row1 = OutboundPacketService.start_or_resume(
            db, event_type="notify_account_create", project_user_id=None
        )
        row2 = OutboundPacketService.start_or_resume(
            db, event_type="notify_account_create", project_user_id=None
        )
        assert row1.id != row2.id


# ===========================================================================
# mark_sent
# ===========================================================================

class TestMarkSent:
    def test_sets_status_sent(self, db):
        row = _new_row(db)
        OutboundPacketService.mark_sent(db, row, send_result=_make_send_result())
        assert row.status == OutboundPacketLog.STATUS_SENT

    def test_sets_sent_at(self, db):
        row = _new_row(db)
        OutboundPacketService.mark_sent(db, row, send_result=_make_send_result())
        assert row.sent_at is not None

    def test_sets_outbound_packet_rec_id_from_result(self, db):
        row = _new_row(db)
        OutboundPacketService.mark_sent(db, row, send_result=_make_send_result(7777))
        assert row.outbound_packet_rec_id == 7777

    def test_clears_last_error(self, db):
        row = _new_row(db)
        row.last_error = "previous error"
        OutboundPacketService.mark_sent(db, row, send_result=_make_send_result())
        assert row.last_error is None

    def test_clears_locked_until(self, db):
        row = _new_row(db)
        row.locked_until = datetime.now(UTC) + timedelta(hours=1)
        OutboundPacketService.mark_sent(db, row, send_result=_make_send_result())
        assert row.locked_until is None

    def test_no_packet_rec_id_in_result_gives_ack_unknown(self, db):
        row = _new_row(db)

        class _NoIdResult:
            def as_dict(self):
                return {"header": {}}

        OutboundPacketService.mark_sent(db, row, send_result=_NoIdResult())
        assert row.ack_status == OutboundPacketLog.ACK_UNKNOWN


# ===========================================================================
# mark_failed / is_locked
# ===========================================================================

class TestMarkFailed:
    def test_increments_retry_count(self, db):
        row = _new_row(db)
        assert row.retry_count == 0
        OutboundPacketService.mark_failed(db, row, error_message="boom")
        assert row.retry_count == 1

    def test_below_max_retries_sets_retrying(self, db):
        row = _new_row(db)
        row.max_retries = 5
        OutboundPacketService.mark_failed(db, row, error_message="err")
        assert row.status == OutboundPacketLog.STATUS_RETRYING

    def test_at_max_retries_sets_locked(self, db):
        row = _new_row(db)
        row.max_retries = 1
        OutboundPacketService.mark_failed(db, row, error_message="err")
        assert row.status == OutboundPacketLog.STATUS_LOCKED
        assert row.locked_until is not None

    def test_locked_sets_next_retry_at(self, db):
        row = _new_row(db)
        row.max_retries = 1
        OutboundPacketService.mark_failed(db, row, error_message="err")
        assert row.next_retry_at is not None

    def test_records_last_error(self, db):
        row = _new_row(db)
        OutboundPacketService.mark_failed(db, row, error_message="connection timeout")
        assert row.last_error == "connection timeout"

    def test_retrying_sets_next_retry_at(self, db):
        row = _new_row(db)
        row.max_retries = 10
        OutboundPacketService.mark_failed(db, row, error_message="err")
        assert row.next_retry_at is not None
        assert row.locked_until is None

    def test_multiple_failures_accumulate(self, db):
        row = _new_row(db)
        row.max_retries = 5
        for _ in range(3):
            OutboundPacketService.mark_failed(db, row, error_message="err")
        assert row.retry_count == 3
        assert row.status == OutboundPacketLog.STATUS_RETRYING


class TestIsLocked:
    def test_locked_when_locked_until_in_future(self, db):
        row = _new_row(db)
        row.locked_until = datetime.now(UTC) + timedelta(hours=1)
        assert OutboundPacketService.is_locked(row) is True

    def test_not_locked_when_locked_until_in_past(self, db):
        row = _new_row(db)
        row.locked_until = datetime.now(UTC) - timedelta(seconds=1)
        assert OutboundPacketService.is_locked(row) is False

    def test_not_locked_when_no_locked_until(self, db):
        row = _new_row(db)
        assert OutboundPacketService.is_locked(row) is False


# ===========================================================================
# mark_acked
# ===========================================================================

class TestMarkAcked:
    def test_mark_acked_true(self, db):
        row = _new_row(db)
        OutboundPacketService.mark_acked(db, row, acked=True)
        assert row.ack_status == OutboundPacketLog.ACK_ACKED
        assert row.acked_at is not None

    def test_mark_acked_false(self, db):
        row = _new_row(db)
        OutboundPacketService.mark_acked(db, row, acked=False)
        assert row.ack_status == OutboundPacketLog.ACK_NOT_ACKED
        assert row.acked_at is None


# ===========================================================================
# safe_mark_failed
# ===========================================================================

class TestSafeMarkFailed:
    def test_creates_row_when_none(self, db):
        pu_id = uuid.uuid4()
        OutboundPacketService.safe_mark_failed(
            db,
            row=None,
            event_type="notify_account_create",
            error_message="oops",
            project_user_id=pu_id,
        )
        db.flush()
        rows = db.query(OutboundPacketLog).filter(
            OutboundPacketLog.project_user_id == pu_id
        ).all()
        assert len(rows) == 1
        assert rows[0].status == OutboundPacketLog.STATUS_FAILED

    def test_updates_existing_row(self, db):
        row = _new_row(db)
        OutboundPacketService.safe_mark_failed(
            db,
            row=row,
            event_type="notify_account_create",
            error_message="updated error",
        )
        assert row.last_error == "updated error"
        assert row.retry_count == 1

    def test_handles_db_exception_gracefully(self, db):
        """safe_mark_failed must not propagate exceptions from the DB layer."""
        with patch.object(
            OutboundPacketService, "mark_failed", side_effect=RuntimeError("db crash")
        ):
            # Should not raise
            OutboundPacketService.safe_mark_failed(
                db,
                row=_new_row(db),
                event_type="notify_account_create",
                error_message="err",
            )


# ===========================================================================
# Full state machine flow
# ===========================================================================

class TestStateMachineFlow:
    def test_pending_to_sent_to_acked(self, db):
        pu_id = uuid.uuid4()
        row = OutboundPacketService.start_or_resume(
            db, event_type="notify_account_create", project_user_id=pu_id
        )
        assert row.status == OutboundPacketLog.STATUS_PENDING

        OutboundPacketService.mark_sent(db, row, send_result=_make_send_result())
        assert row.status == OutboundPacketLog.STATUS_SENT

        OutboundPacketService.mark_acked(db, row, acked=True)
        assert row.ack_status == OutboundPacketLog.ACK_ACKED

    def test_pending_retrying_then_locked(self, db):
        from app.config import settings

        pu_id = uuid.uuid4()
        row = OutboundPacketService.start_or_resume(
            db, event_type="notify_account_create", project_user_id=pu_id
        )
        row.max_retries = 3

        for i in range(2):
            OutboundPacketService.mark_failed(db, row, error_message=f"err-{i}")
            assert row.status == OutboundPacketLog.STATUS_RETRYING

        OutboundPacketService.mark_failed(db, row, error_message="final")
        assert row.status == OutboundPacketLog.STATUS_LOCKED
        assert OutboundPacketService.is_locked(row) is True
