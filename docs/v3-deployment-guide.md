# CEOsystem V3 Deployment Guide & Operational Runbook

This document is the definitive guide and quick-reference manual for deploying and maintaining the **CEOsystem V3 isolated stack** on Google Cloud Platform (`ceo-dev123`, `us-central1`).

---

## 1. Stack Overview & Live URLs

* **GCP Project ID**: `ceo-dev123`
* **GCP Project Number**: `281577273798`
* **GCP Region**: `us-central1`
* **GitHub Repository**: `https://github.com/alneox2026/ceodev-v3`
* **Artifact Registry Repository**: `us-central1-docker.pkg.dev/ceo-dev123/ceosystem`
* **Terraform State**: `gs://ceo-dev123-tfstate/ceodev-v3/middleware`

### Live Production Endpoints

| Service / Resource | Live URL / Identifier | Ingress / Visibility |
| :--- | :--- | :--- |
| **Agent Gateway (V3)** | `https://ceoagent-gateway-v3-281577273798.us-central1.run.app` | Public (FlutterFlow Bearer Auth) |
| **Billing API (V3)** | `https://ceoagent-billing-api-v3-281577273798.us-central1.run.app` | Public (Stripe Webhooks & App Auth) |
| **Persistence Worker (V3)** | `https://ceoagent-persistence-worker-v3-281577273798.us-central1.run.app` | Private (Eventarc Pub/Sub Invocation) |
| **Cloud Run Agent (Buffered V3)** | `https://maxima-cloudrun-v3-281577273798.us-central1.run.app` | Private (Gateway IAM Auth) |
| **Cloud Run Agent (Stream V3)** | `https://maxima-cloudrun-stream-v3-281577273798.us-central1.run.app` | Private (Gateway IAM Auth) |
| **Agent Platform Agent (Buffered V3)** | `projects/281577273798/locations/us-central1/reasoningEngines/6357932034928672768` | Vertex AI Reasoning Engine |
| **Agent Platform Agent (Stream V3)** | `projects/281577273798/locations/us-central1/reasoningEngines/1267738556093169664` | Vertex AI Reasoning Engine |
| **CR Agent Session Backend (Buffered V3)** | `projects/281577273798/locations/us-central1/reasoningEngines/7597266357385691136` | Vertex AI Session Storage |
| **CR Agent Session Backend (Stream V3)** | `projects/281577273798/locations/us-central1/reasoningEngines/5253987176269479936` | Vertex AI Session Storage |
| **Pub/Sub Turn Topic** | `projects/ceo-dev123/topics/agent-turn-events-v3` | Managed Pub/Sub |
| **Eventarc Trigger** | `ceoagent-persistence-worker-v3-turn-events` | Cloud Run Eventarc Trigger |




---

## 2. Standard Deployment Workflow (Step-by-Step)

Open **Google Cloud Shell** and run the following modular steps:

### Step 1: Sync Code and Set Permissions
```bash
cd ~/ceodev-v3
git reset --hard origin/main
git pull origin main
chmod +x scripts/*.sh
```

---

### Step 2: Build All 5 Container Images
Builds and pushes the 5 container images to Artifact Registry, tagging both `:${TAG}` (commit hash) and `:latest`:
```bash
./scripts/cloudshell_build_images_v3.sh
```

**Images Built**:
1. `maxima-cloudrun-v3` (`adkagents/maxima_cloudrun_v3`)
2. `maxima-cloudrun-stream-v3` (`adkagents/maxima_cloudrun_stream_v3`)
3. `ceoagent-gateway-v3` (`services/agent_gateway_v3`)
4. `ceoagent-persistence-worker-v3` (`services/agent_persistence_worker_v3`)
5. `ceoagent-billing-api-v3` (`services/billing_api_v3`)

---

### Step 3: Deploy the 2 Cloud Run ADK Agents
Deploys `maxima-cloudrun-v3` and `maxima-cloudrun-stream-v3` with private authentication, 0-to-20 scaling, and Agent Platform session integration:
```bash
./scripts/cloudshell_deploy_agents_v3.sh
```

---

### Step 4: Deploy the Middleware Infrastructure (Terraform)
Automatically detects the latest built images from Artifact Registry, configures isolated remote state, and applies the full Terraform stack:
```bash
./scripts/cloudshell_deploy_middleware_v3.sh
```

**Resources Created**:
* Cloud Run Services: `ceoagent-gateway-v3`, `ceoagent-persistence-worker-v3`, `ceoagent-billing-api-v3`
* Service Accounts: `ceoagent-gateway-sa-v3`, `ceoagent-worker-sa-v3`, `ceoagent-billing-api-sa-v3`, `ceoagent-eventarc-sa-v3`, `ceoagent-reconciler-sa-v3`
* Pub/Sub Topic: `agent-turn-events-v3`
* Eventarc Trigger: `ceoagent-persistence-worker-v3-turn-events`
* Cloud Scheduler Job: `ceoagent-persistence-worker-v3-billing-reconciliation`
* Cloud Monitoring Alert Policies & Log Metric: `worker_retryable_failures_v3`

---

### Step 5: Deploy Vertex AI Agent Platform Agents (Optional / As Needed)
Deploys the 2 Agent Platform reasoning engines:
```bash
./scripts/cloudshell_deploy_reasoning_engines_v3.sh
```

---

## 3. Master 1-Click Deployment

To run the entire build, agent deployment, and middleware provisioning in a single automated command:

```bash
cd ~/ceodev-v3
git reset --hard origin/main
git pull origin main
chmod +x scripts/*.sh
./scripts/cloudshell_deploy_all_v3.sh
```

---

## 4. Verification & Health Checks

Verify that the services are online and responding correctly:

```bash
# 1. Gateway Health & Readiness
curl -s https://ceoagent-gateway-v3-281577273798.us-central1.run.app/health
# Expected: {"ok":true,"service":"agent-gateway","status":"healthy"}

curl -s https://ceoagent-gateway-v3-281577273798.us-central1.run.app/ready
# Expected: {"ok":true,"service":"agent-gateway","status":"ready"}

# 2. Billing API Health & Readiness
curl -s https://ceoagent-billing-api-v3-281577273798.us-central1.run.app/health
# Expected: {"ok":true,"service":"billing-api","status":"healthy","catalog_schema_version":1,"catalog_environment":"test"}

curl -s https://ceoagent-billing-api-v3-281577273798.us-central1.run.app/ready
# Expected: {"ok":true,"service":"billing-api","status":"ready"}
```

---

## 5. Critical Gotchas & Rules for Future Deployments

### 1. GCP Service Account ID Length Constraint (<= 30 Chars)
* **Rule**: Google Cloud enforces a strict maximum length of **30 characters** on Service Account `account_id`s.
* **Bad**: `ceoagent-billing-reconciler-sa-v3` (33 characters -> Causes Terraform Error)
* **Good**: `ceoagent-reconciler-sa-v3` (25 characters)

### 2. Cloud Monitoring Metric Names Are Project-Global
* **Rule**: Logging metrics (`google_logging_metric`) exist in the global namespace of the GCP project.
* **Bad**: Using generic names like `worker_retryable_failures` (causes `Error 409: Metric already exists` if a previous deployment created it).
* **Good**: Suffix with version: `worker_retryable_failures_v3`.

### 3. Image Tagging & Resolution Strategy
* **Rule**: Always tag both `:${TAG}` (commit hash) AND `:latest` in `cloudbuild`.
* **Rule**: The Terraform deployment script automatically inspects Artifact Registry for the newest tag, preventing 404 image errors when updating non-code files.

### 4. Cloud Run Docker Entrypoint & Port Binding
* **Rule**: Cloud Run dynamically injects the `$PORT` environment variable (default `8080`).
* **Dockerfile CMD**: Must use `sh -c` to expand `$PORT` at runtime:
  ```dockerfile
  CMD ["sh", "-c", "python -m uvicorn app.fast_api_app:app --host 0.0.0.0 --port ${PORT:-8080}"]
  ```

### 5. ADK Agent Platform Session Initialization
* **Rule**: When initializing Vertex AI Agent Platform session backends in `fast_api_app.py`, always wrap `vertexai.init(...)` and `agent_engines.list(...)` in a `try/except` block with fallback to local sessions. If Vertex AI is slow or credentials take a second to resolve, the FastAPI container will still boot immediately and pass Cloud Run health checks.

### 6. Instance Scaling Constraints
* **Rule**: Cloud Run services must have `min_instances = 0` and `max_instances = 20` to prevent quota exhaustion and unexpected idle compute costs.

---

## 6. Troubleshooting Commands

### Inspect Cloud Run Live Startup Logs
```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=ceoagent-gateway-v3" \
  --limit=50 \
  --project=ceo-dev123 \
  --format="value(textPayload,jsonPayload.message)"
```

### Inspect Persistence Worker Eventarc Logs
```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=ceoagent-persistence-worker-v3" \
  --limit=50 \
  --project=ceo-dev123 \
  --format="value(textPayload,jsonPayload.message)"
```

### Inspect Billing API Logs
```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=ceoagent-billing-api-v3" \
  --limit=50 \
  --project=ceo-dev123 \
  --format="value(textPayload,jsonPayload.message)"
```
