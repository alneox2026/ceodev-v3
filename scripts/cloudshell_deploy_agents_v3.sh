#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Deploy the 2 Cloud Run ADK Agents with Dedicated Agent Platform Sessions
# ==============================================================================

PROJECT_ID="${PROJECT_ID:-ceo-dev123}"
REGION="${REGION:-us-central1}"
REPOSITORY="${REPOSITORY:-ceosystem}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

# Auto-detect latest built tags if not explicitly provided
if [ -z "${TAG:-}" ] || [ "${TAG}" = "latest" ]; then
  echo "--> Detecting newest agent image tags in Artifact Registry..."
  MAXIMA_TAG="$(gcloud artifacts docker images list "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/maxima-cloudrun-v3" --include-tags --sort-by=~CREATE_TIME --limit=1 --format='value(tags)' 2>/dev/null | tr ',' '\n' | grep -v '^latest$' | head -n 1 || true)"
  MAXIMA_STREAM_TAG="$(gcloud artifacts docker images list "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/maxima-cloudrun-stream-v3" --include-tags --sort-by=~CREATE_TIME --limit=1 --format='value(tags)' 2>/dev/null | tr ',' '\n' | grep -v '^latest$' | head -n 1 || true)"
  MAXIMA_TAG="${MAXIMA_TAG:-latest}"
  MAXIMA_STREAM_TAG="${MAXIMA_STREAM_TAG:-latest}"
else
  MAXIMA_TAG="${TAG}"
  MAXIMA_STREAM_TAG="${TAG}"
fi

MAXIMA_CLOUDRUN_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/maxima-cloudrun-v3:${MAXIMA_TAG}"
MAXIMA_CLOUDRUN_STREAM_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/maxima-cloudrun-stream-v3:${MAXIMA_STREAM_TAG}"


# Dedicated V3 Agent Platform Session Resource IDs
SESSION_RESOURCE_BUFFERED="projects/281577273798/locations/us-central1/reasoningEngines/7597266357385691136"
SESSION_RESOURCE_STREAMING="projects/281577273798/locations/us-central1/reasoningEngines/5253987176269479936"

echo "================================================================="
echo " Deploying Cloud Run ADK Agents (V3)"
echo " Project ID : ${PROJECT_ID}"
echo " Region     : ${REGION}"
echo " Image Tag  : ${TAG}"
echo "================================================================="

echo "--> [1/2] Deploying maxima-cloudrun-v3 with dedicated Agent Platform session backend..."
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
  --set-env-vars="GOOGLE_GENAI_USE_VERTEXAI=True,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION},PROJECT_ID=${PROJECT_ID},MAXIMA_MODEL=gemini-2.5-flash,AGENT_VERSION=0.1.0,APP_URL=https://maxima-cloudrun-v3-281577273798.us-central1.run.app,AGENT_ENGINE_RESOURCE_NAME=${SESSION_RESOURCE_BUFFERED},AGENT_ENGINE_SESSION_NAME=maxima-cloudrun-v3-sessions"

echo "--> [2/2] Deploying maxima-cloudrun-stream-v3 with dedicated Agent Platform session backend..."
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
  --set-env-vars="GOOGLE_GENAI_USE_VERTEXAI=True,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION},PROJECT_ID=${PROJECT_ID},MAXIMA_MODEL=gemini-2.5-flash,AGENT_VERSION=0.1.0,APP_URL=https://maxima-cloudrun-stream-v3-281577273798.us-central1.run.app,AGENT_ENGINE_RESOURCE_NAME=${SESSION_RESOURCE_STREAMING},AGENT_ENGINE_SESSION_NAME=maxima-cloudrun-stream-v3-sessions"

echo "================================================================="
echo " Cloud Run ADK Agents Deployed Successfully!"
echo " Maxima CloudRun URL        : $(gcloud run services describe maxima-cloudrun-v3 --region "${REGION}" --project "${PROJECT_ID}" --format='value(status.url)')"
echo " Maxima Stream CloudRun URL : $(gcloud run services describe maxima-cloudrun-stream-v3 --region "${REGION}" --project "${PROJECT_ID}" --format='value(status.url)')"
echo "================================================================="
