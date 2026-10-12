from fastapi import FastAPI

from app import __version__
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name, version=__version__)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness check used by CI and the deployment; also reports the running version."""
    return {"status": "ok", "version": __version__}
