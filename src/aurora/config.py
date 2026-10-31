"""Configurações tipadas da aplicação carregadas a partir do ambiente / .env."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Configurações globais do assistente do Residencial Aurora."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    google_api_key: str = Field(default="")
    gemini_api_key: str = Field(default="")
    gemini_model: str = Field(default="gemini-3.5-flash-lite")
    database_url: str = Field(
        default="postgresql+asyncpg://aurora:aurora@localhost:5432/aurora"
    )
    dados_dir: Path = Field(default=PROJECT_ROOT / "dados")
    app_name: str = Field(default="residencial_aurora")

    @model_validator(mode="after")
    def _sync_genai_env(self) -> "Settings":
        effective_key = self.google_api_key or self.gemini_api_key
        if effective_key:
            self.google_api_key = effective_key
            os.environ.setdefault("GOOGLE_API_KEY", effective_key)
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retorna a instância cacheada de Settings."""
    return Settings()
