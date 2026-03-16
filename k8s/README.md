# Kubernetes Deployment (Kustomize)

This directory contains a Kustomize-based Kubernetes deployment for the full stack:
- `postgres` (stateful data via PVC)
- `backend` (FastAPI)
- `frontend` (nginx serving built Vue assets)
- `aime-worker`
- `usage-worker`
- `ingress`

Ingress is configured for cluster ingress class `haproxy` and includes TLS host entries (`spec.tls.hosts`) matching the configured hostname in each overlay.

Database migrations are run automatically in init containers (`alembic upgrade head`) before backend and workers start.

## Layout

- `base/`: Common manifests and default config/secret placeholders.
- `overlays/dev/`: Development-oriented overlay.
- `overlays/prod/`: Production-oriented overlay (replica + host patch examples).

## Configure

Edit overlay files before apply:
- `overlays/dev/config/app.env`
- `overlays/dev/config/secret.env`
- `overlays/prod/config/app.env`
- `overlays/prod/config/secret.env`

At minimum, set:
- `POSTGRES_PASSWORD`
- `DATABASE_URL`
- `AMIE_API_KEY`

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
- `INVITE_TOKEN_TTL_HOURS`, `INVITE_STATE_TTL_MINUTES`, `INVITE_REQUIRE_EMAIL_MATCH`
- `AUTHENTIK_AUTHORIZE_URL`, `AUTHENTIK_CLIENT_ID`, `AUTHENTIK_SCOPE`, `AUTHENTIK_REDIRECT_PATH`
- `AUTHENTIK_STUB_LOGIN_EMAIL` (stub/local environments)

Lifecycle behavior:
- Keep `AUTHENTIK_STUB_AUTO_ACCOUNT_MADE=false` for invite-driven onboarding.
  - If set to `true`, accounts can auto-transition to `account_made` and bypass the intended invite-click flow.

## Apply

```bash
# Dev
kubectl apply -k k8s/overlays/dev

# Prod
kubectl apply -k k8s/overlays/prod
```

## Images

Deployments reference images:
- `ghcr.io/your-org/nrp-aime-backend`
- `ghcr.io/your-org/nrp-aime-frontend`

Set your org/repo image coordinates using `images:` in the overlay `kustomization.yaml` files.
