# NRP AIME Backend

FastAPI backend for managing NRP allocations via the AIME/AMIE system.

## Requirements

- Python 3.11+
- PostgreSQL 14+

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
# Create/edit .env with your settings (or export env vars directly)

# Run database migrations
alembic upgrade head

# Start the API server
uvicorn app.main:app --reload
```

## Recent Changes

- Person-centric magic-link invite onboarding is enabled.
  - Invite links are sent per person (`POST /api/v1/users/{id}/invites`), not per project row.
  - Invite flow uses `preview -> accept -> Authentik login redirect -> callback finalize`.
  - Callback marks account lifecycle as `account_made` and assigns namespace/group access via portal RPC.
- Separate administrator portal authentication flow is enabled.
  - Most API routes now require portal authentication.
  - Invite onboarding endpoints remain public (`/api/v1/invites/*` + `/api/v1/auth/invite/callback`).
  - Admin flow runs via `/api/v1/auth/login` and `/api/v1/auth/callback`.
  - Callback exchanges OAuth code at token endpoint and resolves identity from userinfo/ID token claims.
  - `AUTH_DEV_BYPASS=true` can be used for local development.
- Project provisioning is admin-triggered from the project detail page/API.
  - New projects enter `received` state and send an admin alert.
  - Admin action transitions to `provisioning` then `ready`/`failed`.
  - Provisioning calls portal JSON-RPC (`admin.CreateNamespace`) with `GroupFeatures=["is_k8s_namespace"]`.
  - Namespace metadata updates use flattened portal RPC params (`admin.SetNamespaceInfo`) and populate NSInfo fields from project registration data (PI, grant/allocation, description, institution, resource details, timestamps).
- Portal reconciliation endpoints support drift detection and repair:
  - `admin.ListAllNamespaces`, `admin.GetNSUsers`
  - `admin.AddNSUser`, `admin.DeleteNSUser`
- Invite callback stores Authentik username (`preferred_username`/`username`) into `remote_site_login`; portal membership RPCs use that username for `UserID`.
- Invite success page now includes account username and NRP getting-started/training links.
- Packet lifecycle and observability features were expanded:
  - packet log table with search/sort/pagination
  - reprocess/replay controls
  - worker status and freshness metrics
  - outbound packet tracking + retry state
  - transaction summary checks for expected project/account packet sequences (for example `request_project_create -> notify_project_create -> data_project_create -> inform_transaction_complete` and `request_account_create -> notify_account_create -> data_account_create -> inform_transaction_complete`).
  - account-create parsing captures canonical fields (`GrantNumber`, optional `ProjectID`, `UserGlobalID`, `UserPersonID`, `UserRemoteSiteLogin`, `AllocatedResource`, `ServiceUnitsAllocated`, `DnList`/`UserDnList`) and preserves full packet bodies in `raw_packet`/`raw_body` for lossless auditing.
- Multi-site AMIE polling support is enabled:
  - configure `AMIE_SITE_NAMES` (comma-separated) to poll multiple AMIE sites sequentially each cycle.
  - worker polls both incoming and outgoing packet queues to preserve full transaction sequences.
  - projects/users are tagged with `source_site_name`.
  - projects and project memberships track `allocated_resource`, `service_units_allocated`, and `service_units_remaining` when provided.
  - users track `service_units_allocated` from account/allocation packets when provided.
  - project/person identifiers are no longer globally unique in the DB, so overlapping IDs across sites can coexist.

## Running the AIME Worker

```bash
python -m workers.aime_worker
```

## Running the Usage Export Worker

```bash
python -m workers.usage_worker
```

## Worker Status in Database

Worker heartbeat and runtime state are stored in the `worker_statuses` table.

Example query:

```sql
SELECT worker_name, is_active, current_state, status_message, last_heartbeat
FROM worker_statuses
ORDER BY worker_name;
```

## Project Usage Snapshots in Database

The usage worker continuously refreshes per-project usage in
`project_usage_snapshots`. These values are then used by API endpoints for
project usage and top-level KPI summaries.

Example query:

```sql
SELECT project_id, cpu_used_current, gpu_used_current, charge_interval, last_collected_at
FROM project_usage_snapshots
ORDER BY last_collected_at DESC;
```

Usage exports to AMIE are sent as interval deltas (`AdjustmentUsageRecord`
with `adjustment_type=debit`) for each collection interval, not as repeatedly
sent cumulative totals.

## API Documentation

Once running, visit http://localhost:8000/docs for interactive API docs.

## Invite Flow Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/users/{user_id}/invites` | Send a person-scoped invite link |
| `POST` | `/api/v1/projects/{project_id}/invites` | Create invite directly for a project scope (admin/tooling path) |
| `GET` | `/api/v1/invites/preview?token=...` | Safe invite preview payload for landing page |
| `GET` | `/api/v1/invites/accept?token=...` | Validate invite and redirect to Authentik login |
| `GET` | `/api/v1/invites/callback` | Finalize invite after Authentik callback |
| `POST` | `/api/v1/projects/{project_id}/provision-infrastructure` | Trigger portal-backed namespace/group provisioning for a project |

## Admin Auth Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/auth/session` | Resolve current portal auth principal (or unauthenticated) |
| `GET` | `/api/v1/auth/login?next=/...` | Start administrator login flow |
| `GET` | `/api/v1/auth/callback` | Complete administrator login callback |
| `POST` | `/api/v1/auth/logout` | Clear administrator session |
| `GET` | `/api/v1/auth/me` | Return authenticated administrator principal |

## Audit / Reconciliation Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/audit/run` | Run all cross-service audit checks |
| `POST` | `/api/v1/audit/portal-sync` | Audit/reconcile portal namespace memberships against DB |

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://nrp:nrp@localhost:5432/nrp_aime` | PostgreSQL connection string |
| `PROMETHEUS_URL` | `https://prometheus.nrp-nautilus.io` | NRP Prometheus endpoint |
| `AMIE_SITE_NAME` | `NRP` | Site name for AMIE client |
| `AMIE_SITE_NAMES` | `` | Optional comma-separated AMIE site names to poll one-by-one (for example `NRP,ACCESS`) |
| `AMIE_API_KEY` | `` | API key for AMIE client |
| `AMIE_URL` | `https://amieclient.xsede.org/v0.10/` | AMIE API base URL |
| `AMIE_PROCESSED_CLIENT_STATE` | `nrp-processed` | Client state set after successful ingestion |
| `AMIE_USAGE_URL` | `https://usage.xsede.org/api/v1` | AMIE usage API base URL |
| `AMIE_USAGE_INTERVAL_MINUTES` | `1440` | Usage export interval and usage record bucket size (default: once daily) |
| `AMIE_USAGE_GPU_CHARGE_FACTOR` | `1.0` | Multiplier applied to GPU usage when computing charge |
| `AMIE_USAGE_DEFAULT_USERNAME` | `nrp-system` | Fallback username for usage records when no login is mapped |
| `AMIE_ACCOUNT_CONFIRMATION_ENABLED` | `true` | Enable sending `notify_account_create` confirmations to AIME |
| `AMIE_PACKET_REPROCESS_MAX_RETRIES` | `5` | Max packet re-ingest attempts before lockout |
| `AMIE_PACKET_REPROCESS_LOCKOUT_MINUTES` | `30` | Lockout duration once retry limit is reached |
| `AUTHENTIK_BASE_URL` | `` | Authentik API base URL (for non-stub integration) |
| `AUTHENTIK_API_TOKEN` | `` | Authentik API token |
| `AUTHENTIK_AUTHORIZE_URL` | `` | OIDC authorize endpoint for invite login redirect |
| `AUTHENTIK_CLIENT_ID` | `` | OIDC client ID for invite login redirect |
| `AUTHENTIK_CLIENT_SECRET` | `` | OIDC client secret for invite callback code exchange |
| `AUTHENTIK_OIDC_CONFIGURATION_URL` | `` | Optional OIDC discovery URL used to resolve token/userinfo endpoints |
| `AUTHENTIK_TOKEN_URL` | `` | OIDC token endpoint for invite callback code exchange |
| `AUTHENTIK_USERINFO_URL` | `` | OIDC userinfo endpoint for invite callback claims |
| `AUTHENTIK_SCOPE` | `openid profile email` | OIDC scopes requested during login |
| `AUTHENTIK_REDIRECT_PATH` | `/api/v1/invites/callback` | Backend callback path for invite flow |
| `AUTHENTIK_STUB_LOGIN_EMAIL` | `` | Stub callback identity email for local invite testing |
| `ACCOUNTING_STUB_ENABLED` | `true` | Enable deterministic stub accounting values when snapshots are missing |
| `ACCOUNTING_STUB_CPU_RATIO` | `0.35` | Fraction of allocated CPU shown as current usage in stub mode |
| `ACCOUNTING_STUB_GPU_RATIO` | `0.20` | Fraction of allocated GPU shown as current usage in stub mode |
| `ALERT_WEBHOOK_URL` | `` | Generic webhook endpoint for alerts |
| `ALERT_SLACK_WEBHOOK_URL` | `` | Slack incoming webhook URL for alerts |
| `ALERT_EMAIL_TO` | `` | Comma-separated alert email recipients |
| `ALERT_EMAIL_FROM` | `` | Sender address for email alerts |
| `ALERT_SMTP_HOST` | `` | SMTP host for email alerts |
| `ALERT_SMTP_PORT` | `587` | SMTP port |
| `ALERT_SMTP_USERNAME` | `` | SMTP auth username (optional) |
| `ALERT_SMTP_PASSWORD` | `` | SMTP auth password (optional) |
| `ALERT_SMTP_USE_TLS` | `true` | Enable STARTTLS for SMTP |
| `ALERT_MIN_INTERVAL_MINUTES` | `30` | Per-alert-key throttle window |
| `ALERT_WORKER_STALE_SECONDS` | `300` | Heartbeat lag threshold for worker-down alerts |
| `ALERT_PARSE_FAILURES_THRESHOLD` | `10` | Parse failure threshold for alerting |
| `ALERT_RECONCILE_STALE_MINUTES` | `120` | Max age for authentik reconcile freshness |
| `APP_NAME` | `NRP AIME Allocation Manager` | Display name for API/application |
| `APP_SECRET_KEY` | `dev-change-me` | Secret for invite token hashing + signed state |
| `FRONTEND_BASE_URL` | `http://localhost:5173` | Frontend base URL used for invite links/redirects |
| `BACKEND_BASE_URL` | `http://localhost:8000` | Backend base URL used to construct callback URL |
| `PORTAL_RPC_URL` | `https://portal.nrp.ai/rpc` | Portal JSON-RPC endpoint |
| `PORTAL_RPC_NAMESPACE` | `access` | Parent namespace argument for `admin.CreateNamespace` (configurable) |
| `PORTAL_RPC_TIMEOUT_SECONDS` | `15` | Timeout for portal RPC HTTP calls |
| `PORTAL_RPC_TOKEN` | `` | Shared token for `X-Portal-RPC-Token` header |
| `AUTH_DEV_BYPASS` | `false` | Bypass admin portal authentication (dev-only) |
| `AUTH_STATE_TTL_MINUTES` | `30` | Signed state max age for admin callback flow |
| `AUTH_SESSION_COOKIE_NAME` | `nrp_portal_session` | Session cookie name for portal auth |
| `AUTH_SESSION_TTL_MINUTES` | `720` | Admin session lifetime |
| `AUTH_SESSION_HTTPS_ONLY` | `false` | Mark session cookie HTTPS-only |
| `AUTH_ADMIN_AUTHORIZE_URL` | `` | OIDC authorize endpoint for admin portal login |
| `AUTH_ADMIN_CLIENT_ID` | `` | OIDC client ID for admin portal login |
| `AUTH_ADMIN_CLIENT_SECRET` | `` | OIDC client secret for admin callback code exchange |
| `AUTH_ADMIN_OIDC_CONFIGURATION_URL` | `` | Optional OIDC discovery URL used to resolve token/userinfo endpoints |
| `AUTH_ADMIN_TOKEN_URL` | `` | OIDC token endpoint for admin callback code exchange |
| `AUTH_ADMIN_USERINFO_URL` | `` | OIDC userinfo endpoint for admin callback claims |
| `AUTH_ADMIN_LOGOUT_URL` | `` | Optional IdP logout URL reference for deployments |
| `AUTH_ADMIN_JWKS_URL` | `` | Optional IdP JWKS URL reference for deployments |
| `AUTH_ADMIN_SCOPE` | `openid profile email` | OIDC scopes requested for admin portal login |
| `AUTH_ADMIN_REDIRECT_PATH` | `/api/v1/auth/callback` | Backend callback path (or full URL) for admin portal flow |
| `AUTH_ADMIN_STUB_LOGIN_EMAIL` | `` | Stub callback identity email for local admin-flow testing |
| `INVITE_TOKEN_TTL_HOURS` | `72` | Invite link expiration window |
| `INVITE_STATE_TTL_MINUTES` | `30` | Signed auth-state expiration window |
| `INVITE_REQUIRE_EMAIL_MATCH` | `true` | Require callback identity email to match invite email |
| `DEBUG` | `false` | Enable FastAPI debug mode |
| `ALLOWED_ORIGINS` | `[]` | CORS allowlist |
