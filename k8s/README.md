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
