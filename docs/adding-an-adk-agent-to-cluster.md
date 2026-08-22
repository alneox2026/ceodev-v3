# Adding an ADK Agent to the V3 Middleware Cluster

This guide explains how to connect and register any new Google ADK agent (the 5th, 6th, or 100th agent) to your existing V3 Middleware Cluster (**Gateway**, **Persistence Worker**, **Billing API**, and **Firestore**).

---

## Architecture Overview

In the CEOsystem V3 modular architecture, the **Middleware Cluster** acts as a unified facade for your agents:

```
┌────────────────────────────────────────────────────────────────────────┐
│                      FlutterFlow SuperApp Client                       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ (Firebase Auth JWT)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   V3 Gateway (ceoagent-gateway-v3)                     │
│  - Verifies user auth & holds $0.05 reservation                        │
│  - Looks up agent in config/agents.*.yaml                              │
│  - Routes request & streams SSE tokens back to FlutterFlow             │
│  - Publishes turn-completed event to Pub/Sub                           │
└──────────────┬──────────────────────────────────────────┬──────────────┘
               │                                          │
               ▼ (agent_runtime)                          ▼ (cloud_run_adk)
┌──────────────────────────────┐          ┌──────────────────────────────┐
│  Vertex AI Agent Platform    │          │     Google Cloud Run         │
│  Reasoning Engine            │          │     ADK Container Service    │
│  (Existing or New Agent)     │          │     (Existing or New Agent)  │
└──────────────────────────────┘          └──────────────┬───────────────┘
                                                         │ (Sessions)
                                                         ▼
                                          ┌──────────────────────────────┐
                                          │  Agent Platform Session Store│
                                          │  (Dedicated Reasoning Engine)│
                                          └──────────────────────────────┘
                                                         │
                                    ┌────────────────────┘
                                    ▼ (Pub/Sub Event)
┌────────────────────────────────────────────────────────────────────────┐
│          Persistence Worker (ceoagent-persistence-worker-v3)           │
│  - Computes exact token cost from model catalog                        │
│  - Saves chat history to agent_threads_v3 & messages_v3                │
│  - Settles micro-charge on customer_wallets_v3 & releases hold         │
│  - Writes immutable audit entry to agent_billing_ledger_v3             │
└────────────────────────────────────────────────────────────────────────┘
```

Your agent code does **not** need to live inside this repository. As long as the agent is deployed to **Vertex AI Agent Platform** or **Google Cloud Run**, you can connect it in 5 simple steps.

---

## Step 1: Obtain the Agent Deployment Details

Before registering the agent, obtain its deployment identifier depending on how it was deployed:

### Option A: Agent Deployed to Vertex AI Agent Platform (Reasoning Engine)
You need the **full Resource Name**:
```text
projects/{PROJECT_ID}/locations/{REGION}/reasoningEngines/{ENGINE_ID}
```
*Example*: `projects/ceo-dev123/locations/us-central1/reasoningEngines/8472910482910394857`

### Option B: Agent Deployed to Google Cloud Run (Containerized ADK)
You need two pieces of information:
1. **Cloud Run Base URL**:
   ```text
   https://my-specialist-agent-v3-281577273798.us-central1.run.app
   ```
2. **Dedicated Session Engine Resource Name** (if using Agent Platform for session storage):
   ```text
   projects/ceo-dev123/locations/us-central1/reasoningEngines/{SESSION_ENGINE_ID}
   ```

---

## Step 2: Configure IAM Permissions (Invocation Access)

The Gateway runs under its own Google Cloud Service Account (e.g., `ceoagent-gateway-v3-sa@ceo-dev123.iam.gserviceaccount.com` or your compute default service account). It must have permission to invoke the new agent.

### For Agent Platform (Reasoning Engine):
The Gateway service account needs `roles/aiplatform.user`:
```bash
gcloud projects add-iam-policy-binding ceo-dev123 \
  --member="serviceAccount:281577273798-compute@developer.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```

### For Cloud Run Agents:
The Gateway service account needs `roles/run.invoker` on the new Cloud Run service:
```bash
gcloud run services add-iam-policy-binding my-specialist-agent-v3 \
  --region=us-central1 \
  --project=ceo-dev123 \
  --member="serviceAccount:281577273798-compute@developer.gserviceaccount.com" \
  --role="roles/run.invoker"
```

---

## Step 3: Register the Agent in the Gateway Registry

Open the configuration files in this repository:
- `config/agents.dev.yaml`
- `config/agents.prod.yaml`

Add the new agent entry under the `agents:` mapping:

### Example 1: New Agent on Vertex AI Agent Platform
```yaml
agents:
  # ... existing agents ...

  legal_advisor_v3:
    agent_id: legal_advisor_v3
    backend: agent_runtime
    resource_name: projects/ceo-dev123/locations/us-central1/reasoningEngines/8472910482910394857
    region: us-central1
    streaming_enabled: true          # Set true for SSE streaming, false for buffered
    persistence_enabled: true        # Enables token billing & message history
    auth_policy: firebase
```

### Example 2: New Agent on Google Cloud Run
```yaml
agents:
  # ... existing agents ...

  code_reviewer_v3:
    agent_id: code_reviewer_v3
    backend: cloud_run_adk
    base_url: https://code-reviewer-v3-281577273798.us-central1.run.app
    app_name: app
    region: us-central1
    streaming_enabled: true          # Set true for SSE streaming, false for buffered
    persistence_enabled: true        # Enables token billing & message history
    auth_policy: firebase
    runtime_session_cleanup: cloud_run_adk
```

### Configuration Fields Reference

| Field | Type | Description |
| :--- | :--- | :--- |
| `agent_id` | string | Unique identifier (`[a-z0-9_-]+`). Used in the FlutterFlow API URL. |
| `backend` | string | Either `agent_runtime` (Vertex AI) or `cloud_run_adk` (Cloud Run). |
| `resource_name` | string | Full Vertex AI resource path (Required for `agent_runtime`). |
| `base_url` | string | HTTPS URL of the Cloud Run service (Required for `cloud_run_adk`). |
| `app_name` | string | ADK FastAPI sub-app name (usually `"app"` for Cloud Run). |
| `region` | string | GCP region (`"us-central1"`). |
| `streaming_enabled`| boolean| Set `true` if the agent supports Server-Sent Events (SSE). |
| `persistence_enabled`| boolean| Set `true` to record turns in Firestore and settle wallet usage. |
| `auth_policy` | string | `"firebase"` (enforces user authentication). |

---

## Step 4: Verify Pricing / Model Catalog (Worker)

If your new agent uses **Gemini 2.5 Flash** or **Gemini 2.5 Pro**, the pricing rates are already built-in!

If the new agent uses a different model (e.g., Claude, GPT-4o, or a custom open model), verify or add the model pricing rate in `config/billing.test.yaml` and `config/billing.prod.yaml`:

```yaml
models:
  gemini-2.5-flash:
    input_usd_per_million: 0.30
    output_usd_per_million: 2.50
  
  # Example: Adding a new model
  claude-3-5-sonnet:
    input_usd_per_million: 3.00
    output_usd_per_million: 15.00
```

The Persistence Worker automatically looks up the model returned in the turn metadata, matches the rate, and debits the user's wallet with nano-cent accuracy.

---

## Step 5: Deploy the Updated Gateway to Cloud Shell

Commit and push the registry changes:

```bash
git add config/agents.dev.yaml config/agents.prod.yaml config/billing.*.yaml
git commit -m "feat(agents): register legal_advisor_v3 in middleware cluster"
git push origin main
```

In Google Cloud Shell, rebuild the images and redeploy the middleware:

```bash
cd ~/ceodev-v3
git fetch origin main
git reset --hard origin/main
bash ./scripts/cloudshell_build_images_v3.sh
bash ./scripts/cloudshell_deploy_middleware_v3.sh
```

---

## Step 6: Connect from FlutterFlow

Once deployed, the new agent is **immediately available** to your FlutterFlow SuperApp at standard REST and SSE streaming endpoints:

### 1. Streaming Chat Endpoint (SSE)
```http
POST https://ceoagent-gateway-v3-281577273798.us-central1.run.app/v1/agents/{agent_id}/chat/stream
Headers:
  Authorization: Bearer <FIREBASE_ID_TOKEN>
  Content-Type: application/json
Body:
  {
    "message": "Hello! Can you help me review this contract?",
    "thread_id": "optional-thread-id"
  }
```

### 2. Buffered Chat Endpoint (JSON)
```http
POST https://ceoagent-gateway-v3-281577273798.us-central1.run.app/v1/agents/{agent_id}/chat
Headers:
  Authorization: Bearer <FIREBASE_ID_TOKEN>
  Content-Type: application/json
Body:
  {
    "message": "Hello!",
    "thread_id": "optional-thread-id"
  }
```

### 3. Thread Management
* **Archive Thread**: `POST /v1/agents/{agent_id}/threads/{thread_id}/archive`
* **Delete Thread**: `POST /v1/agents/{agent_id}/threads/{thread_id}/delete`

---

## Summary

To add any new agent to your cluster:
1. Deploy agent to Vertex AI Agent Platform or Cloud Run.
2. Grant IAM invocation permissions to Gateway service account.
3. Add the agent entry to `config/agents.prod.yaml` (and `dev.yaml`).
4. Rebuild and redeploy the Gateway via Cloud Shell (`cloudshell_deploy_middleware_v3.sh`).
5. Call `/v1/agents/{new_agent_id}/chat/stream` from FlutterFlow!
