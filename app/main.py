from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import auth, categories, markets, me, products, storage_areas
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
app.include_router(storage_areas.router)
app.include_router(categories.router)
app.include_router(products.router)
app.include_router(markets.router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness check used by CI and the deployment; also reports the running version."""
    return {"status": "ok", "version": __version__}
