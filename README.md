# nrp-aime

NRP AIME Allocation Manager — a full-stack web application for managing allocations in the National Research Platform (NRP).

## Overview

This system interfaces with the AIME allocation and accounting system.

It currently:
- Receives and stores AMIE packets (including packet logs, status, and parse errors).
- Ingests project + account lifecycle packets into normalized `projects`, `users`, and `project_users`.
- Tracks account lifecycle state (`not_sent_email_invite` -> `sent_email` -> `account_made`).
- Supports person-centric magic-link onboarding with Authentik login redirect/callback.
- Supports a separate administrator portal login flow, with optional dev bypass.
- Uses admin-triggered project provisioning states (`received` -> `provisioning` -> `ready`/`failed`) for portal-backed namespace/group creation.
- Tracks outbound confirmation packets and retry/reprocess operations.
- Displays project and administrative KPIs, worker status, and packet observability in the Vue UI.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI (Python) |
| Database | PostgreSQL + SQLAlchemy (ORM) + Alembic (migrations) |
| Allocation ingestion | AMIE client (`amieclient`) |
| Usage metrics | Prometheus (NRP endpoint) |
| Frontend | Vue 3 + PrimeVue + TailwindCSS + Axios |
| Container orchestration | Docker Compose + Kubernetes (Kustomize) |

## Project Structure

```
nrp-aime/
├── backend/                  # FastAPI application
│   ├── app/
│   │   ├── main.py           # Application entry point
│   │   ├── config.py         # Settings (env vars)
│   │   ├── database.py       # DB engine & session
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   ├── api/              # FastAPI route handlers
│   │   └── services/
│   │       ├── aime/         # AMIE packet ingestion
│   │       ├── invites/      # Magic-link invite + callback flow
│   │       ├── email/        # Invite email template + sending stub
│   │       ├── prometheus/   # NRP metrics queries
│   │       ├── authentik/    # Authentik group/login integration (stubbed API calls)
│   │       └── kubernetes/   # Portal JSON-RPC namespace/user provisioning
│   ├── migrations/           # Alembic migrations
│   ├── workers/              # Background task workers
│   ├── requirements.txt
│   ├── Dockerfile
│   └── alembic.ini
├── frontend/                 # Vue 3 dashboard
│   ├── src/
│   │   ├── api/              # Axios API client modules
│   │   ├── components/       # Reusable Vue components
│   │   ├── views/            # Page-level Vue views
│   │   └── router/           # Vue Router configuration
│   ├── package.json
│   └── vite.config.js
└── docker-compose.yml        # Local development stack
```

## Quick Start (Docker Compose)

```bash
# Start all services (PostgreSQL, migrations, FastAPI backend, workers, Vue frontend)
docker compose up
```

Migrations are run automatically by the dedicated `migrate` service before
`backend`, `aime-worker`, and `usage-worker` start.

Local `docker compose` defaults to `AUTH_DEV_BYPASS=true`, so admin pages are
accessible without external OIDC wiring in development.

Then visit:
- **Frontend**: http://localhost:5173
- **API docs**: http://localhost:8000/docs

## Kubernetes (Kustomize)

Kubernetes manifests are in [`k8s/`](/Users/derekweitzel/git/nrp-aime/k8s/README.md), with `base` plus `dev` and `prod` overlays.

```bash
# Development overlay
kubectl apply -k k8s/overlays/dev

# Production overlay
kubectl apply -k k8s/overlays/prod
```

Before applying, set values in:
- `k8s/overlays/dev/config/secret.env`
- `k8s/overlays/prod/config/secret.env`

At minimum configure `POSTGRES_PASSWORD`, `DATABASE_URL`, and `AMIE_API_KEY`.

## Manual Setup

### Backend

```bash
cd backend
pip install -r requirements.txt

# Set environment variables (or create a .env file)
export DATABASE_URL=postgresql://nrp:nrp@localhost:5432/nrp_aime
export PROMETHEUS_URL=https://prometheus.nrp-nautilus.io

# Run migrations
alembic upgrade head

# Start API server
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/projects/` | List all projects |
| GET | `/api/v1/projects/summary` | Top-level project/user/usage KPI summary |
| GET | `/api/v1/projects/{id}` | Get project details |
| POST | `/api/v1/projects/{id}/provision-infrastructure` | Admin action to create namespace/group via portal RPC |
| GET | `/api/v1/projects/{id}/users` | List users for a project |
| GET | `/api/v1/projects/{id}/usage` | Get CPU/GPU usage from Prometheus |
| POST | `/api/v1/projects/{id}/send-account-email` | Send person-scoped invite links for project users |
| POST | `/api/v1/users/{id}/invites` | Send invite link for a person |
| GET | `/api/v1/invites/preview` | Validate invite token and return safe preview |
| GET | `/api/v1/invites/accept` | Start Authentik login redirect for invite token |
| GET | `/api/v1/invites/callback` | Complete invite callback and account binding |
| GET | `/api/v1/auth/session` | Return current admin portal auth session |
| GET | `/api/v1/auth/login` | Start administrator portal login flow |
| GET | `/api/v1/auth/callback` | Complete administrator portal login callback |
| POST | `/api/v1/auth/logout` | End administrator portal session |
| GET | `/api/v1/users/` | List people/users |
| GET | `/api/v1/users/{id}` | Get user details |
| GET | `/api/v1/packets/logs` | Packet log table (search/sort/pagination) |
| POST | `/api/v1/audit/portal-sync` | Audit/reconcile portal namespace membership drift |
| GET | `/healthz` | Health check |

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://nrp:nrp@localhost:5432/nrp_aime` | PostgreSQL connection string |
| `PROMETHEUS_URL` | `https://prometheus.nrp-nautilus.io` | NRP Prometheus endpoint |
| `AMIE_SITE_NAME` | `NRP` | Site name for AMIE client |
| `AMIE_API_KEY` | `` | API key for AMIE client |
| `AMIE_URL` | `https://amieclient.xsede.org/v0.10/` | AMIE API base URL |
| `AMIE_PROCESSED_CLIENT_STATE` | `nrp-processed` | Client state set after successful ingestion |
| `AMIE_USAGE_URL` | `https://usage.xsede.org/api/v1` | AMIE usage API base URL |
| `AMIE_USAGE_INTERVAL_MINUTES` | `1440` | Usage export interval and record bucket size (once daily) |
| `AMIE_USAGE_GPU_CHARGE_FACTOR` | `1.0` | Multiplier applied to GPU usage when computing charge |
| `AMIE_USAGE_DEFAULT_USERNAME` | `nrp-system` | Fallback username for usage records when no login is mapped |
| `APP_SECRET_KEY` | `dev-change-me` | Secret used for signed invite state and token hashing pepper |
| `FRONTEND_BASE_URL` | `http://localhost:5173` | Base URL used for invite accept/success/error redirects |
| `BACKEND_BASE_URL` | `http://localhost:8000` | Base URL used for Authentik callback URL generation |
| `PORTAL_RPC_URL` | `https://portal.nrp.ai/rpc` | Portal JSON-RPC endpoint |
| `PORTAL_RPC_NAMESPACE` | `access` | Parent namespace used when calling `admin.CreateNamespace` (configurable) |
| `PORTAL_RPC_TIMEOUT_SECONDS` | `15` | HTTP timeout for portal RPC calls |
| `PORTAL_RPC_TOKEN` | `` | Shared token sent as `X-Portal-RPC-Token` for portal RPC auth |
| `AUTH_DEV_BYPASS` | `false` | Bypass admin portal authentication (dev-only) |
| `AUTH_STATE_TTL_MINUTES` | `30` | Signed state TTL for admin auth callback flow |
| `AUTH_SESSION_COOKIE_NAME` | `nrp_portal_session` | Session cookie name for admin portal login |
| `AUTH_SESSION_TTL_MINUTES` | `720` | Admin portal session lifetime |
| `AUTH_SESSION_HTTPS_ONLY` | `false` | Mark admin session cookie as HTTPS-only |
| `AUTH_ADMIN_AUTHORIZE_URL` | `` | OIDC authorize URL for administrator portal flow |
| `AUTH_ADMIN_CLIENT_ID` | `` | OIDC client ID for administrator portal flow |
| `AUTH_ADMIN_CLIENT_SECRET` | `` | OIDC client secret for administrator callback code exchange |
| `AUTH_ADMIN_OIDC_CONFIGURATION_URL` | `` | Optional OIDC discovery URL used to resolve token/userinfo endpoints |
| `AUTH_ADMIN_TOKEN_URL` | `` | OIDC token endpoint for administrator callback code exchange |
| `AUTH_ADMIN_USERINFO_URL` | `` | OIDC userinfo endpoint for administrator callback claims |
| `AUTH_ADMIN_LOGOUT_URL` | `` | Optional IdP logout URL reference for deployments |
| `AUTH_ADMIN_JWKS_URL` | `` | Optional IdP JWKS URL reference for deployments |
| `AUTH_ADMIN_SCOPE` | `openid profile email` | OIDC scopes for administrator portal flow |
| `AUTH_ADMIN_REDIRECT_PATH` | `/api/v1/auth/callback` | Backend callback path (or full URL) for administrator portal flow |
| `AUTH_ADMIN_STUB_LOGIN_EMAIL` | `` | Stub callback email for local admin auth testing |
| `INVITE_TOKEN_TTL_HOURS` | `72` | Invite link expiration in hours |
| `INVITE_STATE_TTL_MINUTES` | `30` | Auth redirect signed-state expiration |
| `INVITE_REQUIRE_EMAIL_MATCH` | `true` | Require authenticated email to match invited email |
| `AUTHENTIK_AUTHORIZE_URL` | `` | OIDC authorize endpoint (when real Authentik login redirect is enabled) |
| `AUTHENTIK_CLIENT_ID` | `` | OIDC client ID for login redirect |
| `AUTHENTIK_CLIENT_SECRET` | `` | OIDC client secret for invite callback code exchange |
| `AUTHENTIK_OIDC_CONFIGURATION_URL` | `` | Optional OIDC discovery URL used to resolve token/userinfo endpoints |
| `AUTHENTIK_TOKEN_URL` | `` | OIDC token endpoint for invite callback code exchange |
| `AUTHENTIK_USERINFO_URL` | `` | OIDC userinfo endpoint for invite callback claims |
| `AUTHENTIK_SCOPE` | `openid profile email` | OIDC scopes for Authentik login |
| `AUTHENTIK_REDIRECT_PATH` | `/api/v1/invites/callback` | Backend callback path for invite flow |
| `AUTHENTIK_STUB_LOGIN_EMAIL` | `` | Stub callback email for local testing without real OIDC |
| `DEBUG` | `false` | Enable debug mode |

See the full backend configuration reference in [backend/README.md](/Users/derekweitzel/git/nrp-aime/backend/README.md).

## Architecture Notes

- The **PostgreSQL database** acts as the central interface between the frontend dashboard and the backend services.
- The **AIME worker** (`workers/aime_worker.py`) polls AMIE packets, logs each packet at debug level on receipt, and persists both raw packet data and normalized Project + User lifecycle records.
- The **Usage worker** (`workers/usage_worker.py`) sends periodic usage records to the AMIE Usage API using `amieclient.UsageClient`.
- The **Prometheus service** queries namespace-scoped pod metrics to report CPU/GPU usage.
- The **Invite service** (`services/invites/service.py`) provides person-centric magic-link onboarding:
  - admin sends invite from person page
  - invite link opens portal landing page
  - user is redirected to Authentik login
  - callback exchanges OAuth code for claims (userinfo/ID token), stores Authentik username (`preferred_username`/`username`) as `remote_site_login`, and assigns namespace/group membership via portal RPC
- The **Audit service** can reconcile portal namespace drift:
  - read state via `admin.ListAllNamespaces` + `admin.GetNSUsers`
  - rectify via `admin.CreateNamespace`, `admin.AddNSUser`, `admin.DeleteNSUser`, `admin.SetNamespaceInfo`
  - `admin.SetNamespaceInfo` is sent with flattened NSInfo fields populated from project registration data
- The **Admin auth flow** (`/api/v1/auth/*`) is separate from invite onboarding:
  - invite pages remain public
  - all main dashboard/admin APIs require portal authentication
  - production authorization policy is expected to be enforced by the upstream IdP flow

## Image Build Workflow

GitHub Actions workflow [`build-images.yml`](/Users/derekweitzel/git/nrp-aime/.github/workflows/build-images.yml) builds backend and frontend images with Buildx and publishes them to GitHub Container Registry (GHCR):
- `ghcr.io/<owner>/nrp-aime-backend`
- `ghcr.io/<owner>/nrp-aime-frontend`
