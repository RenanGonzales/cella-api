from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read from environment variables or the .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Cella API"
    environment: str = "local"
    database_url: str = "postgresql+psycopg://cella:cella@localhost:5432/cella"


@lru_cache
def get_settings() -> Settings:
    return Settings()
