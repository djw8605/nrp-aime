"""ClickHouse accounting data source.

Queries the ``access_accounting.cluster_namespace_usage_daily`` table for
daily GPU usage records and maps them back to NRP projects and users via the
Kubernetes namespace and CILogon subject ID (``created_by``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import clickhouse_connect

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class GpuUsageRow:
    """One aggregated GPU usage record from ClickHouse."""

    namespace: str
    created_by: str  # CILogon subject ID — matches User.remote_site_login
    date: date
    gpu_hours: Decimal


class ClickHouseUsageService:
    """Queries ClickHouse for daily GPU usage data.

    Usage data is aggregated per ``(namespace, created_by, date)`` so that
    each returned row maps to a single user in a single Kubernetes namespace on
    a specific calendar day.
    """

    def __init__(self) -> None:
        self.host = settings.clickhouse_host
        self.port = settings.clickhouse_port
        self.username = settings.clickhouse_user
        self.password = settings.clickhouse_password
        self.database = settings.clickhouse_database
        self.table = settings.clickhouse_table
        self.secure = settings.clickhouse_secure

    @property
    def is_configured(self) -> bool:
        """Return True when a ClickHouse host has been provided."""
        return bool(self.host)

    def _get_client(self) -> clickhouse_connect.driver.Client:
        return clickhouse_connect.get_client(
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            database=self.database,
            secure=self.secure,
        )

    def get_gpu_usage(self, date_from: date, date_to: date) -> list[GpuUsageRow]:
        """Return GPU usage rows for the given inclusive date range.

        Rows are grouped by ``(namespace, created_by, date)`` and ordered by
        date, namespace, and user so that the caller can iterate predictably.

        Returns an empty list when ClickHouse is not configured or when the
        query fails (errors are logged, not raised).
        """
        if not self.is_configured:
            logger.warning(
                "ClickHouse host is not configured; skipping GPU usage query."
            )
            return []

        query = f"""
            SELECT
                namespace,
                created_by,
                date,
                SUM(usage) AS gpu_hours
            FROM {self.table}
            WHERE resource = 'gpu'
              AND date >= {{date_from:Date}}
              AND date <= {{date_to:Date}}
            GROUP BY namespace, created_by, date
            ORDER BY date, namespace, created_by
        """
        try:
            client = self._get_client()
            result = client.query(
                query,
                parameters={"date_from": date_from, "date_to": date_to},
            )
            rows: list[GpuUsageRow] = []
            for row in result.result_rows:
                rows.append(
                    GpuUsageRow(
                        namespace=row[0],
                        created_by=row[1],
                        date=row[2],
                        gpu_hours=Decimal(str(row[3])),
                    )
                )
            logger.info(
                "ClickHouse returned %d GPU usage rows for %s – %s",
                len(rows),
                date_from,
                date_to,
            )
            return rows
        except Exception:
            logger.exception(
                "Failed to query ClickHouse for GPU usage (%s – %s)",
                date_from,
                date_to,
            )
            return []
