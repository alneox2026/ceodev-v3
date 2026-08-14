#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# CEOsystem V3 Complete Stack Deployment Script for Google Cloud Shell
# ==============================================================================

PROJECT_ID="${PROJECT_ID:-ceo-dev123}"
REGION="${REGION:-us-central1}"
REPOSITORY="${REPOSITORY:-ceosystem}"

echo "================================================================="
echo " Starting Full Deployment of CEOsystem V3 Stack"
echo " Project ID : ${PROJECT_ID}"
echo " Region     : ${REGION}"
echo " Repository : ${REPOSITORY}"
echo "================================================================="

gcloud config set project "${PROJECT_ID}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

TAG="$(git rev-parse --short=12 HEAD)"
echo "Build Tag: ${TAG}"

# Ensure Artifact Registry repository exists
gcloud artifacts repositories describe "${REPOSITORY}" \
  --location="${REGION}" \
  --project="${PROJECT_ID}" >/dev/null 2>&1 || \
gcloud artifacts repositories create "${REPOSITORY}" \
  --repository-format=docker \
  --location="${REGION}" \
  --description="CEOsystem Docker Repository" \
  --project="${PROJECT_ID}"

# ------------------------------------------------------------------------------
# 1. Build and push all 5 container images via Cloud Build
# ------------------------------------------------------------------------------
GATEWAY_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/ceoagent-gateway-v3:${TAG}"
WORKER_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/ceoagent-persistence-worker-v3:${TAG}"
BILLING_API_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/ceoagent-billing-api-v3:${TAG}"
MAXIMA_CLOUDRUN_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/maxima-cloudrun-v3:${TAG}"
MAXIMA_CLOUDRUN_STREAM_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/maxima-cloudrun-stream-v3:${TAG}"

echo "--> [1/5] Building Cloud Run Agent (Buffered): ${MAXIMA_CLOUDRUN_IMAGE}"
gcloud builds submit adkagents/maxima_cloudrun_v3 \
  --tag="${MAXIMA_CLOUDRUN_IMAGE}" \
  --project="${PROJECT_ID}"

echo "--> [2/5] Building Cloud Run Agent (Stream): ${MAXIMA_CLOUDRUN_STREAM_IMAGE}"
gcloud builds submit adkagents/maxima_cloudrun_stream_v3 \
  --tag="${MAXIMA_CLOUDRUN_STREAM_IMAGE}" \
  --project="${PROJECT_ID}"

echo "--> [3/5] Building Gateway Image: ${GATEWAY_IMAGE}"
gcloud builds submit . \
  --config=<(cat <<EOF
steps:
- name: gcr.io/cloud-builders/docker
  args: ["build", "-f", "services/agent_gateway_v3/Dockerfile", "-t", "${GATEWAY_IMAGE}", "."]
images:
- "${GATEWAY_IMAGE}"
EOF
) --project="${PROJECT_ID}"

echo "--> [4/5] Building Persistence Worker Image: ${WORKER_IMAGE}"
gcloud builds submit . \
  --config=<(cat <<EOF
steps:
- name: gcr.io/cloud-builders/docker
  args: ["build", "-f", "services/agent_persistence_worker_v3/Dockerfile", "-t", "${WORKER_IMAGE}", "."]
images:
- "${WORKER_IMAGE}"
EOF
) --project="${PROJECT_ID}"

echo "--> [5/5] Building Billing API Image: ${BILLING_API_IMAGE}"
gcloud builds submit . \
  --config=<(cat <<EOF
steps:
- name: gcr.io/cloud-builders/docker
  args: ["build", "-f", "services/billing_api_v3/Dockerfile", "-t", "${BILLING_API_IMAGE}", "."]
images:
- "${BILLING_API_IMAGE}"
EOF
) --project="${PROJECT_ID}"

# ------------------------------------------------------------------------------
# 2. Deploy Cloud Run ADK Agents
# ------------------------------------------------------------------------------
echo "--> Deploying maxima-cloudrun-v3 service..."
gcloud run deploy maxima-cloudrun-v3 \
  --image="${MAXIMA_CLOUDRUN_IMAGE}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --platform=managed \
  --no-allow-unauthenticated \
  --min-instances=0 \
  --max-instances=20 \
  --memory=1Gi \
  --cpu=1 \
  --timeout=300s \
  --set-env-vars="MAXIMA_MODEL=gemini-2.5-flash,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION},PROJECT_ID=${PROJECT_ID}"

echo "--> Deploying maxima-cloudrun-stream-v3 service..."
gcloud run deploy maxima-cloudrun-stream-v3 \
  --image="${MAXIMA_CLOUDRUN_STREAM_IMAGE}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --platform=managed \
  --no-allow-unauthenticated \
  --min-instances=0 \
  --max-instances=20 \
  --memory=1Gi \
  --cpu=1 \
  --timeout=300s \
  --set-env-vars="MAXIMA_MODEL=gemini-2.5-flash,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION},PROJECT_ID=${PROJECT_ID}"


# ------------------------------------------------------------------------------
# 3. Deploy Middleware Infrastructure via Terraform
# ------------------------------------------------------------------------------
echo "--> Applying Terraform Infrastructure for Middleware V3..."
cd "${ROOT_DIR}/infra/terraform"

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
  "billing_api_checkout_success_url": "https://ceoappdev.flutterflow.app/billing-complete?session_id={CHECKOUT_SESSION_ID}",
  "billing_api_checkout_cancel_url": "https://ceoappdev.flutterflow.app/billing-cancelled"
}
EOF

terraform apply -auto-approve

echo "================================================================="
echo " CEOsystem V3 Stack Deployment Succeeded!"
echo "================================================================="
terraform output
