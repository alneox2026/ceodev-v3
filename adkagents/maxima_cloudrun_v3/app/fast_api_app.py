"""Cloud Run FastAPI entrypoint for the Maxima ADK canary."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import vertexai
from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app
from google.cloud import logging as cloud_logging
from vertexai import agent_engines


LOGGER = logging.getLogger(__name__)
AGENT_DIR = str(Path(__file__).resolve().parent.parent)
DEFAULT_AGENT_ENGINE_SESSION_NAME = "maxima-cloudrun-v3-sessions"


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes"}


def _setup_cloud_logging() -> None:
    try:
        cloud_logging.Client().setup_logging()
    except Exception:
        LOGGER.exception("Cloud Logging setup failed; continuing with standard logging.")


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} must be set for the Cloud Run ADK runtime.")
    return value


def _resolve_agent_engine_session_uri() -> str | None:
    if _truthy_env("USE_IN_MEMORY_SESSION"):
        LOGGER.warning("USE_IN_MEMORY_SESSION is enabled; ADK sessions are not durable.")
        return None

    project_id = _required_env("GOOGLE_CLOUD_PROJECT")
    location = _required_env("GOOGLE_CLOUD_LOCATION")
    agent_name = os.getenv(
        "AGENT_ENGINE_SESSION_NAME",
        DEFAULT_AGENT_ENGINE_SESSION_NAME,
    )

    vertexai.init(project=project_id, location=location)
    existing_agents = list(agent_engines.list(filter=f"display_name={agent_name}"))
    agent_runtime = existing_agents[0] if existing_agents else agent_engines.create(
        display_name=agent_name,
    )
    resource_name = getattr(agent_runtime, "resource_name", None) or getattr(
        agent_runtime,
        "name",
        None,
    )
    if not resource_name:
        raise RuntimeError(f"Could not resolve Agent Engine resource for {agent_name}.")

    LOGGER.info("Using Agent Engine sessions backend: %s", resource_name)
    return f"agentengine://{resource_name}"


_setup_cloud_logging()

allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
)
logs_bucket_name = os.getenv("LOGS_BUCKET_NAME")

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    artifact_service_uri=f"gs://{logs_bucket_name}" if logs_bucket_name else None,
    allow_origins=allow_origins,
    session_service_uri=_resolve_agent_engine_session_uri(),
    use_local_storage=False,
    otel_to_cloud=True,
)
app.title = "maxima-cloudrun-v3"
app.description = "Cloud Run ADK runtime for the Maxima v3 agent."

