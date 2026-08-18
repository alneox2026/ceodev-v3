# FlutterFlow API Configuration Guide for CEOsystem V3

This document lists all **V3 Gateway and Billing API endpoints** for FlutterFlow, along with request formats, headers, and variable schemas.

---

## Base URLs

* **Agent Gateway V3 Base URL**:
  ```text
  https://ceoagent-gateway-v3-281577273798.us-central1.run.app
  ```
* **Billing API V3 Base URL**:
  ```text
  https://ceoagent-billing-api-v3-281577273798.us-central1.run.app
  ```

---

## 1. Authentication Header (Required for All Client Endpoints)

In FlutterFlow API Group / Call Settings, add the Authorization header:
```text
Authorization: Bearer [firebase_auth_token]
```

---

## 2. Agent Gateway Endpoints (4 Agents)

### Agent 1: Maxima V3 (Agent Platform — Non-Streaming / Buffered)
1. **Chat**:
   `POST https://ceoagent-gateway-v3-281577273798.us-central1.run.app/v1/agents/maxima_v3/chat`
2. **Archive Thread**:
   `POST https://ceoagent-gateway-v3-281577273798.us-central1.run.app/v1/agents/maxima_v3/threads/[threadId]/archive`
3. **Delete Thread**:
   `POST https://ceoagent-gateway-v3-281577273798.us-central1.run.app/v1/agents/maxima_v3/threads/[threadId]/delete`

---

### Agent 2: Maxima Streaming V3 (Agent Platform — Streaming Responses)
1. **Chat Stream (SSE)**:
   `POST https://ceoagent-gateway-v3-281577273798.us-central1.run.app/v1/agents/maxima_agentruntime_streaming_v3/chat/stream`
2. **Archive Thread**:
   `POST https://ceoagent-gateway-v3-281577273798.us-central1.run.app/v1/agents/maxima_agentruntime_streaming_v3/threads/[threadId]/archive`
3. **Delete Thread**:
   `POST https://ceoagent-gateway-v3-281577273798.us-central1.run.app/v1/agents/maxima_agentruntime_streaming_v3/threads/[threadId]/delete`

---

### Agent 3: Maxima Cloud Run V3 (Cloud Run — Non-Streaming / Buffered)
1. **Chat**:
   `POST https://ceoagent-gateway-v3-281577273798.us-central1.run.app/v1/agents/maxima_cloudrun_v3/chat`
2. **Archive Thread**:
   `POST https://ceoagent-gateway-v3-281577273798.us-central1.run.app/v1/agents/maxima_cloudrun_v3/threads/[threadId]/archive`
3. **Delete Thread**:
   `POST https://ceoagent-gateway-v3-281577273798.us-central1.run.app/v1/agents/maxima_cloudrun_v3/threads/[threadId]/delete`

---

### Agent 4: Maxima Cloud Run Streaming V3 (Cloud Run — Streaming Responses)
1. **Chat Stream (SSE)**:
   `POST https://ceoagent-gateway-v3-281577273798.us-central1.run.app/v1/agents/maxima_cloudrun_stream_v3/chat/stream`
2. **Archive Thread**:
   `POST https://ceoagent-gateway-v3-281577273798.us-central1.run.app/v1/agents/maxima_cloudrun_stream_v3/threads/[threadId]/archive`
3. **Delete Thread**:
   `POST https://ceoagent-gateway-v3-281577273798.us-central1.run.app/v1/agents/maxima_cloudrun_stream_v3/threads/[threadId]/delete`

---

## 3. Chat Request & Response Format

### Buffered Chat Request Body (`POST .../chat`)
```json
{
  "message": "[user_message]",
  "thread_id": "[thread_id]",
  "session_id": "[session_id]"
}
```
*(Note: `thread_id` and `session_id` can be omitted on the first turn; persist the returned values for follow-up turns in the same conversation)*

### Buffered Chat Response Body:
```json
{
  "ok": true,
  "thread_id": "thread-...",
  "turn_id": "turn-...",
  "session_id": "session-...",
  "content": "Agent response text...",
  "usage": {
    "prompt_tokens": 150,
    "response_tokens": 80,
    "total_tokens": 230
  }
}
```

---

## 4. Billing API Endpoints (Top-ups & Subscriptions)

### 1. Create Token Top-up Checkout Session
* **URL**: `POST https://ceoagent-billing-api-v3-281577273798.us-central1.run.app/v1/billing/topups/checkout-session`
* **Body**:
  ```json
  {
    "topup_package_id": "[package_id]"
  }
  ```
  *(Allowed `package_id` values: `"credit_5_usd"`, `"credit_10_usd"`, `"credit_25_usd"`)*
* **Response**:
  ```json
  {
    "ok": true,
    "checkout_url": "https://checkout.stripe.com/c/pay/cs_test_...",
    "session_id": "cs_test_..."
  }
  ```

> [!NOTE]
> **Seamless Package Switching**: Users can switch freely between `$5`, `$10`, and `$25` at any time. Clicking the same package re-opens the active checkout session, while choosing a different package generates a new checkout session for the newly chosen amount with zero lockouts.

---


### 2. Create $5/mo Monthly Platform Fee Checkout Session
* **URL**: `POST https://ceoagent-billing-api-v3-281577273798.us-central1.run.app/v1/billing/service-fee/checkout-session`
* **Body**: `{}`
* **Response**:
  ```json
  {
    "ok": true,
    "checkout_url": "https://checkout.stripe.com/c/pay/cs_test_...",
    "session_id": "cs_test_..."
  }
  ```

---

### 3. Create Stripe Customer Billing Portal Session
* **URL**: `POST https://ceoagent-billing-api-v3-281577273798.us-central1.run.app/v1/billing/customer-portal`
* **Body**:
  ```json
  {
    "return_url": "https://ceoappdev.flutterflow.app"
  }
  ```
* **Response**:
  ```json
  {
    "ok": true,
    "portal_url": "https://billing.stripe.com/p/session/test_..."
  }
  ```
