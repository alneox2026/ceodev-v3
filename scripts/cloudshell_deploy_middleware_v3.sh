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

# Auto-detect latest built tags per service if not explicitly provided
if [ -z "${TAG:-}" ] || [ "${TAG}" = "latest" ]; then
  echo "--> Detecting newest middleware image tags in Artifact Registry..."
  GATEWAY_TAG="$(gcloud artifacts docker images list "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/ceoagent-gateway-v3" --include-tags --sort-by=~CREATE_TIME --limit=1 --format='value(tags)' 2>/dev/null | tr ',' '\n' | grep -v '^latest$' | head -n 1 || true)"
  WORKER_TAG="$(gcloud artifacts docker images list "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/ceoagent-persistence-worker-v3" --include-tags --sort-by=~CREATE_TIME --limit=1 --format='value(tags)' 2>/dev/null | tr ',' '\n' | grep -v '^latest$' | head -n 1 || true)"
  BILLING_API_TAG="$(gcloud artifacts docker images list "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/ceoagent-billing-api-v3" --include-tags --sort-by=~CREATE_TIME --limit=1 --format='value(tags)' 2>/dev/null | tr ',' '\n' | grep -v '^latest$' | head -n 1 || true)"
  GATEWAY_TAG="${GATEWAY_TAG:-latest}"
  WORKER_TAG="${WORKER_TAG:-latest}"
  BILLING_API_TAG="${BILLING_API_TAG:-latest}"
else
  GATEWAY_TAG="${TAG}"
  WORKER_TAG="${TAG}"
  BILLING_API_TAG="${TAG}"
fi

GATEWAY_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/ceoagent-gateway-v3:${GATEWAY_TAG}"
WORKER_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/ceoagent-persistence-worker-v3:${WORKER_TAG}"
BILLING_API_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/ceoagent-billing-api-v3:${BILLING_API_TAG}"


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
