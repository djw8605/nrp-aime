# GPU Hour Accounting → ACCESS Usage API — Design

**Date:** 2026-10-08
**Status:** Approved (2026-10-08); amended for the amieclient fork pin `1700828` and 1000-record batches
**Branch:** `claude/gpu-accounting`

## Goal

Report GPU-hour usage for NRP **GPU allocations** to the ACCESS Usage API, sourced
from the NRP accounting data (ClickHouse, via its public OpenAPI bridge), and show on
the projects page how many GPU hours (1 GPU-hour = 1 SU) each project has used and how
much of that ACCESS has confirmed as loaded.

Classroom and any other allocation types are out of scope.

## Problems with the current pipeline

1. ClickHouse is not configured in production (`CLICKHOUSE_HOST` unset) — nothing is exported.
2. Every project with a namespace is exported; there is no filter to GPU allocations,
   and the AMIE `Resource` falls back to `Project.resource_type`.
3. `AMIE_USAGE_URL` points to the retired `usage.xsede.org`.
4. Only the previous day is queried; missed days are lost. Failed exports are inserted
   into the dedupe table and never retried.
5. Usage whose `created_by` doesn't match a `User` (e.g. service accounts) is silently dropped.
6. "Uploaded" means only that the POST returned; nothing reconciles with ACCESS.
7. The UI's "GPU used" is the last interval only, not a cumulative total.

## Scope rules

- A project is a **GPU allocation** iff `Project.allocated_resource == settings.amie_gpu_resource_name`
  (default `pnrp.sdsc.access-ci.org`). That string is also the `Resource` sent to ACCESS.
- A GPU project must have `site_project_id` and `kubernetes_namespace` to be processed.
- Charge = GPU-hours × `AMIE_USAGE_GPU_CHARGE_FACTOR` (default `1.0`, i.e. 1 GPU-hour = 1 SU).

## Components

### 1. NRP accounting API client — `app/services/nrp_accounting/client.py`

Replaces `app/services/clickhouse/` and the `clickhouse-connect` dependency.

- Base URL `NRP_ACCOUNTING_API_URL` (default `https://nrp-accounting-mcp.nrp-nautilus.io/openapi`),
  timeout `NRP_ACCOUNTING_API_TIMEOUT_SECONDS` (default `120`). No auth.
- `latest_data_date() -> date` — `POST /get_latest_data_date` with `{}`.
- `gpu_usage(namespaces, date_from, date_to) -> list[GpuUsageRow]` —
  `POST /query_resource_usage` with
  `{"start_date", "end_date", "namespace": [...], "resource": "gpu",
    "group_by": ["date", "namespace", "created_by"], "limit": 5000}`.
  If `row_count == limit`, bisect the date range and re-query (single-day ranges that
  still hit the cap are split by namespace chunks). `GpuUsageRow(namespace, created_by, date, gpu_hours: Decimal)`.
- Raises `NrpAccountingApiError` on HTTP / payload errors; the caller aborts the cycle
  (no partial ledger writes based on incomplete data).
- Uses `httpx.Client`; tests inject an `httpx.MockTransport`.

### 2. ACCESS Usage API adapter — `app/services/aime/usage_api.py`

Uses `amieclient.UsageClient`, installed `--no-deps` from the pinned fork
`https://github.com/djw8605/amieclient/archive/1700828b80fce7e5c97f690bc1a0f9b4c9ffd001.tar.gz`
(upstream PR xsede/amieclient#35) in the Dockerfile, CI, and the dev venv. The fork fixes
Compute `ParentRecordID` serialization (PyPI 0.6.1 sends `[null]`), adds `UsageClient.loaded()`,
splits POSTs over 192 KiB to stay under the guide's 256 KB limit, and defaults to
`https://usage.access-ci.org/api/v1` (`usage.xsede.org` fails TLS with an expired certificate).
Switch back to PyPI once upstream releases.

The thin `AccessUsageApiClient` adapter keeps batching, paging, and error handling in one
place so the service can be tested with fakes:

- `post_compute(records: list[ComputeUsageRecord]) -> list[UsageRecordError]` — at most
  `MAX_RECORDS_PER_POST = 1000` records per call (the guide: about 1,000 records fit in 256 KB);
  merges failures across any extra responses from the fork's chunking.
- `loaded(min_loaded_time) -> list[UsageLoadedRecord]` — pages `UsageClient.loaded()` by 25,000.
- `status(from_time, to_time) -> list[UsageStatusResource]`.
- Library, transport, and parse errors (`UsageResponseError`, `requests.RequestException`,
  `KeyError`, …) → `UsageApiError`.

Tests import the real fork: `tests/conftest.py` imports `amieclient.usage` before the per-module
`amieclient` placeholder stubs in older tests can be installed.

### 3. Ledger model — `gpu_usage_records` (migration `0022`)

One row per **(project, usage_date, username)**.

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| project_id | FK projects, indexed | |
| usage_date | Date, indexed | |
| username | String | AMIE `Username` |
| attribution | String | `member` \| `pi` |
| gpu_hours | Numeric(18,6) | summed for this key |
| charge | Numeric(18,6) | gpu_hours × factor |
| local_record_id | String, unique | `nrp-gpu-{site_project_id}-{YYYYMMDD}-{sha256(username)[:12]}` |
| status | String, indexed | `pending` \| `submitted` \| `loaded` \| `failed` |
| submitted_charge | Numeric(18,6) nullable | charge value last POSTed |
| last_error | Text nullable | |
| accounting_db_record_id | String nullable | from `/usage/loaded` |
| attempts | Integer default 0 | |
| submitted_at / loaded_at | DateTime(tz) nullable | |
| created_at / updated_at | DateTime(tz) | |

Unique constraint on `(project_id, usage_date, username)`. `amie_usage_exports` is left
in place (legacy, no longer written).

Same migration adds `projects.gpu_usage_synced_through: Date | None` (via `op.add_column`).

### 4. Attribution — `GpuUsageAttributor`

For each accounting row in a GPU project's namespace:

- **Human** (`created_by` matches `^https?://cilogon\.org/`): find `User.remote_site_login == created_by`
  that has a `ProjectUser` in *this* project with a non-empty `ProjectUser.remote_site_login`.
  Found → username = that login, attribution `member`. Not found → **drop** (logged, counted).
- **Non-human** (anything else: service accounts, `system:*`, empty): charge the PI —
  the project's `ProjectUser` with role `pi` (case-insensitive) and its `remote_site_login`;
  attribution `pi`. If the PI has no login yet → row stored as `pending` with
  `last_error="PI has no site login yet"` and retried each cycle (not dropped).

Rows mapping to the same (project, date, username) are summed.

### 5. Export cycle — `GpuAccountingService.run_cycle(db)` (rewrites `AMIEUsageService`)

1. `latest = api.latest_data_date()`.
2. For each GPU project: window = `[start_date or created_at.date(), min(end_date or latest, latest)]`.
   Fetch start per project = window start if `Project.gpu_usage_synced_through` is null (first
   sync / backfill), else `max(window start, gpu_usage_synced_through − AMIE_USAGE_RESTATEMENT_DAYS)`.
   Query from the earliest fetch start to `latest` for all GPU namespaces, then clip rows to each
   project's `[fetch start, window end]`. After a successful cycle set
   `gpu_usage_synced_through = latest` for each processed project — so worker downtime or API
   outages are caught up automatically.
3. Attribute and aggregate → desired `{(project, date, username): gpu_hours}`.
4. Upsert ledger rows:
   - new key → insert `pending`.
   - existing key with changed `gpu_hours` → update; if previously submitted/loaded,
     reset to `pending` (re-POST overwrites at ACCESS via same LocalRecordID/SubmitTime).
   - Only dates inside the fetched range are compared, so older ledger rows are never touched.
5. Send all `pending` and `failed` rows with charge > 0 (or a previously sent charge) as
   `amieclient.usage.ComputeUsageRecord`s, in batches of at most 1000:
   `SubmitTime = StartTime = {date}T00:00:00Z`, `EndTime = {date+1}T00:00:00Z`,
   `Charge = str(charge)`, `LocalProjectID = site_project_id`, `Resource = amie_gpu_resource_name`,
   `Username`, `LocalRecordID`, `LocalReference = ledger id`,
   `Attributes = {"NodeCount": 1, "Queue": "gpu", "JobName": "nrp-gpu-daily"}`.
   Accepted → `submitted` (store `submitted_charge`, `submitted_at`, `attempts += 1`);
   in `ValidationFailedRecords` → `failed` with error.
6. Reconcile:
   - `loaded(min_loaded_time = oldest submitted_at among submitted rows − 1h)`; match by
     `LocalRecordID` → `loaded`, store `AccountingDbRecordID`, `loaded_at`.
   - `status(from = same, to = now)`; any record in `Errors` still `submitted` → `failed` with error.
7. Return counters (`projects`, `rows`, `dropped`, `pending`, `submitted`, `loaded`, `failed`) for worker status.

If `AMIE_API_KEY` is empty, steps 1–4 still run (ledger reflects usage) but send/reconcile are skipped.
If the accounting API fails, the cycle aborts before touching the ledger.

### 6. API / schema

- `ProjectRead` gains a nested `gpu_accounting: GpuAccountingSummary | None` (null for non-GPU projects):
  `gpu_hours_used`, `su_loaded`, `su_submitted`, `su_pending`, `su_failed`, `failed_records`,
  `usage_through` (max `usage_date`), `last_loaded_at`.
- Computed for the list endpoint with one grouped aggregate query over `gpu_usage_records`
  (by project_id, status) — no per-project queries.
- `ProjectSummary` gains `total_gpu_su_used`, `total_gpu_su_loaded`.

### 7. Frontend

- New `GpuAccountingSummary.vue` component: GPU-hours used vs `service_units_allocated`
  (ProgressBar), "Loaded at ACCESS" SU, pending/submitted/failed SU tags, "data through <date>".
- `ProjectCard.vue`: render the component for GPU projects; remove the `usage_source` tag.
- `ProjectDetailView.vue`: render the same component in the overview.
- `ProjectsView.vue`: summary KPIs for total GPU SU used / loaded.

### 8. Config & deployment

- New: `NRP_ACCOUNTING_API_URL`, `NRP_ACCOUNTING_API_TIMEOUT_SECONDS`, `AMIE_USAGE_RESTATEMENT_DAYS`.
- Changed defaults: `AMIE_USAGE_URL=https://usage.access-ci.org/api/v1` (replaces the dead
  `usage.xsede.org` in `config.py`, `app.env`, `docker-compose.yml`, README),
  `AMIE_GPU_RESOURCE_NAME=pnrp.sdsc.access-ci.org`.
- Removed: `CLICKHOUSE_*`, `AMIE_USAGE_DEFAULT_USERNAME`; `clickhouse-connect` dependency.
- amieclient install source: PyPI → pinned fork (Dockerfile, `.github/workflows/test.yml`).
- Update `deployment/config/app.env`, `docker-compose.yml`, README, AGENTS.md, CLAUDE.md,
  `.github/copilot-instructions.md`.

## Error handling

- Accounting API down → cycle aborts, worker status `error`, ledger untouched.
- Usage API POST error (non-2xx) → affected batch rows stay `pending`/`failed` with `last_error`; retried next cycle.
- Reconcile errors are logged and do not undo submissions.

## Testing (pytest, in-memory SQLite)

- Accounting client: request shape, bisection on row cap, error handling (MockTransport).
- Usage API adapter: batch cap, failure merging, `/usage/loaded` paging, error wrapping, and one
  end-to-end POST through the real fork `UsageClient` (no `ParentRecordID`, `XA-*` headers).
- Attribution: member match, non-member human dropped, service account → PI, PI without login → pending.
- Cycle: GPU-only filter, project window clipping, aggregation per username, idempotent re-run,
  restatement resets to pending, failed rows retried, no-API-key mode.
- Reconcile: loaded → `loaded`; status errors → `failed`.
- API: `gpu_accounting` aggregates on list/detail; null for non-GPU projects; summary totals.
- Migration test covers `0022` upgrade/downgrade.
