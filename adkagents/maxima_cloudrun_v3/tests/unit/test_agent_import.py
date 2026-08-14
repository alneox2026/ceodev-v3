"""Smoke tests for the Maxima Cloud Run canary agent."""

import importlib

from app.agent import MAXIMA_MODEL, app, root_agent


def test_cloudrun_canary_agent_imports() -> None:
    assert root_agent.name == "maxima_cloudrun"
    assert app.name == "app"
    assert MAXIMA_MODEL == "gemini-2.5-flash"


def test_cloudrun_fastapi_entrypoint_imports_with_in_memory_session(
    monkeypatch,
) -> None:
    monkeypatch.setenv("USE_IN_MEMORY_SESSION", "true")
    module = importlib.import_module("app.fast_api_app")

    assert module.app.title == "maxima-cloudrun-canary"
