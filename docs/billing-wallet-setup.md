# Prepaid agent-token billing setup

This is the first billing layer for the gateway. It charges the recorded Gemini
token estimate only; it does not yet allocate Cloud Run, Agent Runtime,
Firestore, Storage, tax, or payment-provider costs.

The $5 monthly service fee is recorded as a separate pending line item in each
active customer billing period. It is not automatically collected until the
Billing API's verified Stripe payment/webhook flow is deployed.

## Do not create or write wallets from FlutterFlow

Firestore creates collections automatically on their first backend write. Do
not create the following collections in FlutterFlow, and do not let a client
create, update, delete, or top up any document in them:

- `customer_wallets_v3`
- `billing_reservations_v3`
- `wallet_transactions_v3`
- `customer_billing_periods_v3`
- `agent_billing_ledger_v3`
- `customer_billing_accounts_v3`
- `stripe_webhook_events_v3`

The public FlutterFlow app may read its own wallet balance only. Query
`customer_wallets_v3` with `owner_uid == currentUserUid`, limit the result to one,
and display `available_credit_nanos / 1,000,000,000` as USD. Do not use a
client-side balance as authorization; the gateway checks the wallet again in a
server-side Firestore transaction.

Wallet document IDs are opaque SHA-256-derived values. Do not calculate or
store them in FlutterFlow. The `owner_uid` query is the intended read path.

## Firestore documents

All money values use integer USD nanos: `1 USD = 1,000,000,000 nanos`. Never
store currency amounts as Firestore doubles.

### `customer_wallets_v3/{opaque_wallet_id}`

Provision this document only after a verified payment in production. For a
development-only smoke test, use the helper below, which creates the wallet and
an immutable test-credit transaction together.

| Field | Firestore type | Meaning |
| --- | --- | --- |
| `schema_version` | integer | Starts at `1`. |
| `billing_subject_id` | string | Currently the Firebase UID; later may be an organization account ID. |
| `owner_uid` | string | Firebase UID permitted to read the balance. |
| `currency` | string | Always `USD`. |
| `status` | string | `active`, `suspended`, or `closed`. |
| `available_credit_nanos` | integer | Spendable prepaid credit. |
| `reserved_credit_nanos` | integer | Credit held by active agent turns. |
| `settled_usage_nanos` | integer | Lifetime token usage debited from this wallet. |
| `lifetime_credited_nanos` | integer | Total credited value; set by payment/provisioning code. |
| `created_at`, `updated_at` | timestamp | Backend timestamps. |
| `last_reservation_at`, `last_settlement_at` | timestamp | Optional operational timestamps. |

### `billing_reservations_v3/{turn_id}`

Created by the gateway before invoking an agent. It holds the configured
maximum per-turn credit, currently `$0.50` (`500000000` nanos), for one hour.
The worker changes it to `settled`, `settled_shortfall`, `unpriced_released`, or
`expired_released`.

Important fields: `turn_id`, `request_id`, `billing_subject_id`, `owner_uid`,
`agent_id`, `currency`, `reserved_amount_nanos`, `status`, `created_at`,
`expires_at`, `settled_at`, `released_at`, `settled_amount_nanos`,
`released_amount_nanos`, `estimated_cost_nanos`, and `shortfall_nanos`.

### `wallet_transactions_v3/{transaction_id}`

This is immutable financial history. A completed turn creates
`usage_{turn_id}` with `transaction_type = agent_usage_debit`. Expired holds
create `reservation_expired_{turn_id}` with
`transaction_type = reservation_expiry_release`. Required fields include
`billing_subject_id`, `owner_uid`, `currency`, `turn_id`, `reservation_id`,
`ledger_document_id`, `amount_nanos`, `released_amount_nanos`,
`estimated_cost_nanos`, `shortfall_nanos`, `status`, and `created_at`.

### `customer_billing_periods_v3/{opaque_period_id}`

Created on the first settled or unpriced turn of a calendar month. Its core
fields are `billing_subject_id`, `owner_uid`, `currency`, `period_key`
(`YYYY-MM`), `period_start`, `period_end`, `status`,
`usage_estimated_nanos`, `collected_usage_nanos`, `uncollected_usage_nanos`,
`usage_turn_count`, `unpriced_turn_count`, `monthly_service_fee_nanos`,
`monthly_service_fee_status`, `created_at`, and `updated_at`.

`monthly_service_fee_nanos` starts at `5000000000` ($5.00) and
`monthly_service_fee_status` starts as `pending_collection`. This makes the
service fee explicit and separate from provider-token usage; it is not a wallet
debit yet.

### `agent_billing_ledger_v3/{turn_id}`

This existing immutable source of truth gains `billing_subject_id`,
`billing_reservation_id`, `billing_reservation_nanos`, and `pricing_version`.
It remains the only source used to determine the actual per-turn debit.

### `customer_billing_accounts_v3/{opaque_billing_account_id}`

This is a private Billing API record, created by the backend before the first
Stripe Customer is created. Its document ID is an opaque SHA-256-derived value
from `billing_subject_id`; the server never accepts the document ID, Stripe
customer ID, or owner UID from FlutterFlow.

| Field | Firestore type | Meaning |
| --- | --- | --- |
| `schema_version` | integer | Starts at `1`. |
| `billing_account_id` | string | Must equal the opaque document ID. Used as the Stripe Customer creation idempotency key. |
| `billing_subject_id` | string | Current Firebase UID; can later be an organization billing account. |
| `owner_uid` | string | Current Firebase UID. Private—never readable by the client through this collection. |
| `currency` | string | Always `USD`. |
| `catalog_environment` | string | `test` or `production`; prevents test and live payment state being mixed. |
| `stripe_customer_id` | string or null | Populated only after the server creates/retrieves the Stripe Customer. |
| `stripe_customer_status` | string | `pending`, `ready`, or `failed`. |
| `stripe_subscription_id` | string or null | The separate $5/month Stripe Subscription, if started. |
| `stripe_subscription_status` | string | Starts as `not_started`; later reflects verified Stripe subscription state. |
| `stripe_subscription_current_period_start`, `stripe_subscription_current_period_end` | timestamp or null | Verified Stripe subscription period boundaries. |
| `active_checkout_request_id`, `active_checkout_session_id`, `active_checkout_url` | string or null | One short-lived, server-created Checkout Session lock per billing account. Never treat the URL as a payment receipt. |
| `active_checkout_mode`, `active_checkout_topup_package_id`, `active_checkout_created_at`, `active_checkout_expires_at` | string/timestamp or null | Server-only Checkout correlation and expiry state. |
| `created_at`, `updated_at` | timestamp | Backend timestamps. |

This record is mutable backend state, not a financial ledger. Stripe event
receipts and wallet transactions provide the immutable audit history.

### `stripe_webhook_events_v3/{opaque_stripe_event_id}`

This is the immutable, backend-only webhook receipt and event-level
idempotency record. The document ID is a SHA-256-derived value from Stripe's
`evt_...` event ID. The Billing API creates it in the same Firestore
transaction as the resulting wallet or subscription accounting records. If it
already exists, the duplicate webhook is acknowledged without applying a
second credit or fee record.

| Field | Firestore type | Meaning |
| --- | --- | --- |
| `schema_version` | integer | Starts at `1`. |
| `stripe_event_id`, `stripe_event_type` | string | Stripe event identity and event type. |
| `stripe_event_created_at`, `processed_at` | timestamp | Stripe creation time and backend processing time. |
| `stripe_livemode` | boolean | Must match the catalog environment (`false` for test, `true` for production). |
| `catalog_environment` | string | `test` or `production`. |
| `payload_sha256` | string | SHA-256 of the verified raw event body; avoids storing the full payload. |
| `outcome` | string | `topup_credited`, `service_fee_collected`, `subscription_state_updated`, or `ignored`. |
| `billing_account_id`, `billing_subject_id`, `owner_uid` | string or null | Server-derived ownership references. |
| `stripe_customer_id`, `stripe_checkout_session_id`, `stripe_payment_intent_id`, `stripe_invoice_id`, `stripe_subscription_id` | string or null | Minimal Stripe correlation IDs. |
| `wallet_transaction_id` | string or null | Immutable financial record created for a funded top-up or paid service fee. |

Never store the `Stripe-Signature` header, webhook signing secret, payment
method/card data, or complete raw webhook body in Firestore.

## Billing API Cloud Run infrastructure

The Billing API is a separate public Cloud Run service named
`ceoagent-billing-api-v3`. It is public only because Stripe needs to deliver an
unauthenticated HTTP webhook. This does **not** authorize wallet funding:

- the future FlutterFlow-facing Checkout endpoints verify a Firebase ID token;
- the webhook endpoint verifies the raw Stripe signature with its
  distinct `whsec_...` secret;
- the Billing API service account has Firestore data access, but no Vertex AI,
  Pub/Sub, or broad Secret Manager role;
- Secret Manager access is granted only to the exact named Stripe secrets.

Terraform injects the existing `stripe-secret-key` as `STRIPE_SECRET_KEY` from
a **pinned numeric secret version**. It does not create the secret or put its
value in Terraform state. A newly created Secret Manager secret normally has
version `1`; update `billing_api_stripe_secret_key_secret_version` whenever a
key is rotated. Do not use `latest` for an environment-variable secret.

Configure the webhook secret in Terraform and Secret Manager:

```hcl
billing_api_stripe_webhook_signing_secret_id      = "stripe-webhook-signing-secret-v3"
billing_api_stripe_webhook_signing_secret_version = "1"
```

After the webhook endpoint is created in Stripe Dashboard, store its `whsec_...` key in Secret Manager (`stripe-webhook-signing-secret-v3`) and grant `roles/secretmanager.secretAccessor` to `ceoagent-billing-api-sa-v3`. The Billing API service mounts this secret as `STRIPE_WEBHOOK_SIGNING_SECRET` to verify event signatures. If this secret is missing or unmounted, the webhook returns `503 Service Unavailable (stripe_webhook_not_configured)`.


The initial test-mode scaling defaults are one vCPU, 512 MiB memory,
concurrency 32, `max_instances = 20`, and `min_instances = 0`. This supports
up to 640 concurrent requests without idle test cost and fits the current
20-vCPU regional allocation quota. Before production, run a staged
Checkout/webhook load test and choose whether to request a quota increase or
raise `billing_api_max_instances`; also set `billing_api_min_instances = 1`
for a warm instance and `billing_api_deletion_protection = true`.

## FlutterFlow/Firebase rules

Merge the following matches into your existing Firestore rules; do not replace
the rest of the application's rules with this fragment. Backend service
accounts bypass Firestore Security Rules, so application code and IAM remain
the controls for all writes.

```text
match /customer_wallets_v3/{walletId} {
  allow read: if request.auth != null
              && resource.data.owner_uid == request.auth.uid;
  allow create, update, delete: if false;
}

match /wallet_transactions_v3/{transactionId} {
  allow read: if request.auth != null
              && resource.data.owner_uid == request.auth.uid;
  allow create, update, delete: if false;
}

match /customer_billing_periods_v3/{periodId} {
  allow read: if request.auth != null
              && resource.data.owner_uid == request.auth.uid;
  allow create, update, delete: if false;
}

match /agent_threads_v3/{threadId} {
  allow read, write: if request.auth != null
                     && resource.data.owner_uid == request.auth.uid;
  match /messages_v3/{messageId} {
    allow read, write: if request.auth != null
                       && resource.data.owner_uid == request.auth.uid;
  }
}


match /billing_reservations_v3/{reservationId} {
  allow read, create, update, delete: if false;
}

match /agent_billing_ledger_v3/{turnId} {
  allow read: if request.auth != null
              && resource.data.owner_uid == request.auth.uid;
  allow create, update, delete: if false;
}

match /customer_billing_accounts_v3/{accountId} {
  allow read, create, update, delete: if false;
}

match /stripe_webhook_events_v3/{stripeEventId} {
  allow read, create, update, delete: if false;
}

match /processed_events_v3/{eventId} {
  allow read, create, update, delete: if false;
}
```

## Stripe Webhook Event Ingestion & Resilience

The Billing API exposes a cryptographically-verified Stripe webhook endpoint at:
`POST /v1/billing/stripe/webhook`

### Event Ingestion Lifecycle:
1. **Signature Verification**: Verified against the Secret Manager secret `stripe-webhook-signing-secret-v3`.
2. **Idempotency & Audit**: Document receipts are recorded in `stripe_webhook_events_v3/{opaque_event_id}`.
3. **Graceful Acknowledgment**:
   - `checkout.session.completed`: Credits `customer_wallets_v3` atomically and writes `wallet_transactions_v3`.
   - `invoice.paid`: Fulfills recurring monthly service fee payments. Initial combined checkout invoices (already credited by checkout session) are acknowledged with `200 OK` (outcome `ignored`).
   - `customer.subscription.*`: Updates subscription state. Unmatched or test events without metadata return `200 OK` (outcome `ignored`) to prevent Stripe delivery retries.

## Development-only wallet provisioning

Authenticate locally as an operator for the development project, then run:

```powershell
python -m pip install -r services/agent_persistence_worker_v3/requirements.txt
python scripts/provision_test_wallet.py `
  --project-id ceo-dev123 `
  --uid FIREBASE_UID `
  --credit-usd 10.00 `
  --non-production
```

This is intentionally not a production credit mechanism. The verified Stripe
webhook now provides the production-shaped credit path: it uses the Stripe
event ID plus a source-specific transaction ID and creates the wallet credit
and `wallet_transactions` record atomically.

## Enabling the feature safely

1. Deploy the code with `billing_enforcement_enabled = false` (the default).
2. Apply the Firestore rule changes and provision a test wallet in the
   development project.
3. Set `billing_enforcement_enabled = true` and
   `billing_reconciliation_enabled = true` in the development Terraform
   variables, then deploy the gateway and worker.
4. Run buffered and streaming smoke tests with a funded UID. Confirm one
   `billing_reservations/{turn_id}`, one `agent_billing_ledger/{turn_id}`, one
   `wallet_transactions/usage_{turn_id}`, and one monthly period record.
5. Confirm that a wallet with less than the reservation amount receives a 402
   before the gateway calls an agent.
6. Let a reserved request expire in development and confirm the scheduled
   reconciliation job releases it. Review its Cloud Scheduler execution and
   worker logs.

Do not enable this for customers until each deployed agent reliably returns
usage metadata, the price catalog is reviewed, and Stripe/payment, refund,
tax, and suspension policies are implemented.
