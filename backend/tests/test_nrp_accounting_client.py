"""Tests for the NRP accounting public API client."""

import json
from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.services.nrp_accounting import client as client_module
from app.services.nrp_accounting.client import (
    GpuUsageRow,
    NrpAccountingApiError,
    NrpAccountingClient,
)

BASE = "https://accounting.test/openapi"


def _client(handler):
    return NrpAccountingClient(base_url=BASE, transport=httpx.MockTransport(handler))


def test_latest_data_date():
    def handler(request):
        assert request.method == "POST"
        assert str(request.url) == f"{BASE}/get_latest_data_date"
        return httpx.Response(200, json={"granularity": "namespace", "latest_data_date": "2026-10-07"})

    assert _client(handler).latest_data_date() == date(2026, 10, 7)


def test_gpu_usage_request_shape_and_parsing():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "row_count": 1,
                "rows": [
                    {
                        "date": "2026-10-07",
                        "namespace": "ns-a",
                        "created_by": "http://cilogon.org/serverE/users/1",
                        "usage": 24.083333,
                    }
                ],
            },
        )

    rows = _client(handler).gpu_usage(["ns-b", "ns-a"], date(2026, 10, 1), date(2026, 10, 7))

    assert seen == [
        {
            "start_date": "2026-10-01",
            "end_date": "2026-10-07",
            "namespace": ["ns-a", "ns-b"],
            "resource": "gpu",
            "group_by": ["date", "namespace", "created_by"],
            "limit": 5000,
        }
    ]
    assert rows == [
        GpuUsageRow(
            namespace="ns-a",
            created_by="http://cilogon.org/serverE/users/1",
            date=date(2026, 10, 7),
            gpu_hours=Decimal("24.083333"),
        )
    ]


def test_gpu_usage_empty_inputs_skip_request():
    def handler(request):  # pragma: no cover - must not be called
        raise AssertionError("no request expected")

    client = _client(handler)
    assert client.gpu_usage([], date(2026, 10, 1), date(2026, 10, 7)) == []
    assert client.gpu_usage(["ns"], date(2026, 10, 8), date(2026, 10, 7)) == []


def test_gpu_usage_bisects_date_range_when_row_cap_hit(monkeypatch):
    monkeypatch.setattr(client_module, "MAX_ROWS_PER_QUERY", 2)
    ranges = []

    def handler(request):
        body = json.loads(request.content)
        ranges.append((body["start_date"], body["end_date"]))
        if body["start_date"] != body["end_date"]:
            rows = [{"date": body["start_date"], "namespace": "ns", "created_by": "x", "usage": 1}] * 2
        else:
            rows = [{"date": body["start_date"], "namespace": "ns", "created_by": "x", "usage": 1}]
        return httpx.Response(200, json={"rows": rows})

    rows = _client(handler).gpu_usage(["ns"], date(2026, 10, 1), date(2026, 10, 2))

    assert ranges == [
        ("2026-10-01", "2026-10-02"),
        ("2026-10-01", "2026-10-01"),
        ("2026-10-02", "2026-10-02"),
    ]
    assert [r.date for r in rows] == [date(2026, 10, 1), date(2026, 10, 2)]


def test_gpu_usage_http_error_raises():
    def handler(request):
        return httpx.Response(502, text="bad gateway")

    with pytest.raises(NrpAccountingApiError):
        _client(handler).gpu_usage(["ns"], date(2026, 10, 1), date(2026, 10, 1))


def test_gpu_usage_malformed_row_raises():
    def handler(request):
        return httpx.Response(200, json={"rows": [{"namespace": "ns"}]})

    with pytest.raises(NrpAccountingApiError):
        _client(handler).gpu_usage(["ns"], date(2026, 10, 1), date(2026, 10, 1))
