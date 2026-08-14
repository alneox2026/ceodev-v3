"""Usage metadata normalization and Gemini 2.5 Flash cost estimates."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


MODEL_NAME = "gemini-2.5-flash"
PRICING_VERSION = "gemini-2.5-flash-usd-on-demand-2026-08-11"
USD_PER_1M_INPUT_TEXT_IMAGE_VIDEO = 0.30
USD_PER_1M_INPUT_AUDIO = 1.00
USD_PER_1M_OUTPUT = 2.50

_USAGE_KEYS = ("usage_metadata", "usageMetadata")


def extract_usage_metadata(event: dict[str, Any]) -> dict[str, Any] | None:
    """Find ADK/Gemini usage metadata in common event envelope shapes."""

    def walk(value: Any, depth: int = 0) -> dict[str, Any] | None:
        if depth > 8:
            return None
        if isinstance(value, dict):
            for key in _USAGE_KEYS:
                usage = value.get(key)
                if isinstance(usage, dict):
                    return usage
            for nested_value in value.values():
                usage = walk(nested_value, depth + 1)
                if usage is not None:
                    return usage
        elif isinstance(value, list):
            for item in value:
                usage = walk(item, depth + 1)
                if usage is not None:
                    return usage
        return None

    return walk(event)


def normalize_usage_metadata(usage_metadata: dict[str, Any]) -> dict[str, Any]:
    """Preserve raw usage fields while adding normalized counts and cost fields."""

    usage = deepcopy(usage_metadata)
    token_counts = _token_counts(usage_metadata)
    if token_counts:
        usage["token_counts"] = token_counts

    prompt_token_count = token_counts.get("prompt_token_count")
    candidates_token_count = token_counts.get("candidates_token_count")
    thoughts_token_count = token_counts.get("thoughts_token_count", 0)
    total_token_count = token_counts.get("total_token_count")

    input_text_image_video_tokens, input_audio_tokens = _input_token_split(
        usage_metadata,
        prompt_token_count,
    )
    output_tokens = _output_token_count(
        prompt_token_count=prompt_token_count,
        candidates_token_count=candidates_token_count,
        thoughts_token_count=thoughts_token_count,
        total_token_count=total_token_count,
    )

    if (
        input_text_image_video_tokens is None
        and input_audio_tokens is None
        and output_tokens is None
    ):
        return usage

    billable_tokens = {
        "input_text_image_video": input_text_image_video_tokens or 0,
        "input_audio": input_audio_tokens or 0,
        "output_including_thinking": output_tokens or 0,
    }
    usage["pricing_model"] = MODEL_NAME
    usage["pricing_version"] = PRICING_VERSION
    usage["pricing_unit"] = "usd_per_1m_tokens"
    usage["pricing"] = {
        "input_text_image_video": USD_PER_1M_INPUT_TEXT_IMAGE_VIDEO,
        "input_audio": USD_PER_1M_INPUT_AUDIO,
        "output_including_thinking": USD_PER_1M_OUTPUT,
    }
    usage["billable_tokens"] = billable_tokens
    usage["estimated_cost_usd"] = _round_usd(
        billable_tokens["input_text_image_video"]
        * USD_PER_1M_INPUT_TEXT_IMAGE_VIDEO
        / 1_000_000
        + billable_tokens["input_audio"] * USD_PER_1M_INPUT_AUDIO / 1_000_000
        + billable_tokens["output_including_thinking"]
        * USD_PER_1M_OUTPUT
        / 1_000_000
    )
    usage["estimated_cost_breakdown_usd"] = {
        "input_text_image_video": _round_usd(
            billable_tokens["input_text_image_video"]
            * USD_PER_1M_INPUT_TEXT_IMAGE_VIDEO
            / 1_000_000
        ),
        "input_audio": _round_usd(
            billable_tokens["input_audio"] * USD_PER_1M_INPUT_AUDIO / 1_000_000
        ),
        "output_including_thinking": _round_usd(
            billable_tokens["output_including_thinking"]
            * USD_PER_1M_OUTPUT
            / 1_000_000
        ),
    }
    return usage


def _token_counts(usage_metadata: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for normalized_key, key_options in {
        "prompt_token_count": ("prompt_token_count", "promptTokenCount"),
        "candidates_token_count": (
            "candidates_token_count",
            "candidatesTokenCount",
        ),
        "thoughts_token_count": ("thoughts_token_count", "thoughtsTokenCount"),
        "total_token_count": ("total_token_count", "totalTokenCount"),
        "cached_content_token_count": (
            "cached_content_token_count",
            "cachedContentTokenCount",
        ),
        "tool_use_prompt_token_count": (
            "tool_use_prompt_token_count",
            "toolUsePromptTokenCount",
        ),
    }.items():
        value = _first_int(usage_metadata, key_options)
        if value is not None:
            counts[normalized_key] = value
    return counts


def _input_token_split(
    usage_metadata: dict[str, Any],
    prompt_token_count: int | None,
) -> tuple[int | None, int | None]:
    if prompt_token_count is None:
        return None, None

    audio_tokens = 0
    non_audio_tokens = 0
    details_found = False
    for detail in _prompt_token_details(usage_metadata):
        modality = str(
            detail.get("modality")
            or detail.get("Modality")
            or detail.get("type")
            or ""
        ).upper()
        token_count = _first_int(detail, ("token_count", "tokenCount"))
        if token_count is None:
            continue
        details_found = True
        if modality == "AUDIO":
            audio_tokens += token_count
        else:
            non_audio_tokens += token_count

    if not details_found:
        return prompt_token_count, 0

    residual_tokens = max(prompt_token_count - audio_tokens - non_audio_tokens, 0)
    return non_audio_tokens + residual_tokens, audio_tokens


def _prompt_token_details(usage_metadata: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("prompt_tokens_details", "promptTokensDetails"):
        value = usage_metadata.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _output_token_count(
    *,
    prompt_token_count: int | None,
    candidates_token_count: int | None,
    thoughts_token_count: int | None,
    total_token_count: int | None,
) -> int | None:
    if candidates_token_count is not None or thoughts_token_count:
        return (candidates_token_count or 0) + (thoughts_token_count or 0)
    if total_token_count is not None and prompt_token_count is not None:
        return max(total_token_count - prompt_token_count, 0)
    return None


def _first_int(source: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = source.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return max(value, 0)
        if isinstance(value, float) and value.is_integer():
            return max(int(value), 0)
        if isinstance(value, str):
            try:
                parsed = int(value)
            except ValueError:
                continue
            return max(parsed, 0)
    return None


def _round_usd(value: float) -> float:
    return round(value, 9)
