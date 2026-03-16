# Kubernetes Deployment (Kustomize)

This directory contains a Kustomize-based Kubernetes deployment for the full stack:
- `postgres` (stateful data via PVC)
- `backend` (FastAPI)
- `frontend` (nginx serving built Vue assets)
- `aime-worker`
- `usage-worker`
- `ingress`
- `nrp-aime-provisioner` service account + rolebindings for namespace/group provisioning workflows

Ingress is configured for cluster ingress class `haproxy` and includes TLS host entries (`spec.tls.hosts`) matching the configured hostname in each overlay.

Database migrations are run automatically in init containers (`alembic upgrade head`) before backend and workers start.

RBAC notes:
- `k8s/base/provisioner-rbac.yaml` creates service account `nrp-aime-provisioner`.
- It binds that service account to:
  - `nautilus-edit-rolebinding` (ClusterRole `nautilus-edit`)
  - `nautilus-admin-rolebinding` (ClusterRole `nautilus-admin`)
- Backend and worker deployments use this service account.

## Layout

- `base/`: Common manifests and default config/secret placeholders.
- `overlays/dev/`: Development-oriented overlay.
- `overlays/prod/`: Production-oriented overlay (replica + host patch examples).
- `overlays/external-db/`: Uses an existing PostgreSQL instance and removes in-cluster `postgres` resources.

## Configure

Edit overlay files before apply:
- `overlays/dev/config/app.env`
- `overlays/dev/config/secret.env`
- `overlays/prod/config/app.env`
- `overlays/prod/config/secret.env`
- `overlays/external-db/config/app.env`
- `overlays/external-db/config/secret.env`

At minimum, set (for `dev` and `prod` overlays):
- `POSTGRES_PASSWORD`
- `DATABASE_URL`
- `AMIE_API_KEY`

For the `external-db` overlay, `DATABASE_URL` and `AMIE_API_KEY` are the required database-related values.

## External Database Overlay

Use `overlays/external-db` when you want this app to connect to an existing PostgreSQL database instead of deploying Kubernetes `postgres` resources.

What this overlay changes:
- Does not include the base `postgres` Deployment, Service, or PVC resources.
- Updates backend and worker `wait-for-db` init containers to check readiness using `pg_isready -d "$DATABASE_URL"`.

Configure:
- `overlays/external-db/config/secret.env`: set `DATABASE_URL`, `AMIE_API_KEY`, and `ALERT_SMTP_PASSWORD` (if SMTP alerts are enabled).
- `overlays/external-db/config/app.env`: set hostnames and other app-level settings.
- `overlays/external-db/ingress-host-patch.yaml`: set your ingress host and TLS host.

Example `DATABASE_URL`:
- `postgresql://db_user:db_password@db.example.org:5432/nrp_aime`
- If credentials contain special characters (`@`, `:`, `/`, `#`), URL-encode them.

Optional alerting configuration:
- `ALERT_WEBHOOK_URL`, `ALERT_SLACK_WEBHOOK_URL`
- `ALERT_EMAIL_TO`, `ALERT_EMAIL_FROM`
- `ALERT_SMTP_HOST`, `ALERT_SMTP_PORT`, `ALERT_SMTP_USERNAME`, `ALERT_SMTP_PASSWORD`

Optional accounting stub configuration:
- `ACCOUNTING_STUB_ENABLED`
- `ACCOUNTING_STUB_CPU_RATIO`, `ACCOUNTING_STUB_GPU_RATIO`

Invite / onboarding configuration:
- `APP_SECRET_KEY` (required for invite token hashing + signed auth state)
- `FRONTEND_BASE_URL`, `BACKEND_BASE_URL`
- `AUTH_DEV_BYPASS` (set `false` for production, optional `true` in dev)
- `AUTH_STATE_TTL_MINUTES`, `AUTH_SESSION_COOKIE_NAME`, `AUTH_SESSION_TTL_MINUTES`, `AUTH_SESSION_HTTPS_ONLY`
- `AUTH_ADMIN_AUTHORIZE_URL`, `AUTH_ADMIN_CLIENT_ID`, `AUTH_ADMIN_SCOPE`, `AUTH_ADMIN_REDIRECT_PATH`
- `AUTH_ADMIN_STUB_LOGIN_EMAIL` (dev-only fallback when no real admin OIDC exchange is wired)
- `INVITE_TOKEN_TTL_HOURS`, `INVITE_STATE_TTL_MINUTES`, `INVITE_REQUIRE_EMAIL_MATCH`
- `AUTHENTIK_AUTHORIZE_URL`, `AUTHENTIK_CLIENT_ID`, `AUTHENTIK_SCOPE`, `AUTHENTIK_REDIRECT_PATH`
- `AUTHENTIK_STUB_LOGIN_EMAIL` (stub/local environments)

Auth flow split:
- Invite flow (`/api/v1/invites/*`) stays public so invite recipients can onboard.
- Administrator portal flow (`/api/v1/auth/*`) protects dashboard/admin APIs.
- Upstream IdP flow/policy should enforce administrator access control.

Lifecycle behavior:
- Keep `AUTHENTIK_STUB_AUTO_ACCOUNT_MADE=false` for invite-driven onboarding.
  - If set to `true`, accounts can auto-transition to `account_made` and bypass the intended invite-click flow.

## Apply

```bash
# Dev
kubectl apply -k k8s/overlays/dev

# Prod
kubectl apply -k k8s/overlays/prod

# External DB
kubectl apply -k k8s/overlays/external-db
```

## Images

Deployments reference images:
- `ghcr.io/your-org/nrp-aime-backend`
- `ghcr.io/your-org/nrp-aime-frontend`

Set your org/repo image coordinates using `images:` in the overlay `kustomization.yaml` files.
