# NRP AIME — Agent Baseline

## Project Overview

NRP AIME is an allocation management portal that bridges **ACCESS/XSEDE AMIE packets** to NRP's Kubernetes infrastructure. It receives allocation requests, provisions namespaces, onboards users via OAuth invites, and reports usage back to AMIE.

**Stack:**
- Backend: FastAPI + SQLAlchemy 2.0 + Alembic + PostgreSQL (Python 3.11)
- Frontend: Vue 3 (Composition API) + PrimeVue + TailwindCSS 4
- Workers: Two standalone Python background tasks (AIME poller, usage exporter)
- Infra: Docker Compose (dev) · Kubernetes + Kustomize (prod) · Argo CD (GitOps)
- Tests: pytest with in-memory SQLite (no live DB required)

**Key directories:**
```
backend/app/models/      SQLAlchemy ORM models (one file per model)
backend/app/schemas/     Pydantic request/response schemas
backend/app/api/         FastAPI routers (one file per resource)
backend/app/services/    Business logic (grouped by domain)
backend/migrations/      Alembic migrations (numbered 0001–)
backend/workers/         Background polling scripts
backend/tests/           pytest suite (conftest.py + test_*.py)
frontend/src/api/        Axios client modules (one file per domain)
frontend/src/components/ Reusable Vue components
frontend/src/views/      Page-level Vue views
deployment/              Kustomize manifests + SealedSecrets + ArgoCD
```

---

## CLI Commands

### Backend
```bash
# Dev server
uvicorn app.main:app --reload

# Tests
python -m pytest tests/ -v --tb=short

# Migrations
alembic upgrade head
alembic downgrade -1
alembic revision --autogenerate -m "feat: description"

# Workers (run as separate processes/containers)
python -m workers.aime_worker
python -m workers.usage_worker
```

### Frontend
```bash
npm install
npm run dev       # Vite dev server (http://localhost:5173)
npm run build     # Production build
npm run preview   # Serve production build locally
```

### Local dev stack
```bash
docker compose up           # All services
docker compose up --build   # Rebuild images first
docker compose run migrate  # Run Alembic migrations in container
```

### Kubernetes
```bash
kubectl apply -k deployment          # Deploy
kubectl kustomize deployment         # Preview manifests
```

---

## Coding Conventions

### Python

- **Models** hold state machine constants as class-level `UPPER_SNAKE_CASE` strings; `LIFECYCLE_STATES` tuple + `LIFECYCLE_STATE_TRANSITIONS` dict are the canonical source of truth.
- **New states** require: constant → tuple entry → transitions entry → migration.
- `set_lifecycle_state()` / `set_account_state()` validate against known states and update the timestamp; use them, not direct attribute assignment.
- Migrations are numbered `NNNN_slug.py`. Run autogenerate then inspect the output before committing.
- Services take a `Session` (not a router dependency) and contain all business logic. Routes are thin.
- Private helpers use a leading underscore: `_has_pending_pi_account()`.
- `from __future__ import annotations` is used in services that have forward references.
- `amieclient` is installed `--no-deps` to avoid its stale `python-dateutil<2.7` pin. Do not add it to `requirements.txt` with deps enabled.

### Vue / JavaScript

- All views are `<script setup>` Composition API. No Options API.
- API calls live in `src/api/<domain>.js` and return `res.data` directly.
- PrimeVue components are used for all UI elements — do not add a second component library.
- Tailwind utilities only; no inline `style=""` except for dynamic values.

### General

- Commit messages follow Conventional Commits: `feat:`, `fix:`, `test:`, `ci:`, `chore:`.
- Add `[skip deploy]` to automated commits that should not trigger the build-and-deploy workflow.
- No linter config exists — follow surrounding code style.

---

## Domain Terminology

| Term | Meaning |
|---|---|
| **AMIE** | AIME Message Interface Engine — packet protocol between sites and ACCESS |
| **AIME** | Allocation & Integrated Management Environment (the ACCESS system) |
| **NRP** | National Research Platform — primary site name (`AMIE_SITE_NAME=NRP`) |
| **PI** | Principal Investigator — project lead; their account must exist before `notify_project_create` is sent |
| **Project / Allocation** | A computational resource grant tracked by `aime_allocation_id` |
| **Packet** | An AMIE message (e.g. `request_project_create`, `notify_account_create`) |
| **Provisioning** | Creating a Kubernetes namespace + Authentik group via the NRP portal RPC |
| **Lifecycle state** | `Project.lifecycle_state` — the single authoritative project state |
| **Account state** | `ProjectUser.account_state` — per-user onboarding progression |
| **Service Units** | Standardized allocation currency (CPU/GPU); debit/credit model |
| **ClickHouse** | Time-series accounting DB — source of per-user GPU hours for AMIE export |
| **CILogon ID** | OAuth subject ID stored in `User.remote_site_login`; matched against `created_by` in ClickHouse |
| **Authentik** | Identity provider used for invite-based OAuth onboarding |
| **Portal RPC** | NRP portal JSON-RPC endpoint for namespace/membership provisioning |
| **SealedSecret** | Bitnami-encrypted K8s secret; commit the `.yaml`, never the plaintext |

---

## GPU Usage Export Pipeline

GPU hours for AMIE reporting come from **ClickHouse**, not Prometheus. Prometheus is only used for the live display endpoint `GET /api/v1/projects/{id}/usage`.

```
ClickHouse: access_accounting.cluster_namespace_usage_daily
  WHERE resource = 'gpu'
  GROUP BY (namespace, created_by, date)
       │                │
       ▼                ▼
  Project.kubernetes_namespace    User.remote_site_login   ← CILogon subject ID
       │                │
       └──── ProjectUser ────┘
                  │
          ProjectUser.remote_site_login  ← AMIE Username (HPC site login)
                  │
          AdjustmentUsageRecord (debit) → AMIE Usage API
                  │
          amie_usage_exports  ← idempotent; local_record_id = nrp-gpu-{project_id}-{YYYYMMDD}-{sha256(cilogon)[:12]}
```

**Identity field semantics** — do not confuse:
- `User.remote_site_login` — CILogon subject ID (set during OAuth invite callback)
- `ProjectUser.remote_site_login` — HPC/site login sent as AMIE `Username`

---

## State Machines

### Project lifecycle (ordered)
```
received → pending_provisioning → provisioning → provisioned
  └─(pi project)→ waiting_pi_account → provisioned
provisioned → aime_notified → active ↔ inactive
provisioning → provisioning_failed → provisioning (retry)
```

### ProjectUser account (ordered)
```
received → email_invite_sent → user_completed_oauth → aime_notified   (regular user)
                                                     → covered_by_project_notification  (PI)
```

---

## Feature Workflow

**Adding a model field:**
1. Add `Mapped[T]` column to model
2. `alembic revision --autogenerate -m "feat: add <field>"` — inspect output
3. Add field to the relevant Pydantic schema
4. Update service logic if needed

**Adding a new state:**
1. Add constant + tuple + transitions entry in model
2. Add migration (manual `op.execute` to backfill existing rows)
3. Update service methods that drive that transition
4. Update frontend severity/label maps in the relevant View/Component

**New API endpoint:**
1. Service method first (business logic, tested in isolation)
2. Route in `app/api/<resource>.py` calling the service
3. Register router in `app/main.py` if it's a new file

**PR checklist:**
- `python -m pytest tests/ -v` passes
- Migration reviewed (upgrade + downgrade)
- No hardcoded secrets
- Conventional Commit message

---

## Environment / Config

All config lives in `backend/app/config.py` as a Pydantic `Settings` class loaded from env vars or `.env`. Key groups:

| Prefix | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `AMIE_*` | AMIE client: site names, API key, usage interval |
| `CLICKHOUSE_*` | ClickHouse accounting database connection (GPU usage source) |
| `AMIE_GPU_RESOURCE_NAME` | AMIE resource string for GPU records — must match AMIE registration |
| `PORTAL_RPC_*` | NRP portal JSON-RPC: URL, token, namespace |
| `AUTH_ADMIN_*` | Admin portal OIDC (separate IdP from invite flow) |
| `AUTHENTIK_*` | Invite onboarding OIDC via Authentik |
| `ALERT_*` | Webhook, Slack, email alert targets + thresholds |

Multi-site: set `AMIE_SITE_NAMES=NRP,ACCESS` (comma-separated). `AMIE_SITE_NAME` is used as the default/first site.

Dev shortcuts: `AUTH_DEV_BYPASS=true`, `AUTHENTIK_STUB_AUTO_ACCOUNT_MADE=true`.

ClickHouse key vars: `CLICKHOUSE_HOST` (blank = GPU accounting disabled), `CLICKHOUSE_PORT` (default `8443`), `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`, `CLICKHOUSE_DATABASE` (default `access_accounting`), `CLICKHOUSE_TABLE` (default `cluster_namespace_usage_daily`), `CLICKHOUSE_SECURE` (default `true`).

---

## Tests

- Tests use an in-memory SQLite database — no PostgreSQL needed.
- Factory fixtures (`make_project`, `make_user`, `make_project_user`) are in `conftest.py`.
- State machine tests are grouped by class: `TestXxxStates`, `TestXxxTransitions`, `TestXxxHappyPaths`, `TestSetXxxValidation`.
- Use `project.can_lifecycle_transition_to(STATE)` to assert allowed/denied transitions; never test the dict directly in business tests.
