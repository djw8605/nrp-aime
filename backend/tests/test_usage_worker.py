"""Tests for the usage worker cycle wiring."""

from workers import usage_worker


class _FakeService:
    def __init__(self, result=None, error=None):
        self.result = result or {"submitted": 2}
        self.error = error

    def run_cycle(self, db):
        if self.error:
            raise self.error
        return self.result


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


class _NullSession:
    def __enter__(self):
        return object()

    def __exit__(self, *exc):
        return False
