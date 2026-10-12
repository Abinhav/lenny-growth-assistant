
import json
import os
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest

from app.core.config import get_settings
from app.services.ai_provider import AIProviderError, generate_response


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_generate_response_uses_ollama() -> None:
    fake_payload = {
        "message": {
            "role": "assistant",
            "content": "Improve onboarding and reduce friction.",
        }
    }

    with patch(
            "urllib.request.urlopen",
            return_value=FakeResponse(fake_payload),
    ) as mock_urlopen:
        result = generate_response("How can activation improve?")

    assert result == "Improve onboarding and reduce friction."

    request = mock_urlopen.call_args.args[0]
    body = json.loads(request.data.decode("utf-8"))

    assert request.full_url.endswith("/api/chat")
    assert body["model"] == get_settings().ollama_model
    assert body["messages"][0]["content"] == (
        "How can activation improve?"
    )
    assert body["stream"] is False


def test_generate_response_rejects_empty_content() -> None:
    with patch(
            "urllib.request.urlopen",
            return_value=FakeResponse({"message": {"content": "  "}}),
    ):
        with pytest.raises(AIProviderError, match="empty response"):
            generate_response("Test prompt")


def test_generate_response_handles_connection_error() -> None:
    with patch(
            "urllib.request.urlopen",
            side_effect=URLError("Connection refused"),
    ):
        with pytest.raises(AIProviderError, match="Unable to reach Ollama"):
            generate_response("Test prompt")


def test_openai_missing_api_key_returns_clear_error() -> None:
    get_settings.cache_clear()

    try:
        with patch.dict(
                os.environ,
                {"MODEL_PROVIDER": "openai", "OPENAI_API_KEY": ""},
        ):
            with pytest.raises(
                    AIProviderError,
                    match="OPENAI_API_KEY is not configured",
            ):
                generate_response("Test prompt")
    finally:
        get_settings.cache_clear()


def test_openai_provider_uses_configured_model() -> None:
    get_settings.cache_clear()

    try:
        with patch.dict(
                os.environ,
                {
                    "MODEL_PROVIDER": "openai",
                    "OPENAI_API_KEY": "test-key",
                    "OPENAI_MODEL": "test-openai-model",
                },
        ):
            fake_client = MagicMock()
            fake_client.with_options.return_value.chat.completions.create.return_value.choices = [
                MagicMock(message=MagicMock(content="OpenAI test response"))
            ]

            with patch(
                    "app.services.ai_provider._get_openai_client",
                    return_value=fake_client,
            ):
                result = generate_response("Test prompt")

            assert result == "OpenAI test response"
            call_kwargs = (
                fake_client.with_options.return_value.chat.completions.create.call_args.kwargs
            )
            assert call_kwargs["model"] == "test-openai-model"
    finally:
        get_settings.cache_clear()


def test_anthropic_provider_uses_configured_model() -> None:
    get_settings.cache_clear()

    try:
        with patch.dict(
                os.environ,
                {
                    "MODEL_PROVIDER": "anthropic",
                    "ANTHROPIC_API_KEY": "test-key",
                    "ANTHROPIC_MODEL": "test-anthropic-model",
                },
        ):
            fake_client = MagicMock()
            fake_client.with_options.return_value.messages.create.return_value.content = [
                MagicMock(type="text", text="Anthropic test response")
            ]

            with patch(
                    "app.services.ai_provider._get_anthropic_client",
                    return_value=fake_client,
            ):
                result = generate_response("Test prompt")

            assert result == "Anthropic test response"
            call_kwargs = (
                fake_client.with_options.return_value.messages.create.call_args.kwargs
            )
            assert call_kwargs["model"] == "test-anthropic-model"
    finally:
        get_settings.cache_clear()


def test_generate_response_rejects_blank_prompt() -> None:
    with pytest.raises(AIProviderError, match="Prompt cannot be empty"):
        generate_response("   ")