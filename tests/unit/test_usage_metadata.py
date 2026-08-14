from services.agent_gateway_v3.app.services.usage_metadata import (
    extract_usage_metadata,
    normalize_usage_metadata,
)


def test_normalize_usage_metadata_prices_gemini_flash_text_tokens() -> None:
    usage = normalize_usage_metadata(
        {
            "prompt_token_count": 1000,
            "candidates_token_count": 200,
            "thoughts_token_count": 50,
            "total_token_count": 1250,
        }
    )

    assert usage["pricing_model"] == "gemini-2.5-flash"
    assert usage["token_counts"] == {
        "prompt_token_count": 1000,
        "candidates_token_count": 200,
        "thoughts_token_count": 50,
        "total_token_count": 1250,
    }
    assert usage["billable_tokens"] == {
        "input_text_image_video": 1000,
        "input_audio": 0,
        "output_including_thinking": 250,
    }
    assert usage["estimated_cost_usd"] == 0.000925
    assert usage["estimated_cost_breakdown_usd"] == {
        "input_text_image_video": 0.0003,
        "input_audio": 0.0,
        "output_including_thinking": 0.000625,
    }


def test_normalize_usage_metadata_splits_audio_prompt_tokens() -> None:
    usage = normalize_usage_metadata(
        {
            "promptTokenCount": 100,
            "candidatesTokenCount": 10,
            "promptTokensDetails": [
                {"modality": "TEXT", "tokenCount": 40},
                {"modality": "AUDIO", "tokenCount": 60},
            ],
        }
    )

    assert usage["token_counts"]["prompt_token_count"] == 100
    assert usage["billable_tokens"] == {
        "input_text_image_video": 40,
        "input_audio": 60,
        "output_including_thinking": 10,
    }
    assert usage["estimated_cost_usd"] == 0.000097


def test_extract_usage_metadata_finds_nested_agent_runtime_shape() -> None:
    event = {
        "payload": {
            "event": {
                "usageMetadata": {
                    "promptTokenCount": 5,
                    "candidatesTokenCount": 3,
                }
            }
        }
    }

    assert extract_usage_metadata(event) == {
        "promptTokenCount": 5,
        "candidatesTokenCount": 3,
    }


def test_normalize_usage_metadata_does_not_price_total_only_usage() -> None:
    usage = normalize_usage_metadata({"total_token_count": 21})

    assert usage["total_token_count"] == 21
    assert usage["token_counts"] == {"total_token_count": 21}
    assert "estimated_cost_usd" not in usage
    assert "billable_tokens" not in usage
