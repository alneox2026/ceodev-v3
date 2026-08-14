# Maxima Migration Plan

## Current state

- `main.py` is the working legacy middleware.
- FlutterFlow currently uses the legacy path.

## Target state

- `services/agent_gateway_v3` becomes the public middleware.
- `services/agent_persistence_worker_v3` consumes Pub/Sub events and writes Firestore.

## Cutover rule

Do not cut Maxima over until:

1. buffered gateway path is implemented
2. Pub/Sub handoff is implemented
3. worker persistence is implemented
4. archive/delete lifecycle is implemented
5. buffered smoke tests pass
6. rollback path is documented and preserved

Status in this repo:

- items 1 through 4 are now implemented in code
- local unit/integration tests are passing
- live deployment and smoke testing are complete
- FlutterFlow cutover is buffered-first for launch
- streaming remains deployed server-side but intentionally deferred in FlutterFlow

## FlutterFlow endpoint switch

Update the Maxima API configuration in FlutterFlow to point to the new gateway base URL:

```text
https://ceoagent-gateway-281577273798.us-central1.run.app
```

Use these endpoints:

- buffered: `POST /v1/agents/maxima/chat`
- archive: `POST /v1/agents/maxima/threads/{thread_id}/archive`
- delete: `POST /v1/agents/maxima/threads/{thread_id}/delete`

Keep the streaming endpoint deployed but do not wire it into FlutterFlow for the launch:

- streaming: `POST /v1/agents/maxima/chat/stream`

Send the Firebase ID token in the `Authorization` header:

```text
Authorization: Bearer <firebase_id_token>
```

Buffered request body:

```json
{
  "message": "Hello",
  "thread_id": "thread-optional",
  "session_id": "session-optional"
}
```

Persist and reuse `thread_id` and `session_id` from the first successful response for follow-up turns.

For rollback, preserve the legacy `main.py` endpoint configuration and use [maxima-rollback-runbook.md](/c:/Users/Admin/Desktop/ANTIGRAVITY/CEOsystem-dev3/docs/maxima-rollback-runbook.md).
