# GPU Hour Accounting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Report daily GPU-hour usage for `pnrp.sdsc.access-ci.org` allocations from the NRP accounting public API to the ACCESS Usage API, and show used vs. ACCESS-confirmed SUs on the projects page.

**Architecture:** A `gpu_usage_records` ledger (one row per project × day × AMIE username) is synced each worker cycle from the NRP accounting OpenAPI bridge, submitted to ACCESS as Compute records through `amieclient.UsageClient` (installed from the pinned fork `djw8605/amieclient@1700828`), and reconciled against `/usage/loaded` and `/usage/status`. The projects API exposes a per-project aggregate of the ledger; the Vue projects page renders it.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, httpx (NRP accounting API), amieclient fork (ACCESS Usage API), pytest (in-memory SQLite), Vue 3 `<script setup>` + PrimeVue + Tailwind 4.

**Spec:** `docs/superpowers/specs/2026-10-08-gpu-accounting-design.md`

## Global Constraints

- GPU allocation ⇔ `Project.allocated_resource == settings.amie_gpu_resource_name`; default `pnrp.sdsc.access-ci.org`. That string is the `Resource` sent to ACCESS.
- 1 GPU-hour = 1 SU: `charge = gpu_hours × AMIE_USAGE_GPU_CHARGE_FACTOR` (default `1.0`), quantized to `Decimal("0.000001")`.
- NRP accounting API: `NRP_ACCOUNTING_API_URL` default `https://nrp-accounting-mcp.nrp-nautilus.io/openapi`, no auth, max 5000 rows per query.
- ACCESS Usage API: `AMIE_USAGE_URL` default `https://usage.access-ci.org/api/v1`; headers `XA-SITE`, `XA-API-KEY`; ≤ 1000 records per POST (`MAX_RECORDS_PER_POST`).
- Use `amieclient.UsageClient` for the Usage API, installed `--no-deps` from `https://github.com/djw8605/amieclient/archive/1700828b80fce7e5c97f690bc1a0f9b4c9ffd001.tar.gz` (fork commit `1700828`, upstream PR xsede/amieclient#35: Compute `ParentRecordID` fix, `UsageClient.loaded()`, POSTs split at 192 KiB, `usage.access-ci.org` default). Never install amieclient from PyPI.
- `usage.xsede.org` is dead (expired TLS cert); every reference must become `usage.access-ci.org`.
- Person ⇔ `created_by` matches `^https?://cilogon\.org/` (case-insensitive). A person who is not a member of the project (with a `ProjectUser.remote_site_login`) is **dropped**. Anything else is charged to the project PI (`ProjectUser.role == "pi"`, case-insensitive). PI without login → ledger row with `username=""`, `status="pending"`, never sent.
- `AMIE_USAGE_RESTATEMENT_DAYS` default `7`.
- Projects tagged `debug` are never exported.
- `local_record_id = f"nrp-gpu-{site_project_id}-{YYYYMMDD}-{sha256(username)[:12]}"`.
- Migrations: SQLite-compatible only (`op.add_column` / `op.create_table`; no `ALTER COLUMN`).
- Run backend tests from `backend/` with `../.venv/bin/python -m pytest tests/ -v --tb=short`.
- Commit messages: Conventional Commits, ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Work on branch `claude/gpu-accounting`.

## File Structure

| Path | Responsibility |
|---|---|
| `backend/app/config.py` (modify) | New/changed settings; drop ClickHouse settings |
| `backend/app/models/gpu_usage_record.py` (create) | Ledger ORM model + status/attribution constants |
| `backend/app/models/project.py` (modify) | `gpu_usage_synced_through` column + relationship |
| `backend/app/models/__init__.py` (modify) | Register model |
| `backend/migrations/versions/0022_gpu_usage_records.py` (create) | Table + column migration |
| `backend/app/services/nrp_accounting/client.py` (create) | NRP accounting API client |
| `backend/app/services/aime/usage_api.py` (create) | Adapter over `amieclient.UsageClient` (batching, paging, error normalisation) |
| `backend/Dockerfile`, `.github/workflows/test.yml`, `backend/requirements.txt` (modify) | Install amieclient from the pinned fork |
| `backend/tests/conftest.py` (modify) | Import the real amieclient before per-module stubs |
| `backend/app/services/gpu_accounting/scope.py` (create) | `is_gpu_project`, `is_exportable_gpu_project` |
| `backend/app/services/gpu_accounting/attribution.py` (create) | `created_by` → AMIE username |
| `backend/app/services/gpu_accounting/service.py` (create) | `GpuAccountingService` (sync, submit, reconcile, run_cycle) |
| `backend/app/services/gpu_accounting/summary.py` (create) | Aggregates for the API |
| `backend/app/schemas/project.py` (modify) | `GpuAccountingSummary`, new `ProjectRead`/`ProjectSummary` fields |
| `backend/app/api/projects.py` (modify) | Attach `gpu_accounting`; summary totals |
| `backend/workers/usage_worker.py` (modify) | Run `GpuAccountingService.run_cycle` |
| `backend/app/services/aime/usage_service.py`, `backend/app/services/clickhouse/` (delete) | Replaced |
| `backend/requirements.txt` (modify) | Drop `clickhouse-connect` |
| `frontend/src/components/GpuAccountingSummary.vue` (create) | GPU SU display block |
| `frontend/src/components/ProjectCard.vue`, `ProjectDetail.vue`, `frontend/src/views/ProjectsView.vue` (modify) | Render it; KPIs |
| `deployment/config/app.env`, `docker-compose.yml`, `README.md`, `backend/README.md`, `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md` (modify) | Config + docs |

---

### Task 1: Settings, ledger model, and migration

**Files:**
- Modify: `backend/app/config.py:15-39`
- Create: `backend/app/models/gpu_usage_record.py`
- Modify: `backend/app/models/project.py` (column after `authentik_group_name`; relationship after `usage_exports`)
- Modify: `backend/app/models/__init__.py`
- Create: `backend/migrations/versions/0022_gpu_usage_records.py`
- Test: `backend/tests/test_gpu_usage_record_model.py`, `backend/tests/test_migrations.py`

**Interfaces:**
- Produces: `settings.nrp_accounting_api_url: str`, `settings.nrp_accounting_api_timeout_seconds: float`, `settings.amie_usage_restatement_days: int`, `settings.amie_gpu_resource_name: str` (default `"pnrp.sdsc.access-ci.org"`), `settings.amie_usage_url` default `"https://usage.access-ci.org/api/v1"`.
- Produces: `GpuUsageRecord` with constants `STATUS_PENDING="pending"`, `STATUS_SUBMITTED="submitted"`, `STATUS_LOADED="loaded"`, `STATUS_FAILED="failed"`, `ATTRIBUTION_MEMBER="member"`, `ATTRIBUTION_PI="pi"`; columns `id, project_id, usage_date, username, attribution, gpu_hours, charge, local_record_id, status, submitted_charge, last_error, accounting_db_record_id, attempts, submitted_at, loaded_at, created_at, updated_at`; relationship `project`.
- Produces: `Project.gpu_usage_synced_through: date | None`, `Project.gpu_usage_records`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_gpu_usage_record_model.py`:

```python
"""Tests for the GPU usage ledger model."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.gpu_usage_record import GpuUsageRecord


def _record(project, **overrides):
    defaults = {
        "project_id": project.id,
        "usage_date": date(2026, 10, 1),
        "username": "alice",
        "attribution": GpuUsageRecord.ATTRIBUTION_MEMBER,
        "gpu_hours": Decimal("1.5"),
        "charge": Decimal("1.5"),
        "local_record_id": "nrp-gpu-p1-20261001-abc",
    }
    defaults.update(overrides)
    return GpuUsageRecord(**defaults)


def test_record_defaults_to_pending(db, make_project):
    project = make_project(db)
    record = _record(project)
    db.add(record)
    db.flush()
    assert record.status == GpuUsageRecord.STATUS_PENDING
    assert record.attempts == 0
    assert record.submitted_charge is None


def test_project_date_username_is_unique(db, make_project):
    project = make_project(db)
    db.add(_record(project))
    db.flush()
    db.add(_record(project, local_record_id="nrp-gpu-p1-20261001-other"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_project_has_synced_through_column(db, make_project):
    project = make_project(db, gpu_usage_synced_through=date(2026, 10, 7))
    db.flush()
    assert project.gpu_usage_synced_through == date(2026, 10, 7)
```

Append to `backend/tests/test_migrations.py` inside `class TestMigrationChain`:

```python
    def test_head_is_gpu_usage_records(self):
        """The GPU usage ledger migration is the current head."""
        scripts = ScriptDirectory.from_config(_alembic_config())
        assert scripts.get_current_head() == "0022_gpu_usage_records"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_gpu_usage_record_model.py tests/test_migrations.py -v --tb=short`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.gpu_usage_record'` and head assertion mismatch.

- [ ] **Step 3: Update settings**

In `backend/app/config.py`, replace the block from `# ClickHouse accounting database` through `amie_gpu_resource_name: str = ""` with:

```python
    # NRP accounting public API (OpenAPI bridge over the ClickHouse accounting DB).
    # Source of daily GPU hours reported to the ACCESS Usage API.
    nrp_accounting_api_url: str = "https://nrp-accounting-mcp.nrp-nautilus.io/openapi"
    nrp_accounting_api_timeout_seconds: float = 120.0

    # GPU-hour allocations: projects whose allocated_resource equals this value are
    # reported to ACCESS, using this value as the usage record Resource.
    amie_gpu_resource_name: str = "pnrp.sdsc.access-ci.org"
```

In the AMIE block, change `amie_usage_url` default to `"https://usage.access-ci.org/api/v1"`, delete the `amie_usage_default_username` line, and add after `amie_usage_gpu_charge_factor`:

```python
    # Days before the last synced date that are re-fetched each cycle so restated
    # accounting data is re-submitted (same LocalRecordID overwrites at ACCESS).
    amie_usage_restatement_days: int = 7
```

- [ ] **Step 4: Create the model**

Create `backend/app/models/gpu_usage_record.py`:

```python
"""Ledger of daily GPU usage reported to the ACCESS Usage API."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class GpuUsageRecord(Base):
    """GPU hours for one AMIE username in one project on one UTC day."""

    __tablename__ = "gpu_usage_records"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "usage_date",
            "username",
            name="uq_gpu_usage_project_date_username",
        ),
    )

    STATUS_PENDING = "pending"
    STATUS_SUBMITTED = "submitted"
    STATUS_LOADED = "loaded"
    STATUS_FAILED = "failed"
    STATUSES = (STATUS_PENDING, STATUS_SUBMITTED, STATUS_LOADED, STATUS_FAILED)

    ATTRIBUTION_MEMBER = "member"
    ATTRIBUTION_PI = "pi"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    usage_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # AMIE Username; "" while the PI has no site login yet (never submitted).
    username: Mapped[str] = mapped_column(String, nullable=False)
    attribution: Mapped[str] = mapped_column(String, nullable=False)
    gpu_hours: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0")
    )
    charge: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0")
    )
    local_record_id: Mapped[str] = mapped_column(
        String, nullable=False, unique=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=STATUS_PENDING, index=True
    )
    submitted_charge: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    accounting_db_record_id: Mapped[str | None] = mapped_column(String, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    loaded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project: Mapped["Project"] = relationship(
        "Project", back_populates="gpu_usage_records"
    )
```

- [ ] **Step 5: Extend Project and register the model**

In `backend/app/models/project.py`, add after the `authentik_group_name` column:

```python
    # Last accounting date fully synced into gpu_usage_records (GPU allocations only).
    gpu_usage_synced_through: Mapped[date | None] = mapped_column(Date, nullable=True)
```

Add after the `usage_exports` relationship:

```python
    gpu_usage_records: Mapped[list["GpuUsageRecord"]] = relationship(
        "GpuUsageRecord",
        back_populates="project",
        cascade="all, delete-orphan",
    )
```

In `backend/app/models/__init__.py` add `from app.models.gpu_usage_record import GpuUsageRecord` (alphabetically after `alert_notification`) and `"GpuUsageRecord",` to `__all__` after `"AlertNotification",`.

- [ ] **Step 6: Create the migration**

Create `backend/migrations/versions/0022_gpu_usage_records.py`:

```python
"""Add GPU usage ledger and per-project sync watermark.

Revision ID: 0022_gpu_usage_records
Revises: 0021_reset_unonboarded_pi_state
Create Date: 2026-10-08 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0022_gpu_usage_records"
down_revision = "0021_reset_unonboarded_pi_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply schema changes."""
    op.create_table(
        "gpu_usage_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("attribution", sa.String(), nullable=False),
        sa.Column("gpu_hours", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("charge", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("local_record_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("submitted_charge", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("accounting_db_record_id", sa.String(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "usage_date",
            "username",
            name="uq_gpu_usage_project_date_username",
        ),
    )
    op.create_index(
        op.f("ix_gpu_usage_records_local_record_id"),
        "gpu_usage_records",
        ["local_record_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_gpu_usage_records_project_id"),
        "gpu_usage_records",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_gpu_usage_records_usage_date"),
        "gpu_usage_records",
        ["usage_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_gpu_usage_records_status"),
        "gpu_usage_records",
        ["status"],
        unique=False,
    )
    op.add_column(
        "projects",
        sa.Column("gpu_usage_synced_through", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    """Rollback schema changes."""
    op.drop_column("projects", "gpu_usage_synced_through")
    op.drop_index(op.f("ix_gpu_usage_records_status"), table_name="gpu_usage_records")
    op.drop_index(op.f("ix_gpu_usage_records_usage_date"), table_name="gpu_usage_records")
    op.drop_index(op.f("ix_gpu_usage_records_project_id"), table_name="gpu_usage_records")
    op.drop_index(
        op.f("ix_gpu_usage_records_local_record_id"), table_name="gpu_usage_records"
    )
    op.drop_table("gpu_usage_records")
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && ../.venv/bin/python -m pytest tests/ -v --tb=short`
Expected: all PASS (existing 128 + 4 new). Note: `app/services/aime/usage_service.py` still references `settings.amie_usage_default_username` but is not imported by tests; it is deleted in Task 7.

- [ ] **Step 8: Commit**

```bash
git add backend/app/config.py backend/app/models/gpu_usage_record.py backend/app/models/project.py backend/app/models/__init__.py backend/migrations/versions/0022_gpu_usage_records.py backend/tests/test_gpu_usage_record_model.py backend/tests/test_migrations.py
git commit -m "feat: add GPU usage ledger model and migration

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: NRP accounting API client

**Files:**
- Create: `backend/app/services/nrp_accounting/__init__.py`, `backend/app/services/nrp_accounting/client.py`
- Test: `backend/tests/test_nrp_accounting_client.py`

**Interfaces:**
- Consumes: `settings.nrp_accounting_api_url`, `settings.nrp_accounting_api_timeout_seconds` (Task 1).
- Produces: `GpuUsageRow(namespace: str, created_by: str, date: date, gpu_hours: Decimal)` (frozen dataclass); `NrpAccountingApiError(RuntimeError)`; `MAX_ROWS_PER_QUERY = 5000`; `NrpAccountingClient(*, base_url=None, timeout=None, transport=None)` with `latest_data_date() -> date` and `gpu_usage(namespaces: list[str], date_from: date, date_to: date) -> list[GpuUsageRow]`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_nrp_accounting_client.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_nrp_accounting_client.py -v --tb=short`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.nrp_accounting'`.

- [ ] **Step 3: Implement the client**

Create `backend/app/services/nrp_accounting/__init__.py`:

```python
"""NRP accounting public API package."""
```

Create `backend/app/services/nrp_accounting/client.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_nrp_accounting_client.py -v --tb=short`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/nrp_accounting backend/tests/test_nrp_accounting_client.py
git commit -m "feat: add NRP accounting public API client

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Install amieclient from the pinned fork + ACCESS Usage adapter

**Files:**
- Modify: `backend/Dockerfile:12-16`, `.github/workflows/test.yml` ("Install dependencies" step), `backend/requirements.txt:9-11` (comment only)
- Modify: `backend/tests/conftest.py` (top of file)
- Create: `backend/app/services/aime/usage_api.py`
- Test: `backend/tests/test_access_usage_api.py`

**Interfaces:**
- Consumes: `settings.amie_site_name`, `settings.amie_api_key`, `settings.amie_usage_url` (Task 1).
- Consumes (library, fork `1700828`): `amieclient.UsageClient(site_name, api_key, usage_url)` context manager with `send(records) -> list[UsageResponse]`, `loaded(min_loaded_time, limit, offset) -> UsageLoaded`, `status(from_time, to_time) -> UsageStatus`; `amieclient.usage.ComputeUsageRecord`, `UsageRecordError` (`.error`, `.record.local_record_id`), `UsageLoadedRecord` (`.local_record_id`, `.resource`, `.charge`, `.accounting_db_record_id`), `UsageResponseError`; `amieclient.usage.response.UsageStatusResource` (`.resource`, `.errors` → `UsageMessageError` with `.error`, `.message.records`).
- Produces: `MAX_RECORDS_PER_POST = 1000`, `LOADED_PAGE_SIZE = 25000`; `UsageApiError(RuntimeError)`; `iso_utc(value: datetime) -> str` (`YYYY-MM-DDTHH:MM:SSZ`); `AccessUsageApiClient(*, site_name=None, api_key=None, usage_url=None, client_factory=UsageClient)` with attribute `api_key: str` and methods `post_compute(records: list[ComputeUsageRecord]) -> list[UsageRecordError]` (raises `ValueError` if > 1000), `loaded(min_loaded_time: datetime, *, page_size: int = LOADED_PAGE_SIZE) -> list[UsageLoadedRecord]`, `status(from_time: datetime, to_time: datetime) -> list[UsageStatusResource]`. All library/transport/parse errors surface as `UsageApiError`.

- [ ] **Step 1: Install the fork everywhere**

The fork is a pure-Python sdist; install it from GitHub's commit archive (no `git` binary needed in the image) and keep `--no-deps` (its `python-dateutil<2.9` pin is still stale; `requirements.txt` supplies `requests` and `python-dateutil`).

In `backend/Dockerfile`, replace:

```dockerfile
# amieclient pins python-dateutil<2.7 which is incompatible with Python 3.11
# (collections.Callable was removed). Install it without its deps so pip does
# not enforce that stale constraint; requirements.txt supplies a compatible dateutil.
RUN pip install --no-cache-dir "amieclient>=0.4.0" --no-deps && \
    pip install --no-cache-dir -r requirements.txt
```

with:

```dockerfile
# amieclient comes from djw8605/amieclient@1700828 (upstream PR xsede/amieclient#35):
# fixes Compute ParentRecordID serialization, adds UsageClient.loaded(),
# keeps POSTs under the 256 KB limit, and defaults to usage.access-ci.org. Switch back to PyPI once upstream releases it.
# Installed without deps: its python-dateutil pin is stale; requirements.txt
# supplies requests and a compatible dateutil.
ARG AMIECLIENT_URL=https://github.com/djw8605/amieclient/archive/1700828b80fce7e5c97f690bc1a0f9b4c9ffd001.tar.gz
RUN pip install --no-cache-dir --no-deps "amieclient @ ${AMIECLIENT_URL}" && \
    pip install --no-cache-dir -r requirements.txt
```

In `.github/workflows/test.yml`, replace the line `pip install --no-cache-dir "amieclient>=0.4.0" --no-deps` with:

```yaml
          pip install --no-cache-dir --no-deps "amieclient @ https://github.com/djw8605/amieclient/archive/1700828b80fce7e5c97f690bc1a0f9b4c9ffd001.tar.gz"
```

In `backend/requirements.txt`, replace the comment lines 9-11 with:

```
# amieclient is installed by the Dockerfile and CI from the pinned fork
# djw8605/amieclient@1700828 with --no-deps (its python-dateutil pin is stale).
# Its runtime dependencies are listed here explicitly as a result.
```

Install it into the local dev venv (already done once while planning; re-run is harmless):

```bash
uv pip install --python .venv/bin/python --no-deps "amieclient @ https://github.com/djw8605/amieclient/archive/1700828b80fce7e5c97f690bc1a0f9b4c9ffd001.tar.gz"
```

- [ ] **Step 2: Make tests use the real amieclient**

`test_account_lifecycle.py`, `test_lifecycle_notifications.py` and `test_user_invites.py` install a placeholder `amieclient` module when it is not already imported. Without intervention, that stub can land in `sys.modules` before the usage modules import `amieclient.usage`. Add at the top of `backend/tests/conftest.py`, directly after the module docstring:

```python
# Import the real amieclient (pinned fork) before any test module installs its
# placeholder stub, so the ACCESS Usage adapter always sees the real package.
try:
    import amieclient.usage  # noqa: F401
except ImportError:  # pragma: no cover - modules fall back to their own stubs
    pass
```

(Verified while planning: the existing 128 tests pass with the real package preloaded.)

- [ ] **Step 3: Write the failing tests**

Create `backend/tests/test_access_usage_api.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_access_usage_api.py -v --tb=short`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.aime.usage_api'`. (If instead it fails importing `amieclient.usage`, Step 1's local install did not run.)

- [ ] **Step 5: Implement the adapter**

Create `backend/app/services/aime/usage_api.py`:

```python
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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && ../.venv/bin/python -m pytest tests/ -v --tb=short`
Expected: all PASS (existing suite + 9 new).

- [ ] **Step 7: Commit**

```bash
git add backend/Dockerfile .github/workflows/test.yml backend/requirements.txt backend/tests/conftest.py backend/app/services/aime/usage_api.py backend/tests/test_access_usage_api.py
git commit -m "feat: install amieclient from pinned fork and add ACCESS usage adapter

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: GPU project scope and usage attribution

**Files:**
- Create: `backend/app/services/gpu_accounting/__init__.py`, `scope.py`, `attribution.py`
- Test: `backend/tests/test_gpu_attribution.py`

**Interfaces:**
- Consumes: `GpuUsageRecord.ATTRIBUTION_*` (Task 1), `settings.amie_gpu_resource_name`.
- Produces: `is_gpu_project(project) -> bool`; `is_exportable_gpu_project(project) -> bool`; `Attribution(username: str, attribution: str)` (frozen dataclass); `GpuUsageAttributor(db)` with `is_person(created_by: str) -> bool` (staticmethod) and `attribute(project, created_by) -> Attribution | None` (None ⇒ drop).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_gpu_attribution.py`:

```python
"""Tests for GPU project scope and created_by attribution."""

from app.models.gpu_usage_record import GpuUsageRecord
from app.services.gpu_accounting.attribution import Attribution, GpuUsageAttributor
from app.services.gpu_accounting.scope import is_exportable_gpu_project, is_gpu_project

GPU = "pnrp.sdsc.access-ci.org"
ALICE = "http://cilogon.org/serverE/users/1001"
BOB = "https://cilogon.org/serverA/users/2002"


def _gpu_project(db, make_project, **overrides):
    defaults = {
        "allocated_resource": GPU,
        "site_project_id": "p.gpu1",
        "kubernetes_namespace": "ns-gpu",
    }
    defaults.update(overrides)
    return make_project(db, **defaults)


class TestScope:
    def test_gpu_project_matches_allocated_resource(self, db, make_project):
        assert is_gpu_project(_gpu_project(db, make_project))
        assert not is_gpu_project(make_project(db, allocated_resource="nrp-classroom.access-ci.org"))
        assert not is_gpu_project(make_project(db, allocated_resource=None))

    def test_exportable_requires_ids_and_excludes_debug(self, db, make_project):
        assert is_exportable_gpu_project(_gpu_project(db, make_project))
        assert not is_exportable_gpu_project(_gpu_project(db, make_project, site_project_id=None))
        assert not is_exportable_gpu_project(_gpu_project(db, make_project, kubernetes_namespace=""))
        assert not is_exportable_gpu_project(_gpu_project(db, make_project, tags=["Debug"]))


class TestAttribution:
    def test_is_person(self):
        assert GpuUsageAttributor.is_person(ALICE)
        assert GpuUsageAttributor.is_person(BOB)
        assert not GpuUsageAttributor.is_person("system:serviceaccount:ns:sa")
        assert not GpuUsageAttributor.is_person("")

    def test_member_person_uses_project_login(self, db, make_project, make_user, make_project_user):
        project = _gpu_project(db, make_project)
        alice = make_user(db, remote_site_login=ALICE)
        make_project_user(db, project, alice, remote_site_login="alice_nrp")

        result = GpuUsageAttributor(db).attribute(project, ALICE)

        assert result == Attribution("alice_nrp", GpuUsageRecord.ATTRIBUTION_MEMBER)

    def test_person_not_in_project_is_dropped(self, db, make_project, make_user, make_project_user):
        project = _gpu_project(db, make_project)
        other = _gpu_project(db, make_project, kubernetes_namespace="ns-other", site_project_id="p.other")
        alice = make_user(db, remote_site_login=ALICE)
        make_project_user(db, other, alice, remote_site_login="alice_nrp")

        assert GpuUsageAttributor(db).attribute(project, ALICE) is None

    def test_member_without_login_is_dropped(self, db, make_project, make_user, make_project_user):
        project = _gpu_project(db, make_project)
        alice = make_user(db, remote_site_login=ALICE)
        make_project_user(db, project, alice, remote_site_login=None)

        assert GpuUsageAttributor(db).attribute(project, ALICE) is None

    def test_unknown_person_is_dropped(self, db, make_project):
        project = _gpu_project(db, make_project)
        assert GpuUsageAttributor(db).attribute(project, BOB) is None

    def test_service_account_charged_to_pi(self, db, make_project, make_user, make_project_user):
        project = _gpu_project(db, make_project)
        pi = make_user(db)
        make_project_user(db, project, pi, role="PI", remote_site_login="pi_nrp")
        db.refresh(project)

        result = GpuUsageAttributor(db).attribute(project, "system:serviceaccount:ns-gpu:runner")

        assert result == Attribution("pi_nrp", GpuUsageRecord.ATTRIBUTION_PI)

    def test_service_account_with_pi_missing_login_is_pending(self, db, make_project, make_user, make_project_user):
        project = _gpu_project(db, make_project)
        pi = make_user(db)
        make_project_user(db, project, pi, role="pi", remote_site_login=None)
        db.refresh(project)

        result = GpuUsageAttributor(db).attribute(project, "")

        assert result == Attribution("", GpuUsageRecord.ATTRIBUTION_PI)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_gpu_attribution.py -v --tb=short`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.gpu_accounting'`.

- [ ] **Step 3: Implement scope and attribution**

Create `backend/app/services/gpu_accounting/__init__.py`:

```python
"""GPU-hour accounting: NRP accounting API → ledger → ACCESS Usage API."""
```

Create `backend/app/services/gpu_accounting/scope.py`:

```python
"""Which projects are GPU-hour allocations reported to ACCESS."""

from __future__ import annotations

from app.config import settings
from app.models.project import Project


def is_gpu_project(project: Project) -> bool:
    """Return True when the project's allocated resource is the GPU resource."""
    resource = (settings.amie_gpu_resource_name or "").strip()
    return bool(resource) and (project.allocated_resource or "").strip() == resource


def is_exportable_gpu_project(project: Project) -> bool:
    """Return True when GPU usage for *project* can be reported to ACCESS."""
    tags = {str(tag).strip().lower() for tag in (project.tags or [])}
    return (
        is_gpu_project(project)
        and bool((project.site_project_id or "").strip())
        and bool((project.kubernetes_namespace or "").strip())
        and "debug" not in tags
    )
```

Create `backend/app/services/gpu_accounting/attribution.py`:

```python
"""Map an accounting ``created_by`` to the AMIE username charged for it.

People are identified by CILogon subject URLs (``User.remote_site_login``)
and must be members of the project; their usage is otherwise dropped.  Any
non-person creator (service accounts, ``system:*``, empty) is charged to the
project PI.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import settings
from app.models.gpu_usage_record import GpuUsageRecord
from app.models.project import Project
from app.models.project_user import ProjectUser
from app.models.user import User

CILOGON_SUBJECT_RE = re.compile(r"^https?://cilogon\.org/", re.IGNORECASE)


@dataclass(frozen=True)
class Attribution:
    """AMIE username to charge; ``""`` when the PI has no site login yet."""

    username: str
    attribution: str


def _preferred_login(memberships: Iterable[ProjectUser]) -> str | None:
    """Pick a site login, preferring GPU-resource and active memberships."""
    gpu_resource = settings.amie_gpu_resource_name
    with_login = [pu for pu in memberships if (pu.remote_site_login or "").strip()]
    if not with_login:
        return None
    with_login.sort(
        key=lambda pu: (
            gpu_resource not in (pu.resource, pu.allocated_resource),
            not pu.is_active,
        )
    )
    return with_login[0].remote_site_login.strip()


class GpuUsageAttributor:
    """Resolves usage rows to AMIE usernames for one sync cycle."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self._member_logins: dict[tuple[uuid.UUID, str], str | None] = {}

    @staticmethod
    def is_person(created_by: str) -> bool:
        return bool(CILOGON_SUBJECT_RE.match(created_by or ""))

    def attribute(self, project: Project, created_by: str) -> Attribution | None:
        """Return who to charge for *created_by* in *project*; None means drop."""
        if self.is_person(created_by):
            login = self._member_login(project, created_by)
            if login is None:
                return None
            return Attribution(login, GpuUsageRecord.ATTRIBUTION_MEMBER)
        return Attribution(self._pi_login(project) or "", GpuUsageRecord.ATTRIBUTION_PI)

    def _member_login(self, project: Project, cilogon_id: str) -> str | None:
        key = (project.id, cilogon_id)
        if key not in self._member_logins:
            memberships = (
                self.db.query(ProjectUser)
                .join(User, User.id == ProjectUser.user_id)
                .filter(
                    ProjectUser.project_id == project.id,
                    User.remote_site_login == cilogon_id,
                )
                .all()
            )
            self._member_logins[key] = _preferred_login(memberships)
        return self._member_logins[key]

    @staticmethod
    def _pi_login(project: Project) -> str | None:
        pis = [
            pu
            for pu in project.project_users
            if str(pu.role or "").strip().lower() == "pi"
        ]
        return _preferred_login(pis)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_gpu_attribution.py -v --tb=short`
Expected: 9 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/gpu_accounting backend/tests/test_gpu_attribution.py
git commit -m "feat: add GPU project scope and usage attribution

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Ledger sync (`GpuAccountingService.sync_ledger`)

**Files:**
- Create: `backend/app/services/gpu_accounting/service.py`
- Create: `backend/tests/gpu_accounting_support.py`
- Test: `backend/tests/test_gpu_accounting_sync.py`

**Interfaces:**
- Consumes: `NrpAccountingClient.latest_data_date()`, `.gpu_usage(namespaces, date_from, date_to)` and `GpuUsageRow` (Task 2); `AccessUsageApiClient` (Task 3); `is_exportable_gpu_project`, `GpuUsageAttributor` (Task 4); `GpuUsageRecord`, `Project.gpu_usage_synced_through` (Task 1).
- Produces: `QUANT = Decimal("0.000001")`, `PI_LOGIN_MISSING = "PI has no site login yet"`; `GpuAccountingService(*, accounting_client=None, usage_client=None)` with `local_record_id(project, usage_date, username) -> str` (staticmethod) and `sync_ledger(db) -> dict[str, int]` returning keys `projects`, `rows`, `dropped`, `records_changed`.
- Produces (tests): `tests/gpu_accounting_support.py` with `GPU`, `FakeAccountingClient(latest, rows)`, `FakeUsageClient(api_key="key")` (fields `posts`, `validation_errors`, `post_error`, `loaded_records`, `status_resources`, `status_error`), `gpu_project(db, make_project, **overrides)`, `usage_row(created_by, day, hours, namespace="ns-gpu")`.

- [ ] **Step 1: Write the test support module**

Create `backend/tests/gpu_accounting_support.py`:

```python
"""Fakes and helpers for GPU accounting service tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from amieclient.usage import UsageRecordError

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
        self.status_resources: list = []  # UsageStatusResource
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
        return list(self.loaded_records)

    def status(self, from_time, to_time):
        if self.status_error is not None:
            raise self.status_error
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
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_gpu_accounting_sync.py`:

```python
"""Tests for syncing NRP accounting rows into the GPU usage ledger."""

import hashlib
from datetime import date
from decimal import Decimal

from app.models.gpu_usage_record import GpuUsageRecord
from app.services.gpu_accounting.service import PI_LOGIN_MISSING, GpuAccountingService
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
    # Next fetch must start at 2026-10-02: synced_through - 7 days <= 2026-10-02.
    assert project.gpu_usage_synced_through == date(2026, 10, 7)
    service.accounting.latest = date(2026, 10, 20)
    service.sync_ledger(db)
    assert service.accounting.calls[-1][1] == date(2026, 10, 2)
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_gpu_accounting_sync.py -v --tb=short`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.gpu_accounting.service'`.

- [ ] **Step 4: Implement `sync_ledger`**

Create `backend/app/services/gpu_accounting/service.py`:

```python
"""GPU-hour accounting export: NRP accounting API → ledger → ACCESS.

Each cycle:
1. ``sync_ledger`` pulls daily GPU usage for GPU allocations, attributes it to
   AMIE usernames, and upserts ``gpu_usage_records``.
2. ``submit_pending`` posts pending/failed records as Compute usage.
3. ``reconcile`` marks records loaded/failed from ``/usage/loaded`` and
   ``/usage/status``.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import settings
from app.models.gpu_usage_record import GpuUsageRecord
from app.models.project import Project
from app.services.aime.usage_api import AccessUsageApiClient
from app.services.gpu_accounting.attribution import GpuUsageAttributor
from app.services.gpu_accounting.scope import is_exportable_gpu_project
from app.services.nrp_accounting.client import GpuUsageRow, NrpAccountingClient

logger = logging.getLogger(__name__)

QUANT = Decimal("0.000001")
PI_LOGIN_MISSING = "PI has no site login yet"

# (usage_date, username) -> (gpu_hours, attribution)
DesiredRecords = dict[tuple[date, str], tuple[Decimal, str]]


class GpuAccountingService:
    """Syncs, submits, and reconciles GPU usage for GPU allocations."""

    def __init__(
        self,
        *,
        accounting_client: NrpAccountingClient | None = None,
        usage_client: AccessUsageApiClient | None = None,
    ) -> None:
        self.accounting = accounting_client or NrpAccountingClient()
        self.usage = usage_client or AccessUsageApiClient()
        self.resource = settings.amie_gpu_resource_name
        self.charge_factor = Decimal(str(settings.amie_usage_gpu_charge_factor))
        self.restatement_days = max(0, settings.amie_usage_restatement_days)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def local_record_id(project: Project, usage_date: date, username: str) -> str:
        """Stable ACCESS LocalRecordID for one project/day/username."""
        user_hash = hashlib.sha256(username.encode()).hexdigest()[:12]
        return f"nrp-gpu-{project.site_project_id}-{usage_date:%Y%m%d}-{user_hash}"

    def _charge(self, gpu_hours: Decimal) -> Decimal:
        return (gpu_hours * self.charge_factor).quantize(QUANT)

    def _fetch_window(self, project: Project, latest: date) -> tuple[date, date] | None:
        """Inclusive date range to (re)fetch for *project*, or None."""
        start = project.start_date
        if start is None and project.created_at is not None:
            start = project.created_at.date()
        if start is None:
            return None
        end = min(project.end_date or latest, latest)
        if project.gpu_usage_synced_through is not None:
            start = max(
                start,
                project.gpu_usage_synced_through - timedelta(days=self.restatement_days),
            )
        if start > end:
            return None
        return start, end

    # ------------------------------------------------------------------
    # Ledger sync
    # ------------------------------------------------------------------

    def sync_ledger(self, db: Session) -> dict[str, int]:
        """Pull GPU usage and upsert ledger rows for every exportable GPU project."""
        counters = {"projects": 0, "rows": 0, "dropped": 0, "records_changed": 0}
        latest = self.accounting.latest_data_date()

        windows: dict[uuid.UUID, tuple[Project, date, date]] = {}
        for project in db.query(Project).all():
            if not is_exportable_gpu_project(project):
                continue
            window = self._fetch_window(project, latest)
            if window is not None:
                windows[project.id] = (project, *window)
        if not windows:
            return counters

        by_namespace: dict[str, list[tuple[Project, date, date]]] = defaultdict(list)
        for entry in windows.values():
            by_namespace[entry[0].kubernetes_namespace].append(entry)

        rows = self.accounting.gpu_usage(
            list(by_namespace),
            min(start for _, start, _ in windows.values()),
            max(end for _, _, end in windows.values()),
        )

        attributor = GpuUsageAttributor(db)
        desired: dict[uuid.UUID, DesiredRecords] = defaultdict(dict)
        pi_missing_from: dict[uuid.UUID, date] = {}
        for row in rows:
            project = self._project_for_row(row, by_namespace)
            if project is None:
                continue
            attribution = attributor.attribute(project, row.created_by)
            if attribution is None:
                counters["dropped"] += 1
                logger.info(
                    "Dropping GPU usage for non-member namespace=%s created_by=%s date=%s hours=%s",
                    row.namespace,
                    row.created_by,
                    row.date,
                    row.gpu_hours,
                )
                continue
            counters["rows"] += 1
            key = (row.date, attribution.username)
            hours, _ = desired[project.id].get(key, (Decimal("0"), attribution.attribution))
            desired[project.id][key] = (hours + row.gpu_hours, attribution.attribution)
            if not attribution.username:
                pi_missing_from[project.id] = min(row.date, pi_missing_from.get(project.id, row.date))

        for project_id, (project, start, end) in windows.items():
            counters["records_changed"] += self._apply(
                db, project, start, end, desired.get(project_id, {})
            )
            missing = pi_missing_from.get(project_id)
            if missing is None:
                project.gpu_usage_synced_through = latest
            else:
                # Hold the watermark so the next fetch re-reads the PI-pending days.
                project.gpu_usage_synced_through = min(
                    latest, missing + timedelta(days=self.restatement_days)
                )
            counters["projects"] += 1

        db.commit()
        return counters

    @staticmethod
    def _project_for_row(
        row: GpuUsageRow,
        by_namespace: dict[str, list[tuple[Project, date, date]]],
    ) -> Project | None:
        for project, start, end in by_namespace.get(row.namespace, []):
            if start <= row.date <= end:
                return project
        return None

    def _apply(
        self,
        db: Session,
        project: Project,
        start: date,
        end: date,
        desired: DesiredRecords,
    ) -> int:
        """Upsert ledger rows for *project* within [start, end]; return change count."""
        existing = {
            (record.usage_date, record.username): record
            for record in db.query(GpuUsageRecord)
            .filter(
                GpuUsageRecord.project_id == project.id,
                GpuUsageRecord.usage_date >= start,
                GpuUsageRecord.usage_date <= end,
            )
            .all()
        }
        changed = 0

        for key, record in existing.items():
            if key in desired:
                continue
            if record.submitted_charge is None:
                db.delete(record)
                changed += 1
            elif Decimal(record.gpu_hours).quantize(QUANT) != Decimal("0").quantize(QUANT):
                self._set_hours(record, Decimal("0").quantize(QUANT))
                changed += 1

        for (usage_date, username), (hours, attribution) in desired.items():
            hours = hours.quantize(QUANT)
            record = existing.get((usage_date, username))
            if record is None:
                db.add(
                    GpuUsageRecord(
                        project_id=project.id,
                        usage_date=usage_date,
                        username=username,
                        attribution=attribution,
                        gpu_hours=hours,
                        charge=self._charge(hours),
                        local_record_id=self.local_record_id(project, usage_date, username),
                        status=GpuUsageRecord.STATUS_PENDING,
                        attempts=0,
                        last_error=None if username else PI_LOGIN_MISSING,
                    )
                )
                changed += 1
            elif Decimal(record.gpu_hours).quantize(QUANT) != hours:
                self._set_hours(record, hours)
                changed += 1
        db.flush()
        return changed

    def _set_hours(self, record: GpuUsageRecord, hours: Decimal) -> None:
        record.gpu_hours = hours
        record.charge = self._charge(hours)
        record.status = GpuUsageRecord.STATUS_PENDING
        record.last_error = None if record.username else PI_LOGIN_MISSING
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_gpu_accounting_sync.py -v --tb=short`
Expected: 10 PASS. Also confirm `ls backend/tests/*.py | xargs grep -l "from tests\." ` resolves imports (the `tests` package has `__init__.py`); if `from tests.gpu_accounting_support import` fails with `ModuleNotFoundError`, check how `tests/support.py` is imported elsewhere (`grep -rn "support import" backend/tests`) and use the same form.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/gpu_accounting/service.py backend/tests/gpu_accounting_support.py backend/tests/test_gpu_accounting_sync.py
git commit -m "feat: sync NRP GPU usage into the usage ledger

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Submit, reconcile, and `run_cycle`

**Files:**
- Modify: `backend/app/services/gpu_accounting/service.py`
- Test: `backend/tests/test_gpu_accounting_submit.py`

**Interfaces:**
- Consumes: `AccessUsageApiClient.post_compute(list[ComputeUsageRecord]) -> list[UsageRecordError]`, `.loaded(since) -> list[UsageLoadedRecord]`, `.status(from, to) -> list[UsageStatusResource]`, `.api_key`, `MAX_RECORDS_PER_POST`, `UsageApiError`, `iso_utc` (Task 3); `amieclient.usage.ComputeUsageRecord`; `sync_ledger` (Task 5).
- Produces: `GpuAccountingService.submit_pending(db) -> dict[str, int]` (keys `submitted`, `failed`); `reconcile(db) -> dict[str, int]` (keys `loaded`, `load_failed`); `run_cycle(db) -> dict[str, int]` (all keys from sync/submit/reconcile, zeros when skipped).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_gpu_accounting_submit.py`:

```python
"""Tests for submitting GPU usage to ACCESS and reconciling load status."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from amieclient.usage import ComputeUsageRecord, UsageLoadedRecord, UsageMessage
from amieclient.usage.message import UsageMessageError
from amieclient.usage.response import UsageStatusResource

from app.models.gpu_usage_record import GpuUsageRecord
from app.services.aime.usage_api import UsageApiError
from app.services.gpu_accounting.service import GpuAccountingService
from tests.gpu_accounting_support import (
    GPU,
    FakeAccountingClient,
    FakeUsageClient,
    gpu_project,
)


def _record(db, project, **overrides):
    defaults = {
        "project_id": project.id,
        "usage_date": date(2026, 10, 2),
        "username": "alice_nrp",
        "attribution": GpuUsageRecord.ATTRIBUTION_MEMBER,
        "gpu_hours": Decimal("2.5"),
        "charge": Decimal("2.5"),
        "local_record_id": f"nrp-gpu-p.gpu1-20261002-{overrides.get('username', 'alice_nrp')}",
        "status": GpuUsageRecord.STATUS_PENDING,
        "attempts": 0,
    }
    defaults.update(overrides)
    record = GpuUsageRecord(**defaults)
    db.add(record)
    db.commit()
    return record


def _submitted(db, project, charge="2.5", **overrides):
    return _record(
        db,
        project,
        status=GpuUsageRecord.STATUS_SUBMITTED,
        submitted_charge=Decimal(charge),
        submitted_at=datetime.now(UTC) - timedelta(hours=2),
        **overrides,
    )


def _loaded(record, charge=2.5, resource=GPU):
    return UsageLoadedRecord(
        accounting_db_record_id="134919900",
        local_record_id=record.local_record_id,
        resource=resource,
        submit_time="2026-10-02T00:00:00+00:00",
        loaded_time="2026-10-08T01:00:00+00:00",
        charge=charge,
    )


def _status_error(record, message):
    failed = ComputeUsageRecord(
        username=record.username,
        local_project_id="p.gpu1",
        local_record_id=record.local_record_id,
        resource=GPU,
        submit_time="2026-10-02T00:00:00Z",
        start_time="2026-10-02T00:00:00Z",
        end_time="2026-10-03T00:00:00Z",
        charge="2.5",
        node_count=1,
    )
    return UsageStatusResource(
        resource=GPU,
        loaded_record_count=0,
        failed_job_count=1,
        total_charge=0,
        errors=[UsageMessageError(message, UsageMessage([failed]))],
    )


def _service(usage=None):
    usage = usage or FakeUsageClient()
    return GpuAccountingService(
        accounting_client=FakeAccountingClient(date(2026, 10, 7)),
        usage_client=usage,
    ), usage


def test_submit_posts_compute_record(db, make_project):
    project = gpu_project(db, make_project)
    record = _record(db, project)
    service, usage = _service()

    assert service.submit_pending(db) == {"submitted": 1, "failed": 0}

    [[sent]] = usage.posts
    assert isinstance(sent, ComputeUsageRecord)
    assert sent.as_dict() == {
        "Username": "alice_nrp",
        "LocalProjectID": "p.gpu1",
        "LocalRecordID": record.local_record_id,
        "LocalReference": str(record.id),
        "Resource": GPU,
        "SubmitTime": "2026-10-02T00:00:00Z",
        "StartTime": "2026-10-02T00:00:00Z",
        "EndTime": "2026-10-03T00:00:00Z",
        "Charge": "2.500000",
        "Attributes": {"NodeCount": 1, "Queue": "gpu", "JobName": "nrp-gpu-daily"},
    }
    assert record.status == GpuUsageRecord.STATUS_SUBMITTED
    assert record.submitted_charge == Decimal("2.5")
    assert record.submitted_at is not None
    assert record.attempts == 1


def test_submit_batches_at_max_records(db, make_project, monkeypatch):
    from app.services.gpu_accounting import service as service_module

    monkeypatch.setattr(service_module, "MAX_RECORDS_PER_POST", 2)
    project = gpu_project(db, make_project)
    for i in range(5):
        _record(db, project, username=f"u{i}")
    service, usage = _service()

    assert service.submit_pending(db) == {"submitted": 5, "failed": 0}
    assert [len(batch) for batch in usage.posts] == [2, 2, 1]


def test_validation_failure_marks_failed_and_is_retried(db, make_project):
    project = gpu_project(db, make_project)
    record = _record(db, project)
    service, usage = _service()
    usage.validation_errors = {record.local_record_id: "Unknown user"}

    assert service.submit_pending(db) == {"submitted": 0, "failed": 1}
    assert record.status == GpuUsageRecord.STATUS_FAILED
    assert record.last_error == "Unknown user"

    usage.validation_errors = {}
    assert service.submit_pending(db) == {"submitted": 1, "failed": 0}
    assert record.status == GpuUsageRecord.STATUS_SUBMITTED
    assert record.attempts == 2


def test_api_error_marks_batch_failed(db, make_project):
    project = gpu_project(db, make_project)
    record = _record(db, project)
    service, usage = _service()
    usage.post_error = UsageApiError("ACCESS usage POST failed: Bad XA-SITE")

    assert service.submit_pending(db) == {"submitted": 0, "failed": 1}
    assert record.status == GpuUsageRecord.STATUS_FAILED
    assert "Bad XA-SITE" in record.last_error


def test_unsendable_records_are_skipped(db, make_project):
    project = gpu_project(db, make_project)
    _record(db, project, username="", attribution=GpuUsageRecord.ATTRIBUTION_PI)
    _record(db, project, username="zero", gpu_hours=Decimal("0"), charge=Decimal("0"))
    service, usage = _service()

    assert service.submit_pending(db) == {"submitted": 0, "failed": 0}
    assert usage.posts == []


def test_zeroed_previously_sent_record_is_resent(db, make_project):
    project = gpu_project(db, make_project)
    _record(db, project, gpu_hours=Decimal("0"), charge=Decimal("0"), submitted_charge=Decimal("2.5"))
    service, usage = _service()

    assert service.submit_pending(db) == {"submitted": 1, "failed": 0}
    assert usage.posts[0][0].charge == "0.000000"


def test_reconcile_marks_loaded_when_charge_matches(db, make_project):
    project = gpu_project(db, make_project)
    record = _submitted(db, project)
    service, usage = _service()
    usage.loaded_records = [_loaded(record)]

    assert service.reconcile(db) == {"loaded": 1, "load_failed": 0}
    assert record.status == GpuUsageRecord.STATUS_LOADED
    assert record.accounting_db_record_id == "134919900"
    assert record.loaded_at is not None


def test_reconcile_ignores_stale_charge_and_other_resources(db, make_project):
    project = gpu_project(db, make_project)
    record = _submitted(db, project, charge="3.0")
    service, usage = _service()
    usage.loaded_records = [_loaded(record, charge=2.5), _loaded(record, charge=3.0, resource="other")]

    assert service.reconcile(db) == {"loaded": 0, "load_failed": 0}
    assert record.status == GpuUsageRecord.STATUS_SUBMITTED


def test_reconcile_marks_status_errors_failed(db, make_project):
    project = gpu_project(db, make_project)
    record = _submitted(db, project)
    service, usage = _service()
    usage.status_resources = [
        _status_error(record, "Allocation could not be found for user alice_nrp")
    ]

    assert service.reconcile(db) == {"loaded": 0, "load_failed": 1}
    assert record.status == GpuUsageRecord.STATUS_FAILED
    assert "Allocation could not be found" in record.last_error


def test_reconcile_loaded_wins_and_status_failure_is_tolerated(db, make_project):
    project = gpu_project(db, make_project)
    record = _submitted(db, project)
    service, usage = _service()
    usage.loaded_records = [_loaded(record)]
    usage.status_error = UsageApiError("ACCESS usage/status failed: KeyError")

    assert service.reconcile(db) == {"loaded": 1, "load_failed": 0}
    assert record.status == GpuUsageRecord.STATUS_LOADED


def test_run_cycle_without_api_key_only_syncs(db, make_project):
    project = gpu_project(db, make_project)
    _record(db, project)
    service, usage = _service(FakeUsageClient(api_key=""))

    counters = service.run_cycle(db)

    assert usage.posts == []
    assert counters["submitted"] == 0
    assert counters["projects"] == 1


def test_run_cycle_submits_and_reconciles(db, make_project):
    project = gpu_project(db, make_project)
    _record(db, project)
    service, usage = _service()

    counters = service.run_cycle(db)

    assert counters["submitted"] == 1
    assert len(usage.posts) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_gpu_accounting_submit.py -v --tb=short`
Expected: FAIL — `AttributeError: 'GpuAccountingService' object has no attribute 'submit_pending'`.

- [ ] **Step 3: Implement submit, reconcile, run_cycle**

In `backend/app/services/gpu_accounting/service.py`, change the imports:

```python
from datetime import UTC, date, datetime, time, timedelta
```

```python
from amieclient.usage import ComputeUsageRecord
from sqlalchemy.orm import Session
```

```python
from app.services.aime.usage_api import (
    MAX_RECORDS_PER_POST,
    AccessUsageApiClient,
    UsageApiError,
    iso_utc,
)
```

Add a module-level helper after `DesiredRecords`:

```python
def _as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; treat them as UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
```

Append these methods to `GpuAccountingService`:

```python
    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def _compute_record(self, record: GpuUsageRecord) -> ComputeUsageRecord:
        """Build one ACCESS Compute usage record (a whole UTC day) for a ledger row."""
        start = datetime.combine(record.usage_date, time.min, tzinfo=UTC)
        return ComputeUsageRecord(
            username=record.username,
            local_project_id=record.project.site_project_id,
            local_record_id=record.local_record_id,
            local_reference=str(record.id),
            resource=self.resource,
            submit_time=iso_utc(start),
            start_time=iso_utc(start),
            end_time=iso_utc(start + timedelta(days=1)),
            charge=str(Decimal(record.charge).quantize(QUANT)),
            node_count=1,
            queue="gpu",
            job_name="nrp-gpu-daily",
        )

    def submit_pending(self, db: Session) -> dict[str, int]:
        """POST pending and failed ledger rows to ACCESS as Compute records."""
        counters = {"submitted": 0, "failed": 0}
        candidates = (
            db.query(GpuUsageRecord)
            .filter(
                GpuUsageRecord.status.in_(
                    [GpuUsageRecord.STATUS_PENDING, GpuUsageRecord.STATUS_FAILED]
                ),
                GpuUsageRecord.username != "",
            )
            .order_by(GpuUsageRecord.usage_date, GpuUsageRecord.local_record_id)
            .all()
        )
        # Zero-charge rows are only sent to overwrite a previously sent charge.
        sendable = [
            record
            for record in candidates
            if Decimal(record.charge) > 0 or record.submitted_charge is not None
        ]

        for offset in range(0, len(sendable), MAX_RECORDS_PER_POST):
            batch = sendable[offset : offset + MAX_RECORDS_PER_POST]
            now = datetime.now(UTC)
            try:
                failures = self.usage.post_compute([self._compute_record(r) for r in batch])
            except UsageApiError as exc:
                logger.error("ACCESS usage POST failed for %d records: %s", len(batch), exc)
                for record in batch:
                    record.status = GpuUsageRecord.STATUS_FAILED
                    record.last_error = str(exc)
                    record.attempts = (record.attempts or 0) + 1
                counters["failed"] += len(batch)
                db.commit()
                continue

            errors = {
                str(failure.record.local_record_id): str(failure.error or "validation failed")
                for failure in failures
            }
            for record in batch:
                record.attempts = (record.attempts or 0) + 1
                if record.local_record_id in errors:
                    record.status = GpuUsageRecord.STATUS_FAILED
                    record.last_error = errors[record.local_record_id]
                    counters["failed"] += 1
                else:
                    record.status = GpuUsageRecord.STATUS_SUBMITTED
                    record.submitted_charge = record.charge
                    record.submitted_at = now
                    record.loaded_at = None
                    record.accounting_db_record_id = None
                    record.last_error = None
                    counters["submitted"] += 1
            db.commit()
        return counters

    # ------------------------------------------------------------------
    # Reconcile
    # ------------------------------------------------------------------

    def reconcile(self, db: Session) -> dict[str, int]:
        """Mark submitted rows loaded/failed using ACCESS load status."""
        counters = {"loaded": 0, "load_failed": 0}
        submitted = (
            db.query(GpuUsageRecord)
            .filter(GpuUsageRecord.status == GpuUsageRecord.STATUS_SUBMITTED)
            .all()
        )
        if not submitted:
            return counters

        now = datetime.now(UTC)
        since = min(_as_utc(r.submitted_at) if r.submitted_at else now for r in submitted)
        since -= timedelta(hours=1)
        by_id = {record.local_record_id: record for record in submitted}

        try:
            loaded = self.usage.loaded(since)
        except UsageApiError:
            logger.exception("ACCESS usage/loaded reconcile failed")
            loaded = []
        try:
            statuses = self.usage.status(since, now)
        except UsageApiError:
            logger.exception("ACCESS usage/status reconcile failed")
            statuses = []

        # Loaded wins: process it first so a stale status error can't override it.
        for item in loaded:
            record = by_id.get(str(item.local_record_id))
            if record is None or record.status != GpuUsageRecord.STATUS_SUBMITTED:
                continue
            if str(item.resource or self.resource) != self.resource:
                continue
            try:
                charge = Decimal(str(item.charge)).quantize(QUANT)
            except ArithmeticError:
                continue
            if record.submitted_charge is None or charge != Decimal(
                record.submitted_charge
            ).quantize(QUANT):
                continue
            record.status = GpuUsageRecord.STATUS_LOADED
            record.accounting_db_record_id = (
                str(item.accounting_db_record_id) if item.accounting_db_record_id else None
            )
            record.loaded_at = now
            record.last_error = None
            counters["loaded"] += 1

        for resource in statuses:
            if str(resource.resource or self.resource) != self.resource:
                continue
            for error in resource.errors:
                message = str(error.error or "load failed")
                for failed in error.message.records:
                    record = by_id.get(str(failed.local_record_id))
                    if record is None or record.status != GpuUsageRecord.STATUS_SUBMITTED:
                        continue
                    record.status = GpuUsageRecord.STATUS_FAILED
                    record.last_error = message
                    counters["load_failed"] += 1

        db.commit()
        return counters

    # ------------------------------------------------------------------
    # Cycle
    # ------------------------------------------------------------------

    def run_cycle(self, db: Session) -> dict[str, int]:
        """Sync the ledger, then submit and reconcile when an API key is set."""
        counters = {
            "projects": 0,
            "rows": 0,
            "dropped": 0,
            "records_changed": 0,
            "submitted": 0,
            "failed": 0,
            "loaded": 0,
            "load_failed": 0,
        }
        counters.update(self.sync_ledger(db))
        if not self.usage.api_key:
            logger.warning(
                "AMIE_API_KEY is not configured; GPU usage ledger updated "
                "without submitting to ACCESS."
            )
            return counters
        counters.update(self.submit_pending(db))
        counters.update(self.reconcile(db))
        logger.info("GPU accounting cycle complete: %s", counters)
        return counters
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_gpu_accounting_submit.py tests/test_gpu_accounting_sync.py -v --tb=short`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/gpu_accounting/service.py backend/tests/test_gpu_accounting_submit.py
git commit -m "feat: submit GPU usage to ACCESS and reconcile load status

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Rewire the usage worker and remove the ClickHouse path

**Files:**
- Modify: `backend/workers/usage_worker.py`
- Delete: `backend/app/services/aime/usage_service.py`, `backend/app/services/clickhouse/` (whole directory)
- Modify: `backend/requirements.txt` (remove `clickhouse-connect>=0.7.0`)
- Test: `backend/tests/test_usage_worker.py`

**Interfaces:**
- Consumes: `GpuAccountingService.run_cycle(db) -> dict[str, int]` (Task 6).
- Produces: `workers.usage_worker.run_once(service) -> dict[str, int]` (one cycle with status updates), used by `run_worker`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_usage_worker.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_usage_worker.py -v --tb=short`
Expected: FAIL — `AttributeError: module 'workers.usage_worker' has no attribute 'run_once'`.

- [ ] **Step 3: Rewrite the worker**

Replace `backend/workers/usage_worker.py` with:

```python
"""GPU usage export worker.

Each cycle pulls daily GPU usage for GPU allocations from the NRP accounting
public API, records it in ``gpu_usage_records``, submits it to the ACCESS
Usage API, and reconciles what ACCESS has loaded.
"""

import logging
import time
from datetime import UTC, datetime

from app.config import settings
from app.database import SessionLocal
from app.services.gpu_accounting.service import GpuAccountingService
from app.services.observability import ObservabilityService
from app.services.worker_status import WorkerStatusService

logger = logging.getLogger(__name__)
WORKER_NAME = "usage-worker"


def _update_worker_status(
    *,
    is_active: bool,
    current_state: str,
    status_message: str | None = None,
    state_payload: dict | None = None,
    mark_success: bool = False,
    mark_error: bool = False,
) -> None:
    """Write worker heartbeat/state to DB."""
    try:
        with SessionLocal() as db:
            WorkerStatusService.update_status(
                db,
                worker_name=WORKER_NAME,
                is_active=is_active,
                current_state=current_state,
                status_message=status_message,
                state_payload=state_payload,
                mark_success=mark_success,
                mark_error=mark_error,
            )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to update %s status", WORKER_NAME)


def _evaluate_alerts() -> None:
    with SessionLocal() as alert_db:
        ObservabilityService.evaluate_alerts(alert_db)


def run_once(service: GpuAccountingService) -> dict[str, int]:
    """Run one GPU accounting cycle and record worker status."""
    _update_worker_status(
        is_active=True,
        current_state="collecting_gpu_usage",
        status_message="collecting GPU usage and reporting to ACCESS",
    )
    with SessionLocal() as db:
        result = service.run_cycle(db)
    _update_worker_status(
        is_active=True,
        current_state="idle",
        status_message=(
            "GPU usage cycle completed"
            if settings.amie_api_key
            else "GPU usage collected; AMIE_API_KEY not configured so nothing was submitted"
        ),
        state_payload={
            **result,
            "last_successful_usage_export_at": datetime.now(UTC).isoformat(),
        },
        mark_success=True,
    )
    _evaluate_alerts()
    return result


def run_worker(poll_interval: int | None = None) -> None:
    """Run the GPU usage export loop indefinitely."""
    interval_seconds = poll_interval or (settings.amie_usage_interval_minutes * 60)
    service = GpuAccountingService()

    if not settings.amie_api_key:
        logger.warning(
            "AMIE_API_KEY is not configured; GPU usage will be collected but not submitted."
        )

    logger.info(
        "GPU usage worker started (site=%s accounting_api=%s usage_url=%s resource=%s interval=%ss)",
        settings.amie_site_name,
        settings.nrp_accounting_api_url,
        settings.amie_usage_url,
        settings.amie_gpu_resource_name,
        interval_seconds,
    )

    _update_worker_status(
        is_active=True,
        current_state="starting",
        status_message="worker starting",
    )

    try:
        while True:
            try:
                run_once(service)
            except Exception as exc:  # noqa: BLE001
                _update_worker_status(
                    is_active=True,
                    current_state="error",
                    status_message=str(exc),
                    mark_error=True,
                )
                logger.exception("GPU usage worker error")

            time.sleep(interval_seconds)
    finally:
        _update_worker_status(
            is_active=False,
            current_state="stopped",
            status_message="worker stopped",
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_worker()
```

- [ ] **Step 4: Delete replaced code and dependency**

```bash
git rm -r backend/app/services/clickhouse backend/app/services/aime/usage_service.py
```

In `backend/requirements.txt` delete the line `clickhouse-connect>=0.7.0`.

Verify nothing references them:

Run: `cd backend && grep -rn "clickhouse\|usage_service\|AMIEUsageService\|amie_usage_default_username" app workers tests`
Expected: no output.

- [ ] **Step 5: Run the full suite**

Run: `cd backend && ../.venv/bin/python -m pytest tests/ -v --tb=short`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/workers/usage_worker.py backend/requirements.txt backend/tests/test_usage_worker.py
git commit -m "feat: run GPU accounting in usage worker; drop direct ClickHouse export

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: GPU accounting summary in the projects API

**Files:**
- Create: `backend/app/services/gpu_accounting/summary.py`
- Modify: `backend/app/schemas/project.py` (add `GpuAccountingSummary` before `ProjectRead`; fields on `ProjectRead` and `ProjectSummary`)
- Modify: `backend/app/api/projects.py:163-325, 451, 522`
- Test: `backend/tests/test_gpu_accounting_summary.py`

**Interfaces:**
- Consumes: `GpuUsageRecord` (Task 1), `is_gpu_project` (Task 4).
- Produces: schema `GpuAccountingSummary(gpu_hours_used: float, su_loaded: float, su_submitted: float, su_pending: float, su_failed: float, failed_records: int, usage_through: date | None, last_loaded_at: datetime | None)`; `ProjectRead.gpu_accounting: GpuAccountingSummary | None`; `ProjectSummary.total_gpu_su_used: float`, `ProjectSummary.total_gpu_su_loaded: float`; `gpu_accounting_summaries(db, projects) -> dict[uuid.UUID, GpuAccountingSummary]`; `gpu_accounting_totals(db) -> tuple[float, float]`. JSON shape consumed by Task 9: `project.gpu_accounting.{gpu_hours_used, su_loaded, su_submitted, su_pending, su_failed, failed_records, usage_through, last_loaded_at}`, `summary.{total_gpu_su_used, total_gpu_su_loaded}`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_gpu_accounting_summary.py`:

```python
"""Tests for GPU accounting aggregates exposed by the projects API."""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.api.projects import list_projects
from app.models.gpu_usage_record import GpuUsageRecord
from app.services.gpu_accounting.summary import (
    gpu_accounting_summaries,
    gpu_accounting_totals,
)
from tests.gpu_accounting_support import gpu_project


def _add(db, project, day, username, hours, status, loaded_at=None):
    db.add(
        GpuUsageRecord(
            project_id=project.id,
            usage_date=day,
            username=username,
            attribution=GpuUsageRecord.ATTRIBUTION_MEMBER,
            gpu_hours=Decimal(hours),
            charge=Decimal(hours),
            local_record_id=f"{project.id}-{day}-{username}",
            status=status,
            attempts=1,
            loaded_at=loaded_at,
        )
    )
    db.commit()


def test_summaries_split_by_status(db, make_project):
    project = gpu_project(db, make_project)
    loaded_at = datetime(2026, 10, 7, 12, tzinfo=UTC)
    _add(db, project, date(2026, 10, 1), "a", "10", GpuUsageRecord.STATUS_LOADED, loaded_at)
    _add(db, project, date(2026, 10, 2), "a", "4", GpuUsageRecord.STATUS_SUBMITTED)
    _add(db, project, date(2026, 10, 3), "a", "2", GpuUsageRecord.STATUS_PENDING)
    _add(db, project, date(2026, 10, 4), "a", "1", GpuUsageRecord.STATUS_FAILED)

    summary = gpu_accounting_summaries(db, [project])[project.id]

    assert summary.gpu_hours_used == 17.0
    assert summary.su_loaded == 10.0
    assert summary.su_submitted == 4.0
    assert summary.su_pending == 2.0
    assert summary.su_failed == 1.0
    assert summary.failed_records == 1
    assert summary.usage_through == date(2026, 10, 4)
    assert summary.last_loaded_at.replace(tzinfo=UTC) == loaded_at


def test_gpu_project_without_records_gets_zero_summary(db, make_project):
    project = gpu_project(db, make_project)
    summary = gpu_accounting_summaries(db, [project])[project.id]
    assert summary.gpu_hours_used == 0.0
    assert summary.usage_through is None


def test_non_gpu_projects_have_no_summary(db, make_project):
    project = make_project(db, allocated_resource="nrp-classroom.access-ci.org")
    assert gpu_accounting_summaries(db, [project]) == {}


def test_totals(db, make_project):
    project = gpu_project(db, make_project)
    _add(db, project, date(2026, 10, 1), "a", "10", GpuUsageRecord.STATUS_LOADED)
    _add(db, project, date(2026, 10, 2), "a", "4", GpuUsageRecord.STATUS_SUBMITTED)

    assert gpu_accounting_totals(db) == (14.0, 10.0)


def test_list_projects_includes_gpu_accounting(db, make_project):
    gpu = gpu_project(db, make_project)
    other = make_project(db, allocated_resource="nrp-classroom.access-ci.org")
    _add(db, gpu, date(2026, 10, 1), "a", "5", GpuUsageRecord.STATUS_LOADED)

    projects = {p.id: p for p in list_projects(include_debug=False, db=db)}

    assert projects[gpu.id].gpu_accounting.su_loaded == 5.0
    assert projects[other.id].gpu_accounting is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_gpu_accounting_summary.py -v --tb=short`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.gpu_accounting.summary'`.

- [ ] **Step 3: Add schemas**

In `backend/app/schemas/project.py`, insert before `class ProjectRead`:

```python
class GpuAccountingSummary(BaseModel):
    """GPU-hour usage (1 GPU-hour = 1 SU) and ACCESS reporting status."""

    gpu_hours_used: float = 0.0
    su_loaded: float = 0.0
    su_submitted: float = 0.0
    su_pending: float = 0.0
    su_failed: float = 0.0
    failed_records: int = 0
    usage_through: date | None = None
    last_loaded_at: datetime | None = None
```

In `ProjectRead`, add after `usage_last_collected_at: datetime | None = None`:

```python
    gpu_accounting: GpuAccountingSummary | None = None
```

In `ProjectSummary`, add after `total_service_units_allocated: float = 0.0`:

```python
    total_gpu_su_used: float = 0.0
    total_gpu_su_loaded: float = 0.0
```

- [ ] **Step 4: Implement the summary service**

Create `backend/app/services/gpu_accounting/summary.py`:

```python
"""Aggregate the GPU usage ledger for API responses."""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.gpu_usage_record import GpuUsageRecord
from app.models.project import Project
from app.schemas.project import GpuAccountingSummary
from app.services.gpu_accounting.scope import is_gpu_project


def gpu_accounting_summaries(
    db: Session, projects: Iterable[Project]
) -> dict[uuid.UUID, GpuAccountingSummary]:
    """Return a summary per GPU project (non-GPU projects are omitted)."""
    summaries = {p.id: GpuAccountingSummary() for p in projects if is_gpu_project(p)}
    if not summaries:
        return {}

    rows = (
        db.query(
            GpuUsageRecord.project_id,
            GpuUsageRecord.status,
            func.coalesce(func.sum(GpuUsageRecord.gpu_hours), 0),
            func.coalesce(func.sum(GpuUsageRecord.charge), 0),
            func.count(GpuUsageRecord.id),
            func.max(GpuUsageRecord.usage_date),
            func.max(GpuUsageRecord.loaded_at),
        )
        .filter(GpuUsageRecord.project_id.in_(list(summaries)))
        .group_by(GpuUsageRecord.project_id, GpuUsageRecord.status)
        .all()
    )
    for project_id, status, hours, charge, count, max_date, max_loaded in rows:
        summary = summaries[project_id]
        summary.gpu_hours_used += float(hours or 0)
        charge = float(charge or 0)
        if status == GpuUsageRecord.STATUS_LOADED:
            summary.su_loaded += charge
        elif status == GpuUsageRecord.STATUS_SUBMITTED:
            summary.su_submitted += charge
        elif status == GpuUsageRecord.STATUS_FAILED:
            summary.su_failed += charge
            summary.failed_records += int(count or 0)
        else:
            summary.su_pending += charge
        if max_date is not None and (
            summary.usage_through is None or max_date > summary.usage_through
        ):
            summary.usage_through = max_date
        if max_loaded is not None and (
            summary.last_loaded_at is None or max_loaded > summary.last_loaded_at
        ):
            summary.last_loaded_at = max_loaded
    return summaries


def gpu_accounting_totals(db: Session) -> tuple[float, float]:
    """Return (total GPU SU used, total GPU SU loaded at ACCESS)."""
    used, loaded = db.query(
        func.coalesce(func.sum(GpuUsageRecord.charge), 0),
        func.coalesce(
            func.sum(
                case(
                    (
                        GpuUsageRecord.status == GpuUsageRecord.STATUS_LOADED,
                        GpuUsageRecord.charge,
                    ),
                    else_=0,
                )
            ),
            0,
        ),
    ).one()
    return float(used or 0), float(loaded or 0)
```

- [ ] **Step 5: Wire into the projects API**

In `backend/app/api/projects.py`:

1. Add imports:

```python
from app.schemas.project import (
    GpuAccountingSummary,
    ProjectRead,
    ProjectSummary,
    ProjectUpdate,
    ProjectUsage,
)
```

```python
from app.services.gpu_accounting.summary import (
    gpu_accounting_summaries,
    gpu_accounting_totals,
)
```

2. Change the `_to_project_read` signature and pass the summary through:

```python
def _to_project_read(
    db: Session,
    *,
    project: Project,
    accounting: AccountingService,
    gpu_summary: GpuAccountingSummary | None = None,
) -> ProjectRead:
```

and add `gpu_accounting=gpu_summary,` after `usage_last_collected_at=usage_last_collected_at,` in the `ProjectRead(...)` call.

3. Add a helper right after `_to_project_read`:

```python
def _to_single_project_read(
    db: Session,
    *,
    project: Project,
    accounting: AccountingService,
) -> ProjectRead:
    gpu_summary = gpu_accounting_summaries(db, [project]).get(project.id)
    return _to_project_read(
        db, project=project, accounting=accounting, gpu_summary=gpu_summary
    )
```

4. In `list_projects`, replace the return with:

```python
    gpu_summaries = gpu_accounting_summaries(db, visible_projects)
    return [
        _to_project_read(
            db,
            project=project,
            accounting=accounting,
            gpu_summary=gpu_summaries.get(project.id),
        )
        for project in visible_projects
    ]
```

5. Replace the three single-project calls (`get_project` at ~line 323, `update_project` at ~lines 451 and 522) `_to_project_read(db, project=project, accounting=accounting)` with `_to_single_project_read(db, project=project, accounting=accounting)`.

6. In `get_projects_summary`, before `return ProjectSummary(`, add:

```python
    gpu_su_used, gpu_su_loaded = gpu_accounting_totals(db)
```

and add to the `ProjectSummary(...)` arguments:

```python
        total_gpu_su_used=gpu_su_used,
        total_gpu_su_loaded=gpu_su_loaded,
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && ../.venv/bin/python -m pytest tests/ -v --tb=short`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/gpu_accounting/summary.py backend/app/schemas/project.py backend/app/api/projects.py backend/tests/test_gpu_accounting_summary.py
git commit -m "feat: expose GPU accounting summary on projects API

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Projects page UI

**Files:**
- Create: `frontend/src/components/GpuAccountingSummary.vue`
- Modify: `frontend/src/components/ProjectCard.vue` (replace the "Usage Source" row, lines 48-55)
- Modify: `frontend/src/components/ProjectDetail.vue` (after the 4-column grid's closing `</div>`, before the `provisioning_last_error` paragraph)
- Modify: `frontend/src/views/ProjectsView.vue` (summary defaults, `kpis`, KPI grid class at line 142)

**Interfaces:**
- Consumes: `project.gpu_accounting` and `summary.total_gpu_su_used/total_gpu_su_loaded` (Task 8).
- Produces: `<GpuAccountingSummary :accounting="object" :allocated="number|null" />`.

- [ ] **Step 1: Create the component**

Create `frontend/src/components/GpuAccountingSummary.vue`:

```vue
<template>
  <div class="space-y-2 rounded-xl border border-violet-100 bg-violet-50 p-3">
    <div class="flex items-baseline justify-between gap-2">
      <p class="m-0 text-xs uppercase tracking-wide text-violet-600">GPU Hours Used (SU)</p>
      <p class="m-0 text-xs text-violet-500">
        data through {{ formatDate(accounting.usage_through) }}
      </p>
    </div>
    <p class="m-0 text-2xl font-bold text-violet-800">
      {{ formatUnits(accounting.gpu_hours_used) }}
      <span v-if="hasAllocation" class="text-sm font-medium text-violet-600">
        / {{ formatUnits(allocated) }}
      </span>
    </p>
    <ProgressBar
      v-if="hasAllocation"
      :value="percentUsed"
      :showValue="false"
      style="height: 0.5rem"
    />
    <div class="grid grid-cols-2 gap-2 text-xs">
      <div>
        <p class="m-0 text-slate-500">Loaded at ACCESS</p>
        <p class="m-0 font-semibold text-emerald-700">{{ formatUnits(accounting.su_loaded) }}</p>
      </div>
      <div>
        <p class="m-0 text-slate-500">Awaiting confirmation</p>
        <p class="m-0 font-semibold text-sky-700">{{ formatUnits(accounting.su_submitted) }}</p>
      </div>
    </div>
    <div
      v-if="accounting.su_pending > 0 || accounting.failed_records > 0"
      class="flex flex-wrap gap-2"
    >
      <Tag
        v-if="accounting.su_pending > 0"
        :value="`${formatUnits(accounting.su_pending)} SU not yet sent`"
        severity="secondary"
        rounded
      />
      <Tag
        v-if="accounting.failed_records > 0"
        :value="`${formatUnits(accounting.su_failed)} SU failed (${accounting.failed_records} records)`"
        severity="danger"
        rounded
      />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import ProgressBar from 'primevue/progressbar'
import Tag from 'primevue/tag'

const props = defineProps({
  accounting: {
    type: Object,
    required: true,
  },
  allocated: {
    type: Number,
    default: null,
  },
})

const hasAllocation = computed(() => Number(props.allocated || 0) > 0)

const percentUsed = computed(() => {
  if (!hasAllocation.value) return 0
  const used = Number(props.accounting.gpu_hours_used || 0)
  return Math.min(100, Math.round((used / Number(props.allocated)) * 100))
})

function formatUnits(value) {
  return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })
}

function formatDate(value) {
  if (!value) return '—'
  return new Date(`${value}T00:00:00Z`).toLocaleDateString(undefined, { timeZone: 'UTC' })
}
</script>
```

- [ ] **Step 2: Use it in ProjectCard**

In `frontend/src/components/ProjectCard.vue`, replace:

```vue
          <div class="flex items-center justify-between gap-2 text-xs">
            <span class="text-slate-500">Usage Source</span>
            <Tag
              :value="project.usage_source || 'none'"
              :severity="project.usage_source === 'usage_snapshot' ? 'info' : 'secondary'"
              rounded
            />
          </div>
```

with:

```vue
          <GpuAccountingSummary
            v-if="project.gpu_accounting"
            :accounting="project.gpu_accounting"
            :allocated="project.service_units_allocated"
          />
```

and add to the `<script setup>` imports:

```js
import GpuAccountingSummary from './GpuAccountingSummary.vue'
```

- [ ] **Step 3: Use it in ProjectDetail**

In `frontend/src/components/ProjectDetail.vue`, insert immediately before `<p v-if="project.provisioning_last_error"`:

```vue
      <GpuAccountingSummary
        v-if="project.gpu_accounting"
        class="mt-4"
        :accounting="project.gpu_accounting"
        :allocated="project.service_units_allocated"
      />
```

and add to imports:

```js
import GpuAccountingSummary from './GpuAccountingSummary.vue'
```

- [ ] **Step 4: Add KPIs to ProjectsView**

In `frontend/src/views/ProjectsView.vue`:

Change the summary default to:

```js
const summary = ref({
  active_projects: 0,
  total_service_units_allocated: 0,
  total_gpu_su_used: 0,
  total_gpu_su_loaded: 0,
})
```

Append to the `kpis` array (after the "Active Projects" entry):

```js
  {
    label: 'GPU SU Used',
    value: formatUsage(summary.value.total_gpu_su_used),
    icon: 'pi-microchip',
    iconClass: 'text-violet-600',
  },
  {
    label: 'GPU SU Loaded at ACCESS',
    value: formatUsage(summary.value.total_gpu_su_loaded),
    icon: 'pi-cloud-upload',
    iconClass: 'text-emerald-600',
  },
```

Change the KPI grid wrapper `<div class="grid grid-cols-1 gap-4 md:grid-cols-3">` (line 142) to:

```vue
    <div class="grid grid-cols-1 gap-4 md:grid-cols-3 xl:grid-cols-5">
```

- [ ] **Step 5: Build to verify**

Run: `cd frontend && npm run build`
Expected: build succeeds with no errors. (If `node_modules` is missing, run `npm install` first.)

- [ ] **Step 6: Visual check**

Start the backend with `AUTH_DEV_BYPASS=true` and the Vite dev server, insert a GPU project with a few `gpu_usage_records` rows (or point at a dev DB after one worker cycle), open `http://localhost:5173/` → Projects, and confirm the card shows GPU hours, the progress bar, "Loaded at ACCESS", and the two new KPI tiles; confirm non-GPU cards show no GPU block.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/GpuAccountingSummary.vue frontend/src/components/ProjectCard.vue frontend/src/components/ProjectDetail.vue frontend/src/views/ProjectsView.vue
git commit -m "feat: show GPU hours used and ACCESS-loaded SUs on projects page

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Deployment config and documentation

**Files:**
- Modify: `deployment/config/app.env`, `docker-compose.yml` (usage-worker service)
- Modify: `README.md`, `backend/README.md`, `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md`

**Interfaces:**
- Consumes: setting names from Task 1.

- [ ] **Step 1: Deployment config**

In `deployment/config/app.env`:
- change `AMIE_USAGE_URL=https://usage.xsede.org/api/v1` → `AMIE_USAGE_URL=https://usage.access-ci.org/api/v1`
- delete `AMIE_USAGE_DEFAULT_USERNAME=nrp-system`
- add after `AMIE_USAGE_GPU_CHARGE_FACTOR=1.0`:

```
AMIE_USAGE_RESTATEMENT_DAYS=7
AMIE_GPU_RESOURCE_NAME=pnrp.sdsc.access-ci.org
NRP_ACCOUNTING_API_URL=https://nrp-accounting-mcp.nrp-nautilus.io/openapi
```

In `docker-compose.yml` `usage-worker.environment`:
- change `AMIE_USAGE_URL: ${AMIE_USAGE_URL:-https://usage.xsede.org/api/v1}` → `AMIE_USAGE_URL: ${AMIE_USAGE_URL:-https://usage.access-ci.org/api/v1}`
- add after `AMIE_USAGE_INTERVAL_MINUTES: 1440`:

```yaml
      AMIE_GPU_RESOURCE_NAME: ${AMIE_GPU_RESOURCE_NAME:-pnrp.sdsc.access-ci.org}
      NRP_ACCOUNTING_API_URL: ${NRP_ACCOUNTING_API_URL:-https://nrp-accounting-mcp.nrp-nautilus.io/openapi}
```

Also run `grep -n "usage.xsede.org" docker-compose.yml` and update any other service's `AMIE_USAGE_URL` default the same way.

- [ ] **Step 2: README.md**

- Line ~27 table row `| Usage accounting | ClickHouse (\`access_accounting\` database) |` → `| Usage accounting | NRP accounting public API (ClickHouse \`access_accounting\`) |`.
- Line ~46 `│   │       ├── clickhouse/   # ClickHouse accounting queries (GPU usage)` → two lines:

```
│   │       ├── gpu_accounting/  # GPU-hour ledger sync, ACCESS submit + reconcile
│   │       ├── nrp_accounting/  # NRP accounting public API client
```

- Lines ~116-119 replace the ClickHouse export block with:

```bash
# GPU accounting (defaults shown)
export NRP_ACCOUNTING_API_URL=https://nrp-accounting-mcp.nrp-nautilus.io/openapi
export AMIE_GPU_RESOURCE_NAME=pnrp.sdsc.access-ci.org
```

- In the env table, delete the seven `CLICKHOUSE_*` rows and the `AMIE_USAGE_DEFAULT_USERNAME` row; replace the `AMIE_GPU_RESOURCE_NAME` row and `AMIE_USAGE_URL` row with:

```
| `NRP_ACCOUNTING_API_URL` | `https://nrp-accounting-mcp.nrp-nautilus.io/openapi` | NRP accounting public API (source of daily GPU hours) |
| `NRP_ACCOUNTING_API_TIMEOUT_SECONDS` | `120` | Timeout for accounting API calls |
| `AMIE_GPU_RESOURCE_NAME` | `pnrp.sdsc.access-ci.org` | Projects with this `allocated_resource` are GPU-hour allocations; also the usage record `Resource` |
| `AMIE_USAGE_URL` | `https://usage.access-ci.org/api/v1` | ACCESS Usage API base URL (test: `https://usage.access-ci.org/api/v1_test`) |
| `AMIE_USAGE_RESTATEMENT_DAYS` | `7` | Days re-fetched each cycle so restated usage is re-submitted |
```

- Lines ~229-230 replace the usage worker + ClickHouse bullets with:

```markdown
- The **Usage worker** (`workers/usage_worker.py`) runs `GpuAccountingService.run_cycle` (`services/gpu_accounting/service.py`) each interval:
  1. Pulls daily GPU hours for GPU allocations (`allocated_resource == AMIE_GPU_RESOURCE_NAME`) from the NRP accounting public API (`POST /query_resource_usage`, grouped by date × namespace × `created_by`).
  2. Attributes each row: a CILogon `created_by` must be a project member (`User.remote_site_login` → `ProjectUser.remote_site_login`), otherwise it is dropped; non-person creators (service accounts) are charged to the PI.
  3. Upserts `gpu_usage_records` (one row per project × day × AMIE username; 1 GPU-hour = 1 SU), catching up from `projects.gpu_usage_synced_through`.
  4. Submits pending/failed rows to the ACCESS Usage API as Compute records (≤ 1000 per POST) through `amieclient.UsageClient` (adapter in `services/aime/usage_api.py`) and reconciles them via `/usage/loaded` and `/usage/status`.
- `amieclient` is installed `--no-deps` from the pinned fork `djw8605/amieclient@1700828` (upstream PR xsede/amieclient#35) until upstream publishes a release with those fixes.
- The projects API exposes `gpu_accounting` (GPU hours used, SU loaded/submitted/pending/failed) per GPU project.
```

- [ ] **Step 3: backend/README.md**

Replace the "ClickHouse accounting integration…" bullet list under `## Recent Changes` (lines ~27-37) with:

```markdown
- GPU-hour accounting for `pnrp.sdsc.access-ci.org` allocations.
  - Source: NRP accounting public API (`app/services/nrp_accounting/client.py`); the direct ClickHouse client was removed.
  - Ledger: `gpu_usage_records` (project × day × AMIE username), status `pending → submitted → loaded | failed`.
  - Submission: Compute records (≤ 1000 per POST) via `amieclient.UsageClient`, wrapped by `app/services/aime/usage_api.py`. amieclient is installed from the pinned fork `djw8605/amieclient@1700828` (Compute `ParentRecordID` fix, `UsageClient.loaded()`, POSTs split under 256 KB, `usage.access-ci.org` default) until upstream releases it.
  - Attribution: project members by CILogon ID; non-person creators charged to the PI; non-member people dropped.
  - New env vars: `NRP_ACCOUNTING_API_URL`, `NRP_ACCOUNTING_API_TIMEOUT_SECONDS`, `AMIE_USAGE_RESTATEMENT_DAYS`; `AMIE_GPU_RESOURCE_NAME` now defaults to `pnrp.sdsc.access-ci.org`. Removed: `CLICKHOUSE_*`, `AMIE_USAGE_DEFAULT_USERNAME`.
```

Delete the `AMIE_USAGE_DEFAULT_USERNAME` row from its env table, and update its `AMIE_USAGE_URL` default if listed.

- [ ] **Step 4: AGENTS.md, CLAUDE.md, copilot instructions**

`AGENTS.md`:
- Domain table: replace the **ClickHouse** row with `| **NRP accounting API** | Public OpenAPI bridge over the ClickHouse accounting DB — source of per-user daily GPU hours for ACCESS export |`; in the **CILogon ID** row change "matched against `created_by` in ClickHouse" to "matched against `created_by` in the NRP accounting API".
- Replace the `## GPU Usage Export Pipeline` section body with:

````markdown
GPU hours for ACCESS reporting come from the **NRP accounting public API** (`NRP_ACCOUNTING_API_URL`), not Prometheus. Only projects with `allocated_resource == AMIE_GPU_RESOURCE_NAME` (`pnrp.sdsc.access-ci.org`) are reported.

```
NRP accounting API: POST /query_resource_usage (resource=gpu, group_by=date,namespace,created_by)
       │                         │
       ▼                         ▼
  Project.kubernetes_namespace   created_by
                                 ├─ CILogon URL → User.remote_site_login → ProjectUser (this project)
                                 │                   → ProjectUser.remote_site_login (AMIE Username)
                                 │                   (not a member → dropped)
                                 └─ anything else  → PI's ProjectUser.remote_site_login
                  │
          gpu_usage_records (project × day × username; 1 GPU-hour = 1 SU)
                  │  local_record_id = nrp-gpu-{site_project_id}-{YYYYMMDD}-{sha256(username)[:12]}
                  ▼
          amieclient.UsageClient (fork @1700828): POST /usage (Compute, ≤1000/batch) → /usage/loaded + /usage/status reconcile
```
````

- Environment table: replace the `CLICKHOUSE_*` row with `| \`NRP_ACCOUNTING_API_*\` | NRP accounting public API (GPU usage source) |`; replace the "ClickHouse key vars" paragraph with: `GPU accounting vars: \`NRP_ACCOUNTING_API_URL\`, \`AMIE_GPU_RESOURCE_NAME\` (default \`pnrp.sdsc.access-ci.org\`), \`AMIE_USAGE_URL\` (default \`https://usage.access-ci.org/api/v1\`), \`AMIE_USAGE_RESTATEMENT_DAYS\` (default \`7\`).`

`CLAUDE.md` Gotchas: replace the ClickHouse bullet with:

```markdown
- GPU usage for ACCESS export comes from the **NRP accounting public API** (`services/nrp_accounting/client.py`), not Prometheus or a direct ClickHouse connection. Only `pnrp.sdsc.access-ci.org` allocations are exported; the ledger is `gpu_usage_records`. Usage is POSTed through `amieclient.UsageClient` (adapter: `services/aime/usage_api.py`). amieclient must be installed `--no-deps` from the pinned fork `djw8605/amieclient@1700828` (see Dockerfile/CI); PyPI 0.6.1 sends `ParentRecordID: [null]` on Compute records and lacks `UsageClient.loaded()`. Switch back to PyPI once upstream (xsede/amieclient#35) releases.
```

`.github/copilot-instructions.md`: replace the "GPU usage export" bullet (line ~63) with the same text as the CLAUDE.md bullet; replace the seven `CLICKHOUSE_*` rows and the `AMIE_GPU_RESOURCE_NAME` row in its env table with the `NRP_ACCOUNTING_API_URL`, `AMIE_GPU_RESOURCE_NAME`, `AMIE_USAGE_RESTATEMENT_DAYS` rows from Step 2.

- [ ] **Step 5: Verify no stale references**

Run: `grep -rn -i "clickhouse_host\|CLICKHOUSE_\|usage.xsede.org\|AMIE_USAGE_DEFAULT_USERNAME\|services/clickhouse\|usage_service" README.md backend/README.md AGENTS.md CLAUDE.md .github deployment docker-compose.yml backend/app backend/workers`
Expected: no output.

Run: `cd backend && ../.venv/bin/python -m pytest tests/ -v --tb=short && cd ../frontend && npm run build`
Expected: all tests PASS; build succeeds.

- [ ] **Step 6: Commit**

```bash
git add deployment/config/app.env docker-compose.yml README.md backend/README.md AGENTS.md CLAUDE.md .github/copilot-instructions.md
git commit -m "docs: document GPU accounting pipeline and update usage config

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
