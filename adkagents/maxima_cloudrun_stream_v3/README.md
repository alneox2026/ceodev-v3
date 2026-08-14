# Maxima Cloud Run Stream Canary

`maxima_cloudrun_stream` is the Cloud Run ADK canary for validating text SSE streaming through `ceoagent-gateway`.

The public FlutterFlow-facing path should be:

```text
POST /v1/agents/maxima_cloudrun_stream/chat/stream
```

The gateway streams tokens to the client, assembles the completed assistant response, then publishes one completed-turn event for asynchronous Firestore persistence. It does not publish per-token events.

This agent uses ADK Python 2.x and Vertex AI by default. The Cloud Run service should remain private and invokable only by the gateway service account.

Deploy with a stable Agent Platform Sessions backend name:

```text
AGENT_ENGINE_SESSION_NAME=maxima-cloudrun-stream-sessions
```

For production-like deployments, prefer setting `AGENT_ENGINE_RESOURCE_NAME` or `AGENT_ENGINE_SESSION_URI` after pre-creating the sessions backend. That avoids a Vertex AI control-plane lookup during normal Cloud Run cold starts.

The ADK app name is `app`; the gateway registry entry must use `app_name: app`.
