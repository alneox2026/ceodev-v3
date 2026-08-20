#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Deploy Middleware Infrastructure via Terraform (Gateway, Worker, Billing API, Pub/Sub)
# ==============================================================================

PROJECT_ID="${PROJECT_ID:-ceo-dev123}"
REGION="${REGION:-us-central1}"
REPOSITORY="${REPOSITORY:-ceosystem}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

# Auto-detect latest built digests or tags per service if not explicitly provided
if [ -n "${TAG:-}" ] && [ "${TAG}" != "latest" ]; then
  GATEWAY_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/ceoagent-gateway-v3:${TAG}"
  WORKER_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/ceoagent-persistence-worker-v3:${TAG}"
  BILLING_API_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/ceoagent-billing-api-v3:${TAG}"
else
  echo "--> Detecting newest middleware image digests in Artifact Registry..."
  GATEWAY_DIGEST="$(gcloud artifacts docker images list "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/ceoagent-gateway-v3" --sort-by=~CREATE_TIME --limit=1 --format='value(version)' 2>/dev/null || true)"
  WORKER_DIGEST="$(gcloud artifacts docker images list "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/ceoagent-persistence-worker-v3" --sort-by=~CREATE_TIME --limit=1 --format='value(version)' 2>/dev/null || true)"
  BILLING_API_DIGEST="$(gcloud artifacts docker images list "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/ceoagent-billing-api-v3" --sort-by=~CREATE_TIME --limit=1 --format='value(version)' 2>/dev/null || true)"

  if [ -n "${GATEWAY_DIGEST}" ]; then
    GATEWAY_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/ceoagent-gateway-v3@${GATEWAY_DIGEST}"
  else
    GATEWAY_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/ceoagent-gateway-v3:latest"
  fi

  if [ -n "${WORKER_DIGEST}" ]; then
    WORKER_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/ceoagent-persistence-worker-v3@${WORKER_DIGEST}"
  else
    WORKER_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/ceoagent-persistence-worker-v3:latest"
  fi

  if [ -n "${BILLING_API_DIGEST}" ]; then
    BILLING_API_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/ceoagent-billing-api-v3@${BILLING_API_DIGEST}"
  else
    BILLING_API_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/ceoagent-billing-api-v3:latest"
  fi
fi


echo "================================================================="
echo " Deploying Middleware Infrastructure (Terraform V3)"
echo " Project ID        : ${PROJECT_ID}"
echo " Region            : ${REGION}"
echo " Gateway Image     : ${GATEWAY_IMAGE}"
echo " Worker Image      : ${WORKER_IMAGE}"
echo " Billing API Image : ${BILLING_API_IMAGE}"
echo "================================================================="

cd "${ROOT_DIR}/infra/terraform"

# Clean any stale generated tfvars
rm -f terraform.auto.tfvars.json

# Ensure backend.hcl exists
if [ ! -f "backend.hcl" ]; then
  cp backend.hcl.example backend.hcl
fi

terraform init -backend-config=backend.hcl -reconfigure

cat > terraform.auto.tfvars.json <<EOF
{
  "project_id": "${PROJECT_ID}",
  "region": "${REGION}",
  "gateway_image": "${GATEWAY_IMAGE}",
  "worker_image": "${WORKER_IMAGE}",
  "billing_api_image": "${BILLING_API_IMAGE}",
  "allowed_origins": ["https://ceoappdev.flutterflow.app"],
  "billing_api_allowed_origins": ["https://ceoappdev.flutterflow.app"],
  "billing_api_stripe_secret_key_secret_version": "1",
  "billing_api_stripe_webhook_signing_secret_id": "stripe-webhook-signing-secret-v3",
  "billing_api_stripe_webhook_signing_secret_version": "1",
  "billing_api_checkout_success_url": "https://ceoappdev.flutterflow.app/billing-complete?session_id={CHECKOUT_SESSION_ID}",
  "billing_api_checkout_cancel_url": "https://ceoappdev.flutterflow.app/billing-cancelled",
  "billing_enforcement_enabled": true
}
EOF


terraform apply -auto-approve

echo "================================================================="
echo " CEOsystem V3 Middleware Deployed Successfully!"
echo "================================================================="
terraform output
