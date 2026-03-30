# NRP AIME — Copilot Instructions

## Project Overview

NRP AIME is an allocation management portal that bridges ACCESS/XSEDE AMIE packets to NRP's Kubernetes infrastructure. It receives allocation requests, provisions Kubernetes namespaces via the NRP portal RPC, onboards users through OAuth invite flows, and reports usage back to AMIE.

**Stack:** FastAPI + SQLAlchemy 2.0 + Alembic + PostgreSQL (Python 3.11) · Vue 3 (Composition API) + PrimeVue + TailwindCSS 4 · Kubernetes + Kustomize + Argo CD

**Key directories:**
```
backend/app/models/      SQLAlchemy ORM models
backend/app/schemas/     Pydantic schemas
backend/app/api/         FastAPI routers (one per resource)
backend/app/services/    Business logic (grouped by domain)
backend/migrations/      Alembic migrations (numbered 0001–)
backend/tests/           pytest (in-memory SQLite, no live DB needed)
frontend/src/api/        Axios client modules
frontend/src/views/      Page-level Vue views
deployment/              Kustomize + SealedSecrets + ArgoCD
```

---

## State Machines — Critical Pattern

State machines are the core domain pattern. **Always use the model methods, not direct attribute assignment.**

### Project lifecycle
```
received → pending_provisioning → provisioning → provisioned
  └─(pi project)→ waiting_pi_account → provisioned
provisioned → aime_notified → active ↔ inactive
provisioning → provisioning_failed → provisioning (retry)
```

- Transition map: `Project.LIFECYCLE_STATE_TRANSITIONS`
- Check: `project.can_lifecycle_transition_to(STATE)`
- Mutate: `project.set_lifecycle_state(STATE)` — validates and raises `ValueError` on unknown state

### ProjectUser account lifecycle
```
received → email_invite_sent → user_completed_oauth → aime_notified   (regular user)
                                                     → covered_by_project_notification  (PI)
```

- Transition map: `ProjectUser.ACCOUNT_STATE_TRANSITIONS`
- Check: `project_user.can_transition_to(STATE)`
- Mutate: `project_user.set_account_state(STATE)`

**Adding a new state:** constant → tuple → transitions dict → migration → service logic → frontend label/severity maps.

---

## Coding Conventions

### Python
- Models own state constants (`LIFECYCLE_STATE_RECEIVED = "received"`) and transition maps.
- Services contain all business logic; routes are thin wrappers calling services.
- Private helpers use a leading underscore.
- `provisioning_state` is a legacy column kept for backwards compat — `lifecycle_state` is the source of truth.
- `amieclient` is installed `--no-deps` to avoid its stale `python-dateutil<2.7` constraint. Do not add it to `requirements.txt` with deps.
- Migrations are numbered `NNNN_slug.py`. Always inspect autogenerate output before committing.
- **GPU usage export** (`services/aime/usage_service.py`) sources data from **ClickHouse** via `services/clickhouse/service.py`. Prometheus is only used for the live display endpoint. `User.remote_site_login` holds the CILogon subject ID matched against `created_by` in ClickHouse; `ProjectUser.remote_site_login` is the AMIE `Username`.

### Vue / JavaScript
- All components use `<script setup>` Composition API — no Options API.
- API calls live in `src/api/<domain>.js` and return `res.data`.
- PrimeVue only — no second UI library.

### Commits
Conventional Commits: `feat:`, `fix:`, `test:`, `ci:`, `chore:`. Add `[skip deploy]` to automated commits to suppress the build-and-deploy workflow.

---

## Domain Terminology

| Term | Meaning |
|---|---|
| **AMIE** | AIME Message Interface Engine — packet protocol between sites and ACCESS |
| **AIME** | Allocation & Integrated Management Environment (the ACCESS system) |
| **NRP** | National Research Platform — primary site (`AMIE_SITE_NAME=NRP`) |
| **PI** | Principal Investigator — project lead; account must exist before `notify_project_create` is sent |
| **Project / Allocation** | A resource grant tracked by `aime_allocation_id` |
| **Packet** | An AMIE message (`request_project_create`, `notify_account_create`, etc.) |
| **Provisioning** | Creating K8s namespace + Authentik group via NRP portal RPC |
| **Authentik** | Identity provider for invite-based OAuth onboarding |
| **SealedSecret** | Bitnami-encrypted K8s secret — commit the YAML, never the plaintext |
| **Service Units** | Standardized CPU/GPU allocation currency |

---

## CLI Commands

```bash
# Backend
uvicorn app.main:app --reload
python -m pytest tests/ -v --tb=short
alembic upgrade head
alembic revision --autogenerate -m "feat: description"

# Frontend
npm run dev
npm run build

# Local stack
docker compose up
docker compose run migrate

# Kubernetes
kubectl apply -k deployment
```

---

## Environment Config

All settings are in `backend/app/config.py` (Pydantic `Settings`, loaded from `.env` or environment).

| Prefix | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `AMIE_*` | AMIE client — site names, API key, usage interval |
| `CLICKHOUSE_HOST` | ClickHouse hostname — blank disables GPU accounting |
| `CLICKHOUSE_PORT` | ClickHouse port (default `8443`) |
| `CLICKHOUSE_USER` | ClickHouse username (default `default`) |
| `CLICKHOUSE_PASSWORD` | ClickHouse password |
| `CLICKHOUSE_DATABASE` | ClickHouse database (default `access_accounting`) |
| `CLICKHOUSE_TABLE` | ClickHouse table (default `cluster_namespace_usage_daily`) |
| `CLICKHOUSE_SECURE` | Use TLS (default `true`) |
| `AMIE_GPU_RESOURCE_NAME` | AMIE resource string for GPU records — must match AMIE registration; falls back to `Project.resource_type` |
| `PORTAL_RPC_*` | NRP portal JSON-RPC — URL, token, namespace |
| `AUTH_ADMIN_*` | Admin portal OIDC |
| `AUTHENTIK_*` | Invite onboarding OIDC |
| `ALERT_*` | Webhook, Slack, email targets + thresholds |

Multi-site: `AMIE_SITE_NAMES=NRP,ACCESS`. Dev shortcuts: `AUTH_DEV_BYPASS=true`.

---

## Feature Workflow

**New model field:** add `Mapped[T]` column → `alembic revision --autogenerate` (inspect!) → update Pydantic schema → update service.

**New API endpoint:** service method first → route in `app/api/<resource>.py` → register router in `app/main.py` if new file.

**New state:** constant + tuple + transitions entry → migration with backfill → service transition logic → frontend severity/label maps.

**Tests:** use `conftest.py` factory fixtures (`make_project`, `make_user`, `make_project_user`). Group by `TestXxxStates`, `TestXxxTransitions`, `TestXxxHappyPaths`.
