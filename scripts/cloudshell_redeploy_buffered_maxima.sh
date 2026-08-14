#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-ceo-dev123}"
AGENT_REGION="${AGENT_REGION:-us-central1}"
GATEWAY_REGION="${GATEWAY_REGION:-us-central1}"
REPO="${REPO:-ceosystem}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "Project: ${PROJECT_ID}"
echo "Agent Runtime region: ${AGENT_REGION}"
echo "Gateway region: ${GATEWAY_REGION}"

gcloud config set project "$PROJECT_ID"

echo "Deploying Maxima to Agent Runtime..."
(
  cd adkagents/maxima_v3
  agents-cli install
  agents-cli deploy \
    --project "$PROJECT_ID" \
    --region "$AGENT_REGION" \
    --no-confirm-project
)

echo "Updating gateway agent registry from deployment_metadata.json..."
readarray -t RUNTIME_INFO < <(python3 - <<'PY'
import json
import pathlib
import re

metadata_path = pathlib.Path("adkagents/maxima_v3/deployment_metadata.json")
metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
runtime = metadata["remote_agent_runtime_id"]
match = re.search(r"/locations/([^/]+)/", runtime)
if not match:
    raise SystemExit(f"Could not parse region from runtime id: {runtime}")
region = match.group(1)

print(runtime)
print(region)
PY
)

MAXIMA_RESOURCE_NAME="${RUNTIME_INFO[0]}"
MAXIMA_RUNTIME_REGION="${RUNTIME_INFO[1]}"
echo "Maxima resource: ${MAXIMA_RESOURCE_NAME}"
echo "Maxima runtime region: ${MAXIMA_RUNTIME_REGION}"

TAG="$(git rev-parse --short HEAD)-$(date +%Y%m%d%H%M%S)"
GATEWAY_IMAGE="${GATEWAY_REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/ceoagent-gateway-v3:gateway-${TAG}"

cat > cloudbuild-gateway.yaml <<EOF
steps:
- name: gcr.io/cloud-builders/docker
  args: ["build", "-f", "services/agent_gateway_v3/Dockerfile", "-t", "${GATEWAY_IMAGE}", "."]
images:
- "${GATEWAY_IMAGE}"
EOF

echo "Building gateway image: ${GATEWAY_IMAGE}"
gcloud builds submit --project "$PROJECT_ID" --config cloudbuild-gateway.yaml .

echo "Deploying gateway..."
gcloud run services update ceoagent-gateway-v3 \
  --image "$GATEWAY_IMAGE" \
  --update-env-vars "AGENT_MAXIMA_RESOURCE_NAME=${MAXIMA_RESOURCE_NAME},AGENT_MAXIMA_REGION=${MAXIMA_RUNTIME_REGION}" \
  --region "$GATEWAY_REGION" \
  --project "$PROJECT_ID"

GATEWAY_URL="$(gcloud run services describe ceoagent-gateway-v3 \

  --region "$GATEWAY_REGION" \
  --project "$PROJECT_ID" \
  --format='value(status.url)')"

echo "Gateway URL: ${GATEWAY_URL}"
curl -i "${GATEWAY_URL}/health"
curl -i "${GATEWAY_URL}/ready"

echo
echo "Redeploy complete. Run the authenticated buffered smoke separately with a fresh Firebase token."
