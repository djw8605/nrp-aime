"""ACCESS Usage API adapter over ``amieclient.UsageClient``.

amieclient is installed from djw8605/amieclient@1700828 (upstream PR
xsede/amieclient#35), which fixes Compute ``ParentRecordID`` serialization, adds
``UsageClient.loaded()``, and splits POSTs over 192 KiB.  This adapter keeps batching, paging, and error
normalisation in one place so the accounting service can be tested with fakes.
See references/ACCESS Usage API User's Guide.txt.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

import requests
from amieclient import UsageClient
from amieclient.usage import (
    ComputeUsageRecord,
    UsageLoadedRecord,
    UsageRecordError,
    UsageResponseError,
)
from amieclient.usage.response import UsageStatusResource

from app.config import settings

logger = logging.getLogger(__name__)

# The guide caps POST bodies at 256 KB (about 1000 records). The fork's
# UsageClient.send() also splits anything over 192 KiB, so a batch may yield
# several responses; post_compute() merges their failures.
MAX_RECORDS_PER_POST = 1000
# GET /usage/loaded returns at most 25,000 records per request.
LOADED_PAGE_SIZE = 25000

# Library, transport, and response-parsing failures we normalise.
_CLIENT_ERRORS = (
    UsageResponseError,
    requests.RequestException,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
)


class UsageApiError(RuntimeError):
    """Raised when the Usage API is unreachable, rejects a call, or returns junk."""


def iso_utc(value: datetime) -> str:
    """Format *value* as an ISO 8601 UTC timestamp ending in ``Z``."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class AccessUsageApiClient:
    """Posts Compute usage to ACCESS and queries its load status."""

    def __init__(
        self,
        *,
        site_name: str | None = None,
        api_key: str | None = None,
        usage_url: str | None = None,
        client_factory: Callable[..., UsageClient] = UsageClient,
    ) -> None:
        self.site_name = site_name or settings.amie_site_name
        self.api_key = api_key if api_key is not None else settings.amie_api_key
        self.usage_url = usage_url or settings.amie_usage_url
        self._client_factory = client_factory

    def _client(self) -> UsageClient:
        return self._client_factory(
            site_name=self.site_name,
            api_key=self.api_key,
            usage_url=self.usage_url,
        )

    def post_compute(self, records: list[ComputeUsageRecord]) -> list[UsageRecordError]:
        """POST one batch of Compute records; return validation failures."""
        if len(records) > MAX_RECORDS_PER_POST:
            raise ValueError(
                f"At most {MAX_RECORDS_PER_POST} records per POST (got {len(records)})"
            )
        try:
            with self._client() as client:
                responses = client.send(list(records))
        except _CLIENT_ERRORS as exc:
            raise UsageApiError(f"ACCESS usage POST failed: {exc}") from exc
        return [failed for response in responses for failed in response.failed_records]

    def loaded(
        self, min_loaded_time: datetime, *, page_size: int = LOADED_PAGE_SIZE
    ) -> list[UsageLoadedRecord]:
        """Return every record loaded since *min_loaded_time* (Compute only)."""
        records: list[UsageLoadedRecord] = []
        offset = 0
        try:
            with self._client() as client:
                while True:
                    page = client.loaded(
                        min_loaded_time=min_loaded_time,
                        limit=page_size,
                        offset=offset,
                    ).records
                    records.extend(page)
                    if len(page) < page_size:
                        return records
                    offset += page_size
        except _CLIENT_ERRORS as exc:
            raise UsageApiError(f"ACCESS usage/loaded failed: {exc}") from exc

    def status(
        self, from_time: datetime, to_time: datetime
    ) -> list[UsageStatusResource]:
        """Return per-resource load status (with errors) for a time window."""
        try:
            with self._client() as client:
                return list(client.status(from_time=from_time, to_time=to_time).resources)
        except _CLIENT_ERRORS as exc:
            raise UsageApiError(f"ACCESS usage/status failed: {exc}") from exc
