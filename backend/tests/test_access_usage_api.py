"""Tests for the ACCESS Usage API adapter over amieclient.UsageClient."""

import json
from datetime import UTC, datetime

import pytest
import requests
from amieclient.usage import (
    ComputeUsageRecord,
    UsageLoaded,
    UsageLoadedRecord,
    UsageRecordError,
    UsageResponse,
    UsageResponseError,
    UsageStatus,
)

from app.services.aime.usage_api import (
    AccessUsageApiClient,
    UsageApiError,
    iso_utc,
)


def _compute(local_record_id="r1"):
    return ComputeUsageRecord(
        username="alice_nrp",
        local_project_id="p.gpu1",
        local_record_id=local_record_id,
        resource="pnrp.sdsc.access-ci.org",
        submit_time="2026-10-02T00:00:00Z",
        start_time="2026-10-02T00:00:00Z",
        end_time="2026-10-03T00:00:00Z",
        charge="2.500000",
        node_count=1,
        queue="gpu",
        job_name="nrp-gpu-daily",
    )


class _FakeUsageClient:
    """Stands in for amieclient.UsageClient; records calls."""

    instances = []

    def __init__(self, site_name, api_key, usage_url):
        self.kwargs = {"site_name": site_name, "api_key": api_key, "usage_url": usage_url}
        self.sent = []
        self.loaded_calls = []
        self.send_result = [UsageResponse(message="queued", failed_records=[])]
        self.send_error = None
        self.pages = []
        self.status_result = UsageStatus(resources=[])
        _FakeUsageClient.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def send(self, records):
        if self.send_error:
            raise self.send_error
        self.sent.append(records)
        return self.send_result

    def loaded(self, min_loaded_time=None, limit=None, offset=None, local_record_id=None):
        self.loaded_calls.append((min_loaded_time, limit, offset))
        return UsageLoaded(records=self.pages.pop(0))

    def status(self, from_time=None, to_time=None):
        return self.status_result


@pytest.fixture()
def fake_factory():
    _FakeUsageClient.instances = []
    configured = {}

    def factory(**kwargs):
        client = _FakeUsageClient(**kwargs)
        for key, value in configured.items():
            setattr(client, key, value)
        return client

    factory.configure = configured
    return factory


def _adapter(factory):
    return AccessUsageApiClient(
        site_name="NRP",
        api_key="secret",
        usage_url="https://usage.test/api/v1",
        client_factory=factory,
    )


def test_iso_utc_formats_z_suffix():
    assert iso_utc(datetime(2026, 10, 7, 1, 2, 3, tzinfo=UTC)) == "2026-10-07T01:02:03Z"


def test_fork_compute_record_has_no_parent_record_id():
    """Guards the fork fix: upstream 0.6.1 sent ParentRecordID: [null]."""
    payload = _compute().as_dict()
    assert "ParentRecordID" not in payload
    assert payload["Attributes"] == {"NodeCount": 1, "JobName": "nrp-gpu-daily", "Queue": "gpu"}


def test_post_compute_returns_validation_failures(fake_factory):
    record = _compute("bad")
    failure = UsageRecordError(error="Unknown user", record=record)
    fake_factory.configure["send_result"] = [UsageResponse(message="0 queued", failed_records=[failure])]

    failures = _adapter(fake_factory).post_compute([_compute("good"), record])

    client = _FakeUsageClient.instances[0]
    assert client.kwargs == {
        "site_name": "NRP",
        "api_key": "secret",
        "usage_url": "https://usage.test/api/v1",
    }
    assert [r.local_record_id for r in client.sent[0]] == ["good", "bad"]
    assert [(f.error, f.record.local_record_id) for f in failures] == [("Unknown user", "bad")]


def test_post_compute_rejects_oversized_batch(fake_factory):
    with pytest.raises(ValueError):
        _adapter(fake_factory).post_compute([_compute(str(i)) for i in range(1001)])


@pytest.mark.parametrize(
    "error",
    [UsageResponseError("Bad XA-SITE"), requests.ConnectionError("down")],
)
def test_post_compute_wraps_errors(fake_factory, error):
    fake_factory.configure["send_error"] = error
    with pytest.raises(UsageApiError):
        _adapter(fake_factory).post_compute([_compute()])


def test_loaded_pages_until_short_page(fake_factory):
    def rec(i):
        return UsageLoadedRecord(
            accounting_db_record_id=str(i),
            local_record_id=f"r{i}",
            resource="pnrp.sdsc.access-ci.org",
            submit_time=None,
            loaded_time=None,
            charge=1,
        )

    fake_factory.configure["pages"] = [[rec(1), rec(2)], [rec(3)]]
    since = datetime(2026, 10, 1, tzinfo=UTC)

    records = _adapter(fake_factory).loaded(since, page_size=2)

    assert [r.local_record_id for r in records] == ["r1", "r2", "r3"]
    assert _FakeUsageClient.instances[0].loaded_calls == [(since, 2, 0), (since, 2, 2)]


def test_status_returns_resources_and_wraps_parse_errors(fake_factory, monkeypatch):
    status = UsageStatus.from_list([
        {
            "Resource": "pnrp.sdsc.access-ci.org",
            "LoadedRecordCount": 1,
            "FailedJobCount": 0,
            "TotalCharge": 2.5,
            "Errors": [],
        }
    ])
    fake_factory.configure["status_result"] = status
    start, end = datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 10, 2, tzinfo=UTC)
    adapter = _adapter(fake_factory)

    assert [r.resource for r in adapter.status(start, end)] == ["pnrp.sdsc.access-ci.org"]

    def broken_status(self, from_time=None, to_time=None):
        raise KeyError("FailedJobCount")

    monkeypatch.setattr(_FakeUsageClient, "status", broken_status)
    with pytest.raises(UsageApiError):
        adapter.status(start, end)


def test_real_usage_client_posts_to_access_with_headers(monkeypatch):
    """End-to-end through the real amieclient UsageClient with a stubbed transport."""
    seen = {}

    def fake_send(session, prepared, **kwargs):
        seen["url"] = prepared.url
        seen["headers"] = dict(prepared.headers)
        seen["body"] = json.loads(prepared.body)
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(
            {"Message": "1 records have been queued for loading.", "ValidationFailedRecords": []}
        ).encode()
        return response

    monkeypatch.setattr(requests.Session, "send", fake_send)
    adapter = AccessUsageApiClient(
        site_name="NRP", api_key="secret", usage_url="https://usage.access-ci.org/api/v1"
    )

    assert adapter.post_compute([_compute()]) == []
    assert seen["url"] == "https://usage.access-ci.org/api/v1/usage/"
    assert seen["headers"]["XA-SITE"] == "NRP"
    assert seen["headers"]["XA-API-KEY"] == "secret"
    assert seen["body"]["UsageType"] == "Compute"
    assert seen["body"]["Records"][0]["LocalRecordID"] == "r1"
    assert "ParentRecordID" not in seen["body"]["Records"][0]
