from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "PeoplePulse"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://aetherhr:aetherhr@db:5432/aetherhr"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    cors_origins: list[str] = ["http://127.0.0.1:8000", "http://localhost:8000"]

    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
