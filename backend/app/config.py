import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", _BACKEND_ROOT / ".env", Path(".env")),
        extra="ignore",
    )

    company_name: str = "SKODA"
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    llm_provider: str = "auto"  # auto | openai | anthropic | claude | azure | mock
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_reasoning_model: str = "o4-mini"
    openai_reasoning_effort: str = "medium"
    openai_finetune_auto: bool = True
    openai_finetune_base: str = "gpt-4o-mini"
    openai_finetune_min_examples: int = 20
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = ""
    azure_openai_api_version: str = "2024-08-01-preview"
    database_url: str = "postgresql://negotiator:negotiator@postgres:5432/negotiation"
    redis_url: str = "redis://redis:6379/0"
    use_in_memory: bool = False
    handoff_webhook_url: str = ""
    slack_webhook_url: str = ""
    sendgrid_api_key: str = ""
    notify_email_from: str = "aria@skoda.example"
    notify_email_to: str = ""
    cors_origins: str = "http://localhost:3000"
    rate_limit_per_minute: int = 30
    session_ttl_seconds: int = 60 * 60 * 6
    handoff_sla: str = "2 hours during sourcing-desk hours"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if os.environ.get("VERCEL") == "1" and "USE_IN_MEMORY" not in os.environ:
        return settings.model_copy(update={"use_in_memory": True})
    return settings
