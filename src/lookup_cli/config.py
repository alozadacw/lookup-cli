"""
Central config. Secrets come from environment variables / .env (per the
project's decision to avoid a keychain/vault dependency for v1). Each
connector plugin defines and documents its own required env vars in its
own package -- this file only holds settings the core needs.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOOKUP_CLI_", env_file=".env", extra="ignore")

    cache_db_path: Path = Path.home() / ".lookup-cli" / "cache.sqlite3"
    cache_ttl_seconds: int = 3600


def get_settings() -> Settings:
    settings = Settings()
    settings.cache_db_path.parent.mkdir(parents=True, exist_ok=True)
    return settings
