"""Client for the NRP accounting public API (OpenAPI bridge over ClickHouse).

GPU usage comes from ``POST /query_resource_usage`` grouped per
``(date, namespace, created_by)``.  ``created_by`` is the pod creator: a
CILogon subject URL for people, or a service-account / system identity.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

MAX_ROWS_PER_QUERY = 5000


class NrpAccountingApiError(RuntimeError):
    """Raised when the accounting API fails or returns an unexpected payload."""


@dataclass(frozen=True)
class GpuUsageRow:
    """GPU hours for one creator in one namespace on one day."""

    namespace: str
    created_by: str
    date: date
    gpu_hours: Decimal


class NrpAccountingClient:
    """Reads daily GPU usage from the NRP accounting OpenAPI bridge."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or settings.nrp_accounting_api_url).rstrip("/")
        self.timeout = timeout or settings.nrp_accounting_api_timeout_seconds
        self._transport = transport

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                response = client.post(f"{self.base_url}/{path}", json=payload)
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise NrpAccountingApiError(f"NRP accounting API {path} failed: {exc}") from exc
        if not isinstance(body, dict):
            raise NrpAccountingApiError(f"NRP accounting API {path} returned a non-object payload")
        return body

    def latest_data_date(self) -> date:
        """Return the most recent fully ingested accounting date."""
        raw = self._post("get_latest_data_date", {}).get("latest_data_date")
        try:
            return date.fromisoformat(str(raw))
        except ValueError as exc:
            raise NrpAccountingApiError(f"Invalid latest_data_date: {raw!r}") from exc

    def gpu_usage(
        self, namespaces: list[str], date_from: date, date_to: date
    ) -> list[GpuUsageRow]:
        """Return GPU usage rows for *namespaces* in the inclusive date range."""
        if not namespaces or date_from > date_to:
            return []
        return self._query(sorted(set(namespaces)), date_from, date_to)

    def _query(
        self, namespaces: list[str], date_from: date, date_to: date
    ) -> list[GpuUsageRow]:
        body = self._post(
            "query_resource_usage",
            {
                "start_date": date_from.isoformat(),
                "end_date": date_to.isoformat(),
                "namespace": namespaces,
                "resource": "gpu",
                "group_by": ["date", "namespace", "created_by"],
                "limit": MAX_ROWS_PER_QUERY,
            },
        )
        rows = body.get("rows")
        if not isinstance(rows, list):
            raise NrpAccountingApiError("query_resource_usage response has no rows list")
        if len(rows) >= MAX_ROWS_PER_QUERY:
            return self._split(namespaces, date_from, date_to)
        return [self._parse_row(row) for row in rows]

    def _split(
        self, namespaces: list[str], date_from: date, date_to: date
    ) -> list[GpuUsageRow]:
        """Re-query a capped result in smaller pieces (dates first, then namespaces)."""
        if date_from < date_to:
            midpoint = date_from + timedelta(days=(date_to - date_from).days // 2)
            return self._query(namespaces, date_from, midpoint) + self._query(
                namespaces, midpoint + timedelta(days=1), date_to
            )
        if len(namespaces) > 1:
            half = len(namespaces) // 2
            return self._query(namespaces[:half], date_from, date_to) + self._query(
                namespaces[half:], date_from, date_to
            )
        raise NrpAccountingApiError(
            f"More than {MAX_ROWS_PER_QUERY} GPU rows for namespace "
            f"{namespaces[0]} on {date_from}"
        )

    @staticmethod
    def _parse_row(row: Any) -> GpuUsageRow:
        try:
            return GpuUsageRow(
                namespace=str(row["namespace"]),
                created_by=str(row.get("created_by") or ""),
                date=date.fromisoformat(str(row["date"])),
                gpu_hours=Decimal(str(row["usage"])),
            )
        except (KeyError, TypeError, AttributeError, ValueError, ArithmeticError) as exc:
            raise NrpAccountingApiError(f"Malformed usage row: {row!r}") from exc
