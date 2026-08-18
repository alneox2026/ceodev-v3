#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Deploy the 2 Vertex AI Agent Platform Reasoning Engines
# ==============================================================================

PROJECT_ID="${PROJECT_ID:-ceo-dev123}"
REGION="${REGION:-us-central1}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

echo "================================================================="
echo " Deploying Vertex AI Agent Platform Reasoning Engines"
echo " Project ID : ${PROJECT_ID}"
echo " Region     : ${REGION}"
echo "================================================================="

# Ensure agents-cli or adk CLI is available
if ! command -v agents-cli &> /dev/null; then
  echo "--> Installing agents-cli and google-adk..."
  pip install --user "google-adk>=1.15.0" "google-cloud-aiplatform[agent-engines]>=1.130.0"
  export PATH="${HOME}/.local/bin:${PATH}"
fi

echo "--> [1/2] Deploying Maxima V3 Buffered to Agent Platform..."
(
  cd "${ROOT_DIR}/adkagents/maxima_v3"
  agents-cli install || true
  agents-cli deploy --project "${PROJECT_ID}" --region "${REGION}" --no-confirm-project
)

echo "--> [2/2] Deploying Maxima V3 Streaming to Agent Platform..."
(
  cd "${ROOT_DIR}/adkagents/maxima_agentruntime_streaming_v3"
  agents-cli install || true
  agents-cli deploy --project "${PROJECT_ID}" --region "${REGION}" --no-confirm-project
)

echo "================================================================="
echo " Vertex AI Agent Platform Reasoning Engines Deployed!"
echo "================================================================="
