"""Fakes and helpers for GPU accounting service tests."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal

from amieclient.usage import UsageLoadedRecord, UsageRecordError

from app.services.aime.usage_api import UsageApiError
from app.services.nrp_accounting.client import GpuUsageRow

GPU = "pnrp.sdsc.access-ci.org"


class FakeAccountingClient:
    """In-memory stand-in for NrpAccountingClient."""

    def __init__(self, latest: date, rows: list[GpuUsageRow] | None = None) -> None:
        self.latest = latest
        self.rows = list(rows or [])
        self.calls: list[tuple[list[str], date, date]] = []

    def latest_data_date(self) -> date:
        return self.latest

    def gpu_usage(self, namespaces, date_from, date_to):
        self.calls.append((sorted(namespaces), date_from, date_to))
        return [
            row
            for row in self.rows
            if row.namespace in namespaces and date_from <= row.date <= date_to
        ]


class FakeUsageClient:
    """In-memory stand-in for AccessUsageApiClient (amieclient types in/out)."""

    def __init__(self, api_key: str = "key") -> None:
        self.api_key = api_key
        self.posts: list[list] = []  # batches of ComputeUsageRecord
        self.validation_errors: dict[str, str] = {}  # LocalRecordID -> error
        self.post_error: UsageApiError | None = None
        self.loaded_records: list = []  # UsageLoadedRecord
        self.loaded_calls: list = []  # min_loaded_time per bulk loaded() call
        self.loaded_by_id: dict[str, UsageLoadedRecord] = {}
        self.loaded_record_calls: list[str] = []
        self.loaded_record_error: UsageApiError | None = None
        # UsageStatusResource list, or callable(from_time, to_time) -> list
        self.status_resources: list | Callable = []
        self.status_calls: list = []  # (from_time, to_time)
        self.status_error: UsageApiError | None = None

    def post_compute(self, records):
        if self.post_error is not None:
            raise self.post_error
        self.posts.append(list(records))
        return [
            UsageRecordError(error=self.validation_errors[r.local_record_id], record=r)
            for r in records
            if r.local_record_id in self.validation_errors
        ]

    def loaded(self, min_loaded_time):
        self.loaded_calls.append(min_loaded_time)
        return list(self.loaded_records)

    def loaded_record(self, local_record_id):
        self.loaded_record_calls.append(local_record_id)
        if self.loaded_record_error is not None:
            raise self.loaded_record_error
        return self.loaded_by_id.get(local_record_id)

    def status(self, from_time, to_time):
        self.status_calls.append((from_time, to_time))
        if self.status_error is not None:
            raise self.status_error
        if callable(self.status_resources):
            return list(self.status_resources(from_time, to_time))
        return list(self.status_resources)


def gpu_project(db, make_project, **overrides):
    defaults = {
        "allocated_resource": GPU,
        "site_project_id": "p.gpu1",
        "kubernetes_namespace": "ns-gpu",
        "start_date": date(2026, 10, 1),
    }
    defaults.update(overrides)
    return make_project(db, **defaults)


def usage_row(created_by: str, day: date, hours: str, namespace: str = "ns-gpu") -> GpuUsageRow:
    return GpuUsageRow(
        namespace=namespace,
        created_by=created_by,
        date=day,
        gpu_hours=Decimal(hours),
    )
