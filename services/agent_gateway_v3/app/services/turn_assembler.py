"""Helpers to assemble streamed tokens into a final turn result."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.agent_gateway_v3.app.services.usage_metadata import (
    extract_usage_metadata,
    normalize_usage_metadata,
)


@dataclass
class TurnAssembler:
    text_fragments: list[str] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    raw_events: list[dict[str, Any]] = field(default_factory=list)

    def add_text(self, value: str) -> str:
        if not value:
            return ""

        current_text = self.reply_text()
        if value.startswith(current_text):
            delta = value[len(current_text) :]
            if delta:
                self.text_fragments.append(delta)
            return delta

        overlap = self._suffix_prefix_overlap(current_text, value)
        delta = value[overlap:]
        if delta:
            self.text_fragments.append(delta)
        return delta

    def add_event(self, event: dict[str, Any]) -> None:
        self.raw_events.append(event)
        usage = extract_usage_metadata(event)
        if usage is not None:
            self.usage = normalize_usage_metadata(usage)

    def set_usage(self, usage: dict[str, Any]) -> None:
        self.usage = normalize_usage_metadata(usage)

    def reply_text(self) -> str:
        return "".join(self.text_fragments).strip()

    def _suffix_prefix_overlap(self, current_text: str, next_value: str) -> int:
        max_overlap = min(len(current_text), len(next_value))
        for overlap in range(max_overlap, 0, -1):
            if current_text[-overlap:] == next_value[:overlap]:
                return overlap
        return 0
