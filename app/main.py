from fastapi import FastAPI

from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0")


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness check used by CI and the deployment."""
    return {"status": "ok"}
