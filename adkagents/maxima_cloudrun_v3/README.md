# Maxima Cloud Run Canary

`maxima_cloudrun` is a separate ADK canary project for validating Maxima on Cloud Run without changing the production Agent Runtime deployment.

The canary keeps Maxima's current instructions and Google Search grounding behavior, but defaults to `gemini-2.5-flash`. It is intended to be deployed as a private Cloud Run service named `maxima-cloudrun-canary` and called only through `ceoagent-gateway`.

Use Vertex AI in `us-central1` for this canary unless a newer model has been verified in the target region first.

When deployed through `agents-cli`, the ADK API server exposes the app as `app` because the configured `agent_directory` is `app`. The ADK `App(name=...)` and gateway registry `app_name` must therefore both be `app` unless the deployment package layout is changed.

The canary is configured for Agent Platform Sessions (`session_type = "agent_platform_sessions"`) so ADK session state survives Cloud Run instance restarts, scale-out, and revision changes. Deploy with `AGENT_ENGINE_SESSION_NAME=maxima-cloudrun-sessions` so the ADK API server reuses a stable managed session backend.

Because sessions are now persistent, the gateway registry uses `runtime_session_cleanup: cloud_run_adk`; delete events let the worker call the canary ADK session delete endpoint through Cloud Run auth instead of leaking stale runtime sessions.
