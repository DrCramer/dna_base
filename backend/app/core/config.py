from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Лабораторный реестр ДНК"
    database_url: str = "postgresql+asyncpg://dna:dna@postgres:5432/dna_registry"
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 60 * 12
    cookie_name: str = "dna_registry_session"
    storage_dir: Path = Path("/app/data")
    cors_origins: list[str] = [
        "http://localhost:4001",
        "http://127.0.0.1:4001",
        "http://localhost:4000",
        "http://127.0.0.1:4000",
    ]
    cors_origin_regex: str | None = (
        r"^https?://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|"
        r"172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+|192\.168\.\d+\.\d+)(:\d+)?$"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
