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
GATEWAY_LATEST="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/ceoagent-gateway-v3:latest"

WORKER_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/ceoagent-persistence-worker-v3:${TAG}"
WORKER_LATEST="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/ceoagent-persistence-worker-v3:latest"

BILLING_API_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/ceoagent-billing-api-v3:${TAG}"
BILLING_API_LATEST="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/ceoagent-billing-api-v3:latest"

MAXIMA_CLOUDRUN_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/maxima-cloudrun-v3:${TAG}"
MAXIMA_CLOUDRUN_LATEST="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/maxima-cloudrun-v3:latest"

MAXIMA_CLOUDRUN_STREAM_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/maxima-cloudrun-stream-v3:${TAG}"
MAXIMA_CLOUDRUN_STREAM_LATEST="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/maxima-cloudrun-stream-v3:latest"

echo "--> [1/5] Building Cloud Run Agent (Buffered): ${MAXIMA_CLOUDRUN_IMAGE}"
gcloud builds submit adkagents/maxima_cloudrun_v3 \
  --config=<(cat <<EOF
steps:
- name: gcr.io/cloud-builders/docker
  args: ["build", "-t", "${MAXIMA_CLOUDRUN_IMAGE}", "-t", "${MAXIMA_CLOUDRUN_LATEST}", "."]
images:
- "${MAXIMA_CLOUDRUN_IMAGE}"
- "${MAXIMA_CLOUDRUN_LATEST}"
EOF
) --project="${PROJECT_ID}"

echo "--> [2/5] Building Cloud Run Agent (Stream): ${MAXIMA_CLOUDRUN_STREAM_IMAGE}"
gcloud builds submit adkagents/maxima_cloudrun_stream_v3 \
  --config=<(cat <<EOF
steps:
- name: gcr.io/cloud-builders/docker
  args: ["build", "-t", "${MAXIMA_CLOUDRUN_STREAM_IMAGE}", "-t", "${MAXIMA_CLOUDRUN_STREAM_LATEST}", "."]
images:
- "${MAXIMA_CLOUDRUN_STREAM_IMAGE}"
- "${MAXIMA_CLOUDRUN_STREAM_LATEST}"
EOF
) --project="${PROJECT_ID}"

echo "--> [3/5] Building Gateway Image: ${GATEWAY_IMAGE}"
gcloud builds submit . \
  --config=<(cat <<EOF
steps:
- name: gcr.io/cloud-builders/docker
  args: ["build", "-f", "services/agent_gateway_v3/Dockerfile", "-t", "${GATEWAY_IMAGE}", "-t", "${GATEWAY_LATEST}", "."]
images:
- "${GATEWAY_IMAGE}"
- "${GATEWAY_LATEST}"
EOF
) --project="${PROJECT_ID}"

echo "--> [4/5] Building Persistence Worker Image: ${WORKER_IMAGE}"
gcloud builds submit . \
  --config=<(cat <<EOF
steps:
- name: gcr.io/cloud-builders/docker
  args: ["build", "-f", "services/agent_persistence_worker_v3/Dockerfile", "-t", "${WORKER_IMAGE}", "-t", "${WORKER_LATEST}", "."]
images:
- "${WORKER_IMAGE}"
- "${WORKER_LATEST}"
EOF
) --project="${PROJECT_ID}"

echo "--> [5/5] Building Billing API Image: ${BILLING_API_IMAGE}"
gcloud builds submit . \
  --config=<(cat <<EOF
steps:
- name: gcr.io/cloud-builders/docker
  args: ["build", "-f", "services/billing_api_v3/Dockerfile", "-t", "${BILLING_API_IMAGE}", "-t", "${BILLING_API_LATEST}", "."]
images:
- "${BILLING_API_IMAGE}"
- "${BILLING_API_LATEST}"
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
