
import asyncio
import logging
from functools import lru_cache

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class AIProviderError(Exception):
    """Raised when an AI provider cannot return a response."""


@lru_cache
def _get_openai_client(api_key: str):
    from openai import OpenAI

    return OpenAI(api_key=api_key)


@lru_cache
def _get_anthropic_client(api_key: str):
    from anthropic import Anthropic

    return Anthropic(api_key=api_key)


def _generate_ollama(prompt: str) -> str:
    import json
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    settings = get_settings()
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    payload = {
        "model": settings.ollama_model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(
                request,
                timeout=settings.model_timeout_seconds,
        ) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        logger.warning("Ollama returned HTTP status %s.", exc.code)
        raise AIProviderError(
            f"Ollama returned HTTP status {exc.code}."
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        logger.warning("Unable to reach Ollama: %s", type(exc).__name__)
        raise AIProviderError(
            "Unable to reach Ollama. Check that it is running."
        ) from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AIProviderError(
            "Ollama returned an invalid response."
        ) from exc

    content = result.get("message", {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise AIProviderError("Ollama returned an empty response.")

    return content.strip()


def _generate_openai(prompt: str) -> str:
    settings = get_settings()

    if not settings.openai_api_key:
        raise AIProviderError(
            "OPENAI_API_KEY is not configured for the OpenAI provider."
        )

    try:
        client = _get_openai_client(settings.openai_api_key)
        result = client.with_options(
            timeout=settings.model_timeout_seconds
        ).chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
        )
        content = result.choices[0].message.content
    except Exception as exc:
        logger.warning("OpenAI request failed: %s", type(exc).__name__)
        raise AIProviderError("The OpenAI request failed.") from exc

    if not content or not content.strip():
        raise AIProviderError("OpenAI returned an empty response.")

    return content.strip()


def _generate_anthropic(prompt: str) -> str:
    settings = get_settings()

    if not settings.anthropic_api_key:
        raise AIProviderError(
            "ANTHROPIC_API_KEY is not configured for the Anthropic provider."
        )

    try:
        client = _get_anthropic_client(settings.anthropic_api_key)
        result = client.with_options(
            timeout=settings.model_timeout_seconds
        ).messages.create(
            model=settings.anthropic_model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        text_blocks = [
            block.text
            for block in result.content
            if getattr(block, "type", None) == "text"
        ]
        content = "\n".join(text_blocks)
    except Exception as exc:
        logger.warning("Anthropic request failed: %s", type(exc).__name__)
        raise AIProviderError("The Anthropic request failed.") from exc

    if not content.strip():
        raise AIProviderError("Anthropic returned an empty response.")

    return content.strip()


async def _generate_claude_agent_sdk(prompt: str) -> str:
    """Generate a response through Claude Agent SDK without enabling tools."""
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        query,
    )

    settings = get_settings()
    text_parts: list[str] = []
    result_text = ""

    try:
        options = ClaudeAgentOptions(
            model=settings.claude_agent_sdk_model,
            tools=[],
            allowed_tools=[],
            permission_mode="dontAsk",
            max_turns=1,
        )

        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if getattr(block, "type", None) == "text":
                        text = getattr(block, "text", "")
                        if text:
                            text_parts.append(text)

            elif isinstance(message, ResultMessage):
                result_text = getattr(message, "result", "") or ""

    except Exception as exc:
        logger.warning(
            "Claude Agent SDK request failed: %s",
            type(exc).__name__,
        )
        raise AIProviderError(
            "Claude Agent SDK request failed. Check Claude Code CLI "
            "availability and authentication."
        ) from exc

    content = "\n".join(text_parts).strip() or result_text.strip()

    if not content:
        raise AIProviderError(
            "Claude Agent SDK returned an empty response."
        )

    return content



def _generate_pi_coding_agent(prompt: str) -> str:
    """Generate a response through Pi Coding Agent."""
    import os
    import shutil
    import subprocess

    settings = get_settings()
    executable = shutil.which(settings.pi_coding_agent_executable)

    if not executable:
        raise AIProviderError(
            "Pi Coding Agent CLI was not found. Ensure 'pi' is on PATH."
        )

    command = [
        executable,
        "--provider", settings.pi_coding_agent_provider,
        "--model", settings.pi_coding_agent_model,
        "--no-session",
        "--no-tools",
        "--print",
        prompt,
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(settings.model_timeout_seconds, 300),
            check=False,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired as exc:
        logger.warning("Pi Coding Agent timed out. Prompt length: %s", len(prompt))
        raise AIProviderError("Pi Coding Agent timed out.") from exc
    except OSError as exc:
        logger.warning("Could not launch Pi: %s", type(exc).__name__)
        raise AIProviderError("Could not start Pi Coding Agent.") from exc

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        logger.error(
            "Pi exited with status %s. stderr=%s",
            result.returncode,
            stderr[-2000:],
        )
        raise AIProviderError(
            f"Pi Coding Agent failed (exit {result.returncode}). "
            f"{stderr[-500:] or 'Check provider configuration.'}"
        )

    content = (result.stdout or "").strip()
    if not content:
        raise AIProviderError("Pi Coding Agent returned an empty response.")

    return content

def generate_response(prompt: str) -> str:
    """Generate a response using a synchronous provider."""
    settings = get_settings()

    if not prompt.strip():
        raise AIProviderError("Prompt cannot be empty.")

    try:
        if settings.model_provider == "ollama":
            return _generate_ollama(prompt)
        if settings.model_provider == "openai":
            return _generate_openai(prompt)
        if settings.model_provider == "anthropic":
            return _generate_anthropic(prompt)
        if settings.model_provider == "claude_agent_sdk":
            return asyncio.run(_generate_claude_agent_sdk(prompt))
        if settings.model_provider == "pi_coding_agent":
            return _generate_pi_coding_agent(prompt)

        raise AIProviderError(
            f"Unsupported provider '{settings.model_provider}'."
        )
    except AIProviderError:
        raise


async def generate_response_async(prompt: str) -> str:
    """Generate a response without blocking the async API route."""
    settings = get_settings()

    if not prompt.strip():
        raise AIProviderError("Prompt cannot be empty.")

    if settings.model_provider == "claude_agent_sdk":
        return await _generate_claude_agent_sdk(prompt)

    return await asyncio.to_thread(generate_response, prompt)
