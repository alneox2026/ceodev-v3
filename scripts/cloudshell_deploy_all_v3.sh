#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Master Orchestration Script: Full Deployment of CEOsystem V3 Stack
# ==============================================================================

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

export TAG="${TAG:-$(git rev-parse --short=12 HEAD)}"

echo "================================================================="
echo " Starting End-to-End CEOsystem V3 Deployment"
echo " Git Commit / Release Tag: ${TAG}"
echo "================================================================="

# Step 1: Build all 5 container images via Cloud Build
bash "${ROOT_DIR}/scripts/cloudshell_build_images_v3.sh"

# Step 2: Deploy the 2 Cloud Run ADK Agents
bash "${ROOT_DIR}/scripts/cloudshell_deploy_agents_v3.sh"

# Step 3: Deploy the Middleware Infrastructure (Terraform)
bash "${ROOT_DIR}/scripts/cloudshell_deploy_middleware_v3.sh"


echo "================================================================="
echo " ALL CLOUD RUN SERVICES & AGENTS DEPLOYED SUCCESSFULLY!"
echo "================================================================="
