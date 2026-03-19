# Kubernetes Deployment (Argo CD)

This directory is the single deployment source for `nrp-aime`.
It contains the working external-database Kubernetes manifests without the old base and overlay indirection.

No `Namespace` object is created from this repo.
The deployment is targeted at `access-accounting` via Kustomize metadata in `deployment/kustomization.yaml`.

## Layout

```text
deployment/
├── argocd/
│   └── application.yaml
├── config/
│   ├── app.env
│   └── secret.env.example
├── kustomization.yaml
├── resources/
│   ├── aime-worker-deployment.yaml
│   ├── backend-deployment.yaml
│   ├── backend-service.yaml
│   ├── frontend-deployment.yaml
│   ├── frontend-service.yaml
│   ├── ingress.yaml
│   └── usage-worker-deployment.yaml
└── secrets/
    ├── kustomization.yaml
    └── nrp-aime-sealed-secret.yaml
```

`config/secret.env.example` is a template only.
Keep plaintext `config/secret.env` local and out of Git, then commit the encrypted `SealedSecret` YAML instead.

## Argo CD

The example application is in `argocd/application.yaml`.

Before applying it:

1. Update `spec.source.repoURL`.
2. Update `spec.source.targetRevision` if you deploy from a release branch or tag.
3. Update `spec.destination.namespace` if you change the deployment namespace.
4. Pin the backend and frontend image tags in `deployment/kustomization.yaml`.

Apply it with:

```bash
kubectl apply -f deployment/argocd/application.yaml
```

The example does not enable `CreateNamespace=true`.

## Sealed Secrets

This deployment expects a `Secret` named `nrp-aime-secrets`.
Generate and commit a Bitnami Sealed Secret under `deployment/secrets/`.

Use `deployment/config/secret.env.example` as the template for required keys.
Some values appear in both `app.env` and the secret template because the live deployment overrides them from the secret where needed.

Example workflow:

```bash
NAMESPACE=access-accounting
PLAINTEXT_ENV=/tmp/nrp-aime.secret.env
OUTPUT=deployment/secrets/nrp-aime-sealed-secret.yaml

kubectl create secret generic nrp-aime-secrets \
  --namespace "$NAMESPACE" \
  --from-env-file "$PLAINTEXT_ENV" \
  --dry-run=client \
  -o yaml \
| kubeseal \
    --format yaml \
    --namespace "$NAMESPACE" \
    --name nrp-aime-secrets \
> "$OUTPUT"
```

Then list the sealed secret in `deployment/secrets/kustomization.yaml`:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - nrp-aime-sealed-secret.yaml
```

The encrypted YAML is what you commit.
Do not commit the plaintext env file.
If your Sealed Secrets controller uses a non-default name or namespace, add the matching `kubeseal` controller flags.

## Apply Directly

After the namespace exists and the secret is provided through a SealedSecret or a precreated `Secret`, you can render or apply directly:

```bash
kubectl kustomize deployment
kubectl apply -k deployment
```

## Images

This deployment uses:

- `ghcr.io/djw8605/nrp-aime-backend`
- `ghcr.io/djw8605/nrp-aime-frontend`

For Argo CD, pin image tags instead of leaving `latest` in `deployment/kustomization.yaml`.
