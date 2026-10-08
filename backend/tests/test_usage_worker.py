"""Tests for the usage worker cycle wiring."""


import pytest

from workers import usage_worker


class _FakeService:
    def __init__(self, result=None, error=None, disabled_reason=None):
        self.result = result or {"submitted": 2}
        self.error = error
        self.disabled_reason = disabled_reason

    def run_cycle(self, db):
        if self.error:
            raise self.error
        return self.result

    def submission_disabled_reason(self):
        return self.disabled_reason


def test_run_once_records_success(monkeypatch):
    statuses = []
    monkeypatch.setattr(usage_worker, "_update_worker_status", lambda **kw: statuses.append(kw))
    monkeypatch.setattr(usage_worker, "_evaluate_alerts", lambda: None)
    monkeypatch.setattr(usage_worker, "SessionLocal", _NullSession)

    result = usage_worker.run_once(_FakeService())

    assert result == {"submitted": 2}
    assert statuses[0]["current_state"] == "collecting_gpu_usage"
    assert statuses[-1]["current_state"] == "idle"
    assert statuses[-1]["mark_success"] is True
    assert statuses[-1]["state_payload"]["submitted"] == 2
    assert "last_successful_usage_export_at" in statuses[-1]["state_payload"]


def _patch_worker(monkeypatch):
    statuses = []
    monkeypatch.setattr(usage_worker, "_update_worker_status", lambda **kw: statuses.append(kw))
    monkeypatch.setattr(usage_worker, "_evaluate_alerts", lambda: None)
    monkeypatch.setattr(usage_worker, "SessionLocal", _NullSession)
    return statuses


def test_run_once_without_submission_keeps_export_freshness(monkeypatch):
    statuses = _patch_worker(monkeypatch)
    reason = "AMIE_USAGE_SUBMIT_ENABLED is false (dry run)"

    usage_worker.run_once(_FakeService(result={"rows": 3}, disabled_reason=reason))

    final = statuses[-1]
    assert final["current_state"] == "idle"
    assert final["mark_success"] is True
    assert "last_successful_usage_export_at" not in final["state_payload"]
    assert final["state_payload"]["rows"] == 3
    assert "submission is disabled" in final["status_message"]
    assert reason in final["status_message"]


def test_run_once_propagates_cycle_error_without_idle_status(monkeypatch):
    statuses = _patch_worker(monkeypatch)

    with pytest.raises(RuntimeError, match="accounting down"):
        usage_worker.run_once(_FakeService(error=RuntimeError("accounting down")))

    assert [s["current_state"] for s in statuses] == ["collecting_gpu_usage"]


class _NullSession:
    def __enter__(self):
        return object()

    def __exit__(self, *exc):
        return False
