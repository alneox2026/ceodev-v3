# Middleware V3 Deployment Runbook

This runbook covers the isolated deployment of the V3 middleware stack:

- public Cloud Run gateway (`ceoagent-gateway-v3`)
- authenticated Cloud Run persistence worker (`ceoagent-persistence-worker-v3`)
- public Stripe Billing API (`ceoagent-billing-api-v3`)
- Pub/Sub topic for completed turn events (`agent-turn-events-v3`)
- Eventarc trigger from Pub/Sub to the worker

## 1. Build and push container images

Preferred path:

```powershell
.\scripts\build_images.ps1
```

Manual equivalent:

```bash
docker build -f services/agent_gateway_v3/Dockerfile -t us-central1-docker.pkg.dev/ceo-dev123/ceosystem/ceoagent-gateway-v3:latest .
docker push us-central1-docker.pkg.dev/ceo-dev123/ceosystem/ceoagent-gateway-v3:latest
docker build -f services/agent_persistence_worker_v3/Dockerfile -t us-central1-docker.pkg.dev/ceo-dev123/ceosystem/ceoagent-persistence-worker-v3:latest .
docker push us-central1-docker.pkg.dev/ceo-dev123/ceosystem/ceoagent-persistence-worker-v3:latest
docker build -f services/billing_api_v3/Dockerfile -t us-central1-docker.pkg.dev/ceo-dev123/ceosystem/ceoagent-billing-api-v3:latest .
docker push us-central1-docker.pkg.dev/ceo-dev123/ceosystem/ceoagent-billing-api-v3:latest
```

## 2. Prepare Terraform variables

Copy [terraform.tfvars.example](/c:/Users/Admin/Desktop/ANTIGRAVITY/CEOsystem-dev3/infra/terraform/terraform.tfvars.example) to `terraform.tfvars` and fill in the real image URIs.

Launch defaults for this repo:

- `allowed_origins = ["https://ceoappdev.flutterflow.app"]`
- request-based billing for both Cloud Run services
- second-generation execution environment for both Cloud Run services
- gateway `min_instances = 1`
- worker `min_instances = 0`
- Billing API `min_instances = 0`, `max_instances = 20`, and concurrency `32`

For the Billing API, the existing test Stripe Secret Manager secret must be
named `stripe-secret-key` (or the matching Terraform variable must be changed)
and the secret version must be pinned. Terraform manages only its runtime IAM
binding; it never writes the Stripe secret value. Leave the webhook signing
secret variables empty until the signed webhook route has been deployed.

Optionally add `alert_notification_channels` if you already have Cloud Monitoring notification channel resource names configured.

## 2a. Configure remote Terraform state

Do not keep production Terraform state only in a Cloud Shell home directory. Use a GCS backend.

1. Create a state bucket once:

```bash
gcloud storage buckets create gs://ceo-dev123-tfstate \
  --project=ceo-dev123 \
  --location=us-central1 \
  --uniform-bucket-level-access
```

2. Copy [backend.hcl.example](/c:/Users/Admin/Desktop/ANTIGRAVITY/CEOsystem-dev3/infra/terraform/backend.hcl.example) to `backend.hcl` and adjust the bucket or prefix (`prefix = "ceodev-v3/middleware"`).


3. Initialize Terraform with the backend:

```bash
terraform init -backend-config=backend.hcl -reconfigure
```

## 3. Apply infrastructure

Preferred path:

```powershell
.\scripts\deploy_infra.ps1 `
  -GatewayImage "us-central1-docker.pkg.dev/ceo-dev123/ceosystem/ceoagent-gateway-v3:latest" `
  -WorkerImage "us-central1-docker.pkg.dev/ceo-dev123/ceosystem/ceoagent-persistence-worker-v3:latest" `
  -BillingApiImage "us-central1-docker.pkg.dev/ceo-dev123/ceosystem/ceoagent-billing-api-v3:latest" `
  -AllowedOrigins "https://ceoappdev.flutterflow.app" `
  -BillingApiCheckoutSuccessUrl "https://ceoappdev.flutterflow.app/billing-complete?session_id={CHECKOUT_SESSION_ID}" `
  -BillingApiCheckoutCancelUrl "https://ceoappdev.flutterflow.app/billing-cancelled"
```

Manual equivalent from [infra/terraform](/c:/Users/Admin/Desktop/ANTIGRAVITY/CEOsystem-dev3/infra/terraform):

```bash
terraform init -backend-config=backend.hcl -reconfigure
terraform plan
terraform apply
```

This Terraform stack creates:

- the gateway Cloud Run service (`ceoagent-gateway-v3`)
- the worker Cloud Run service (`ceoagent-persistence-worker-v3`)
- the Billing API Cloud Run service (`ceoagent-billing-api-v3`) and its separate runtime service account
- service accounts with least-privilege runtime roles
- the `agent-turn-events-v3` Pub/Sub topic

- the Eventarc trigger that invokes the worker on `/events/pubsub`
- Cloud Monitoring alert policies for:
  - gateway 5xx responses
  - elevated gateway p95 latency
  - worker retryable failures

After apply, record the deterministic service URLs from Terraform outputs:

- `gateway_url`
- `worker_url`
- `billing_api_url`

Use `gateway_url` as the canonical FlutterFlow base URL.

## 4. Smoke test the gateway

Use [smoke_gateway.ps1](/c:/Users/Admin/Desktop/ANTIGRAVITY/CEOsystem-dev3/scripts/smoke_gateway.ps1).

Full rollout helper:

```powershell
.\scripts\rollout_maxima.ps1 `
  -AuthToken "FIREBASE_ID_TOKEN" `
  -AllowedOrigins "https://ceoappdev.flutterflow.app"
```

By default, `rollout_maxima.ps1` now runs the buffered smoke path only. Add `-IncludeStreamingSmoke` only when you are explicitly validating the SSE endpoint.

Buffered test:

```powershell
.\scripts\smoke_gateway.ps1 `
  -ServiceUrl "https://YOUR_GATEWAY_URL" `
  -AuthToken "FIREBASE_ID_TOKEN" `
  -Message "Hello from the new gateway"
```

Streaming test:

```powershell
.\scripts\smoke_gateway.ps1 `
  -ServiceUrl "https://YOUR_GATEWAY_URL" `
  -AuthToken "FIREBASE_ID_TOKEN" `
  -Message "Hello from the new streaming gateway" `
  -Stream
```

## 5. Verify the full path

Confirm all of the following:

1. `GET /ready` returns `200`
2. gateway returns `reply_text` for buffered chat
3. unauthenticated buffered chat returns `401`
4. Pub/Sub topic receives events
5. worker logs show `worker_event_persisted`
6. Firestore receives:
   - `agent_threads_v3/{thread_id}`
   - `agent_threads_v3/{thread_id}/messages_v3/{turn_id}_user`
   - `agent_threads_v3/{thread_id}/messages_v3/{turn_id}_assistant`
7. archive action returns `status = "archived"`
8. delete action returns `status = "deleted"` and worker logs show `worker_thread_delete_processed`
9. Cloud Run Error Reporting remains empty for both services during the verification window

If prepaid agent-token billing is enabled, also follow
[billing-wallet-setup.md](billing-wallet-setup.md) before the FlutterFlow
cutover. In particular, test a funded wallet, an insufficient wallet, and an
expired reservation before turning on customer charging.

Optional backend regression:

- run a streaming smoke test and confirm `metadata`, `token`, and final `done`

## 6. Cutover rule

Do not switch FlutterFlow to the new gateway until:

1. buffered smoke test passes
2. worker persistence is visible in Firestore
3. duplicate delivery test confirms no duplicate messages
4. archive/delete lifecycle is validated end-to-end
5. rollback path to the legacy `main.py` service remains available

For the Maxima launch, keep FlutterFlow on the buffered endpoint only:

- `POST /v1/agents/maxima/chat`
- `POST /v1/agents/maxima/threads/{thread_id}/archive`
- `POST /v1/agents/maxima/threads/{thread_id}/delete`

Do not wire the streaming endpoint into FlutterFlow until the buffered launch has a stable production window.

## 7. Rollback

Use the one-page runbook: [maxima-rollback-runbook.md](/c:/Users/Admin/Desktop/ANTIGRAVITY/CEOsystem-dev3/docs/maxima-rollback-runbook.md)

## 8. Script inventory

- [build_images.ps1](/c:/Users/Admin/Desktop/ANTIGRAVITY/CEOsystem-dev3/scripts/build_images.ps1): build and push all three container images
- [deploy_infra.ps1](/c:/Users/Admin/Desktop/ANTIGRAVITY/CEOsystem-dev3/scripts/deploy_infra.ps1): write Terraform vars, run `init`, `plan`, and optionally `apply`
- [rollout_maxima.ps1](/c:/Users/Admin/Desktop/ANTIGRAVITY/CEOsystem-dev3/scripts/rollout_maxima.ps1): build, deploy, fetch the deterministic gateway URL, and run buffered smoke tests (streaming optional)
- [smoke_gateway.ps1](/c:/Users/Admin/Desktop/ANTIGRAVITY/CEOsystem-dev3/scripts/smoke_gateway.ps1): direct buffered or stream call against an existing gateway URL

## Sources

- ADK Agent Runtime testing guide: [adk.dev/deploy/agent-runtime/test](https://adk.dev/deploy/agent-runtime/test/)
- Cloud Run service identity: [cloud.google.com/run/docs/configuring/services/service-identity](https://cloud.google.com/run/docs/configuring/services/service-identity)
- Eventarc Pub/Sub to Cloud Run Terraform: [cloud.google.com/eventarc/standard/docs/run/create-trigger-pub-sub-terraform](https://cloud.google.com/eventarc/standard/docs/run/create-trigger-pub-sub-terraform)
- Pub/Sub publisher roles: [cloud.google.com/pubsub/docs/publisher](https://cloud.google.com/pubsub/docs/publisher)
