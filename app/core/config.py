from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "dev-only-secret-do-not-use-in-production"
MIN_JWT_SECRET_BYTES = 32  # RFC 7518: HS256 keys should be at least 256 bits


class Settings(BaseSettings):
    """Application settings, read from environment variables or the .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Cella API"
    environment: str = "local"
    database_url: str = "postgresql+psycopg://cella:cella@localhost:5432/cella"

    # Auth
    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_days: int = 7

    # Public demo: POST /auth/demo creates a private copy of the demo household per visitor.
    demo_enabled: bool = False
    demo_ttl_hours: int = 24
    # Ceiling of live demo copies, so a flood of clicks cannot fill the database.
    demo_max_sandboxes: int = 500

    # Origins allowed to call the API from a browser (the Vite dev server by default).
    cors_origins: list[str] = ["http://localhost:5173"]

    @model_validator(mode="after")
    def require_real_secret_in_production(self) -> "Settings":
        if self.environment == "production":
            if self.jwt_secret == DEFAULT_JWT_SECRET:
                raise ValueError("JWT_SECRET must be set in production")
            if len(self.jwt_secret.encode()) < MIN_JWT_SECRET_BYTES:
                raise ValueError(f"JWT_SECRET must be at least {MIN_JWT_SECRET_BYTES} bytes")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
