#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Deploy the 2 Cloud Run ADK Agents
# ==============================================================================

PROJECT_ID="${PROJECT_ID:-ceo-dev123}"
REGION="${REGION:-us-central1}"
REPOSITORY="${REPOSITORY:-ceosystem}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

TAG="${TAG:-latest}"
MAXIMA_CLOUDRUN_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/maxima-cloudrun-v3:${TAG}"
MAXIMA_CLOUDRUN_STREAM_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/maxima-cloudrun-stream-v3:${TAG}"


echo "================================================================="
echo " Deploying Cloud Run ADK Agents"
echo " Project ID : ${PROJECT_ID}"
echo " Region     : ${REGION}"
echo " Image Tag  : ${TAG}"
echo "================================================================="

echo "--> [1/2] Deploying maxima-cloudrun-v3..."
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
  --port=8080 \
  --set-env-vars="MAXIMA_MODEL=gemini-2.5-flash,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION},PROJECT_ID=${PROJECT_ID}"

echo "--> [2/2] Deploying maxima-cloudrun-stream-v3..."
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
  --port=8080 \
  --set-env-vars="MAXIMA_MODEL=gemini-2.5-flash,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION},PROJECT_ID=${PROJECT_ID}"

echo "================================================================="
echo " Cloud Run ADK Agents Deployed Successfully!"
echo " Maxima CloudRun URL        : $(gcloud run services describe maxima-cloudrun-v3 --region "${REGION}" --project "${PROJECT_ID}" --format='value(status.url)')"
echo " Maxima Stream CloudRun URL : $(gcloud run services describe maxima-cloudrun-stream-v3 --region "${REGION}" --project "${PROJECT_ID}" --format='value(status.url)')"
echo "================================================================="
