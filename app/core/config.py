from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_name: str = "The Lenny Growth Assistant"
    app_version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"

    api_prefix: str = "/api/v1"
    database_url: str = ""

    # AI provider configuration
    model_provider: Literal[
        "ollama",
        "openai",
        "anthropic",
        "claude_agent_sdk",
        "pi_coding_agent",
    ] = "ollama"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"

    claude_agent_sdk_model: str = "claude-sonnet-4-5"

    # Pi Coding Agent configuration
    pi_coding_agent_provider: str = "ollama"
    pi_coding_agent_model: str = "qwen2.5:3b"
    pi_coding_agent_executable: str = "pi"

    model_timeout_seconds: int = 180

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached application settings instance."""
    return Settings()
