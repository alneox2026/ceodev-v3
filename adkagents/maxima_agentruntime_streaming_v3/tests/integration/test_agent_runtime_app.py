# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

import pytest
from google.adk.events.event import Event
from vertexai.agent_engines.templates.adk import AdkApp

from app.agent_runtime_app import AgentEngineApp


@pytest.fixture
def agent_app(monkeypatch: pytest.MonkeyPatch) -> AgentEngineApp:
    """Fixture to create and set up AgentEngineApp instance"""
    # Set integration test flag to mock external services
    monkeypatch.setenv("INTEGRATION_TEST", "TRUE")

    from app.agent_runtime_app import agent_runtime

    agent_runtime.set_up()
    return agent_runtime


@pytest.mark.asyncio
async def test_agent_stream_query(agent_app: AgentEngineApp) -> None:
    """
    Integration test for the agent stream query functionality.
    Tests that the agent returns valid streaming responses.
    """
    # Create message and events for the async_stream_query
    message = "Hi!"
    events = []
    async for event in agent_app.async_stream_query(message=message, user_id="test"):
        events.append(event)
    assert len(events) > 0, "Expected at least one chunk in response"

    # Check for valid content in the response
    has_text_content = False
    for event in events:
        validated_event = Event.model_validate(event)
        content = validated_event.content
        if (
            content is not None
            and content.parts
            and any(part.text for part in content.parts)
        ):
            has_text_content = True
            break

    assert has_text_content, "Expected at least one event with text content"


def test_agent_feedback(agent_app: AgentEngineApp) -> None:
    """
    Integration test for the agent feedback functionality.
    Tests that feedback can be registered successfully.
    """
    feedback_data = {
        "score": 5,
        "text": "Great response!",
        "user_id": "test-user-456",
        "session_id": "test-session-456",
    }

    # Should not raise any exceptions
    agent_app.register_feedback(feedback_data)

    # Test invalid feedback
    with pytest.raises(ValueError):
        invalid_feedback = {
            "score": "invalid",  # Score must be numeric
            "text": "Bad feedback",
            "user_id": "test-user-789",
            "session_id": "test-session-789",
        }
        agent_app.register_feedback(invalid_feedback)

    logging.info("All assertions passed for agent feedback test")


def test_async_stream_query_defaults_to_sse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_run_config: dict[str, Any] = {}

    async def fake_async_stream_query(
        self,
        *,
        message: str | dict[str, Any],
        user_id: str,
        session_id: str | None = None,
        session_events: list[dict[str, Any]] | None = None,
        run_config: dict[str, Any] | None = None,
        **kwargs,
    ) -> AsyncIterator[dict[str, Any]]:
        del self, message, user_id, session_id, session_events, kwargs
        captured_run_config.update(run_config or {})
        yield {"content": {"role": "model", "parts": [{"text": "chunk"}]}}

    monkeypatch.setattr(AdkApp, "async_stream_query", fake_async_stream_query)

    from app.agent_runtime_app import agent_runtime

    async def _run() -> None:
        events = []
        async for event in agent_runtime.async_stream_query(
            message="hello",
            user_id="test-user",
        ):
            events.append(event)
        assert len(events) == 1

    asyncio.run(_run())

    assert captured_run_config["streaming_mode"] == "sse"


def test_async_stream_query_preserves_explicit_run_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_run_config: dict[str, Any] = {}

    async def fake_async_stream_query(
        self,
        *,
        message: str | dict[str, Any],
        user_id: str,
        session_id: str | None = None,
        session_events: list[dict[str, Any]] | None = None,
        run_config: dict[str, Any] | None = None,
        **kwargs,
    ) -> AsyncIterator[dict[str, Any]]:
        del self, message, user_id, session_id, session_events, kwargs
        captured_run_config.update(run_config or {})
        yield {"content": {"role": "model", "parts": [{"text": "chunk"}]}}

    monkeypatch.setattr(AdkApp, "async_stream_query", fake_async_stream_query)

    from app.agent_runtime_app import agent_runtime

    explicit_run_config = {
        "streaming_mode": None,
        "max_llm_calls": 12,
        "custom_metadata": {"origin": "test"},
    }

    async def _run() -> None:
        events = []
        async for event in agent_runtime.async_stream_query(
            message="hello",
            user_id="test-user",
            run_config=explicit_run_config,
        ):
            events.append(event)
        assert len(events) == 1

    asyncio.run(_run())

    assert captured_run_config == explicit_run_config


def test_register_operations_exposes_buffered_query() -> None:
    from app.agent_runtime_app import agent_runtime

    operations = agent_runtime.register_operations()

    assert "async_buffered_query" in operations["async"]
    assert "async_stream_query" in operations["async_stream"]


def test_async_buffered_query_forces_non_streaming_run_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_run_config: dict[str, Any] = {}

    async def fake_async_stream_query(
        self,
        *,
        message: str | dict[str, Any],
        user_id: str,
        session_id: str | None = None,
        session_events: list[dict[str, Any]] | None = None,
        run_config: dict[str, Any] | None = None,
        **kwargs,
    ) -> AsyncIterator[dict[str, Any]]:
        del self, message, user_id, session_id, session_events, kwargs
        captured_run_config.update(run_config or {})
        yield {"content": {"role": "model", "parts": [{"text": "final"}]}}

    monkeypatch.setattr(AdkApp, "async_stream_query", fake_async_stream_query)

    from app.agent_runtime_app import agent_runtime

    events = asyncio.run(
        agent_runtime.async_buffered_query(
            message="hello",
            user_id="test-user",
            run_config={"streaming_mode": "sse", "max_llm_calls": 12},
        )
    )

    assert events == [{"content": {"role": "model", "parts": [{"text": "final"}]}}]
    assert captured_run_config == {
        "streaming_mode": None,
        "max_llm_calls": 12,
    }
