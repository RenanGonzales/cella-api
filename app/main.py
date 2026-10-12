from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import auth, me
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name, version=__version__)

# Only needed in local development, where the Vite dev server runs on another port.
# In production the frontend and the API share the same origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(me.router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness check used by CI and the deployment; also reports the running version."""
    return {"status": "ok", "version": __version__}
