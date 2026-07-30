"""Application configuration via Pydantic Settings (reads .env).

All settings are prefixed with ``TRADESCOUT_`` so they never clash with other
tools. A ``.env`` file is optional; sensible defaults are used otherwise.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="TRADESCOUT_",
        extra="ignore",
    )

    app_name: str = "TradeScout AI"
    app_version: str = "0.1.0"
    database_url: str = "sqlite:///./tradescout.db"
    mock_mode: bool = True
    default_campaign_name: str = "Demo Campaign"

    # LLM integration (all optional — leave blank to use offline heuristics).
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"


settings = Settings()
