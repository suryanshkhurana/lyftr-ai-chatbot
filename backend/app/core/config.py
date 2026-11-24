"""Environment-driven configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_KEYS = 2


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    llm_api_keys: str = Field(default="", alias="LLM_API_KEYS")
    database_url: str = Field(default="sqlite:///./data/app.db", alias="DATABASE_URL")
    allowed_origins: str = Field(default="http://localhost:3000", alias="ALLOWED_ORIGINS")
    enable_failure_simulation: bool = Field(default=False, alias="ENABLE_FAILURE_SIMULATION")

    llm_model: str = Field(default="gemini/gemini-flash-lite-latest", alias="LLM_MODEL")
    llm_api_base: str | None = Field(default=None, alias="LLM_API_BASE")  # optional, e.g. OpenAI-compatible host
    llm_temperature: float = Field(default=0.2, alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=2048, alias="LLM_MAX_TOKENS")
    llm_timeout_seconds: float = Field(default=12.0, alias="LLM_TIMEOUT_SECONDS")
    default_system_prompt: str = Field(
        default="You are Lyftr AI, a helpful, concise assistant. Answer clearly and accurately.",
        alias="DEFAULT_SYSTEM_PROMPT",
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Optional self-hosted last-resort fallback (OpenAI-compatible). Disabled unless model, base and key are set.
    fallback_llm_model: str = Field(default="", alias="FALLBACK_LLM_MODEL")
    fallback_llm_api_base: str = Field(default="", alias="FALLBACK_LLM_API_BASE")
    fallback_llm_api_key: str = Field(default="", alias="FALLBACK_LLM_API_KEY")
    fallback_llm_timeout_seconds: float = Field(default=120.0, alias="FALLBACK_LLM_TIMEOUT_SECONDS")

    @property
    def fallback_enabled(self) -> bool:
        return all(v.strip() for v in (self.fallback_llm_model, self.fallback_llm_api_base, self.fallback_llm_api_key))

    @property
    def api_keys(self) -> list[str]:
        """Comma-separated keys, trimmed; empty entries are dropped (and reported via key_config_error)."""
        return [k.strip() for k in self.llm_api_keys.split(",") if k.strip()]

    @property
    def key_config_error(self) -> str | None:
        raw_parts = self.llm_api_keys.split(",") if self.llm_api_keys.strip() else []
        if any(not p.strip() for p in raw_parts):
            return "LLM_API_KEYS contains an empty entry"
        if len(self.api_keys) < MIN_KEYS:
            return f"LLM_API_KEYS must contain at least {MIN_KEYS} keys"
        return None

    @property
    def origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def sqlite_path(self) -> Path:
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            raise ValueError("DATABASE_URL must be a SQLite URL like sqlite:////data/app.db")
        # sqlite:////data/app.db -> /data/app.db ; sqlite:///./data/app.db -> ./data/app.db
        return Path(self.database_url[len(prefix):])


@lru_cache
def get_settings() -> Settings:
    return Settings()
