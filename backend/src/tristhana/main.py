"""Composition root: wires settings, logging and adapters into one ASGI app.

Run with `uvicorn tristhana.main:app`.
"""

from fastapi import FastAPI

from tristhana import __version__
from tristhana.api import v1
from tristhana.logs import configure_logging
from tristhana.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.effective_log_format)

    app = FastAPI(
        title="Tristhana API",
        version=__version__,
        # Interactive docs only outside prod; the OpenAPI schema stays available for codegen.
        docs_url=None if settings.app_env == "prod" else "/docs",
        redoc_url=None,
    )
    app.state.settings = settings
    app.include_router(v1.router)
    return app


app = create_app()
