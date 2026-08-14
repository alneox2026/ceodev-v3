#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Build & Push All 5 Container Images to Google Artifact Registry
# ==============================================================================

PROJECT_ID="${PROJECT_ID:-ceo-dev123}"
REGION="${REGION:-us-central1}"
REPOSITORY="${REPOSITORY:-ceosystem}"

echo "================================================================="
echo " Building Container Images for CEOsystem V3"
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

echo "================================================================="
echo " All 5 Container Images Built & Pushed Successfully!"
echo " Gateway Image      : ${GATEWAY_IMAGE}"
echo " Worker Image       : ${WORKER_IMAGE}"
echo " Billing API Image  : ${BILLING_API_IMAGE}"
echo " Maxima CR Image    : ${MAXIMA_CLOUDRUN_IMAGE}"
echo " Maxima Stream CR   : ${MAXIMA_CLOUDRUN_STREAM_IMAGE}"
echo "================================================================="
