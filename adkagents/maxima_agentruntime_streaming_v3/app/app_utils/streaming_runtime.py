from __future__ import annotations

from collections.abc import AsyncIterable, Mapping
from typing import Any

from vertexai.agent_engines.templates.adk import AdkApp


DEFAULT_STREAMING_MODE = "sse"


def merge_stream_run_config(
    run_config: Mapping[str, Any] | None,
) -> dict[str, Any]:
    merged_run_config = dict(run_config or {})
    merged_run_config.setdefault("streaming_mode", DEFAULT_STREAMING_MODE)
    return merged_run_config


def merge_buffered_run_config(
    run_config: Mapping[str, Any] | None,
) -> dict[str, Any]:
    merged_run_config = dict(run_config or {})
    merged_run_config["streaming_mode"] = None
    return merged_run_config


def _event_to_json_dict(event: Any) -> dict[str, Any]:
    if isinstance(event, dict):
        return event
    if hasattr(event, "model_dump"):
        dumped = event.model_dump(mode="json", exclude_none=True)
        if isinstance(dumped, dict):
            return dumped
        return {"event": dumped}
    if hasattr(event, "dict"):
        dumped = event.dict(exclude_none=True)
        if isinstance(dumped, dict):
            return dumped
        return {"event": dumped}
    return {"event": str(event)}


class StreamingDefaultAdkApp(AdkApp):
    async def async_buffered_query(
        self,
        *,
        message: str | dict[str, Any],
        user_id: str,
        session_id: str | None = None,
        session_events: list[dict[str, Any]] | None = None,
        run_config: dict[str, Any] | None = None,
        **kwargs,
    ) -> list[dict[str, Any]]:
        effective_run_config = merge_buffered_run_config(run_config)
        events: list[dict[str, Any]] = []
        async for event in super().async_stream_query(
            message=message,
            user_id=user_id,
            session_id=session_id,
            session_events=session_events,
            run_config=effective_run_config,
            **kwargs,
        ):
            events.append(_event_to_json_dict(event))
        return events

    async def async_stream_query(
        self,
        *,
        message: str | dict[str, Any],
        user_id: str,
        session_id: str | None = None,
        session_events: list[dict[str, Any]] | None = None,
        run_config: dict[str, Any] | None = None,
        **kwargs,
    ) -> AsyncIterable[dict[str, Any]]:
        effective_run_config = merge_stream_run_config(run_config)
        async for event in super().async_stream_query(
            message=message,
            user_id=user_id,
            session_id=session_id,
            session_events=session_events,
            run_config=effective_run_config,
            **kwargs,
        ):
            yield event
