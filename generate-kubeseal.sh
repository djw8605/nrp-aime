#!/bin/sh

# Get the sealed secret from nautilus
kubeseal --fetch-cert --controller-name sealed-secrets --controller-namespace sealed-secrets-operator > nautilus-cert.pem

NAMESPACE=access-accounting
PLAINTEXT_ENV=deployment/config/secret.env
OUTPUT=deployment/secrets/nrp-aime-sealed-secret.yaml

kubectl create secret generic nrp-aime-secrets \
  --namespace "$NAMESPACE" \
  --from-env-file "$PLAINTEXT_ENV" \
  --dry-run=client \
  -o yaml \
| kubeseal \
    --format yaml \
    --cert nautilus-cert.pem \
    --namespace "$NAMESPACE" \
    --name nrp-aime-secrets \
> "$OUTPUT"
