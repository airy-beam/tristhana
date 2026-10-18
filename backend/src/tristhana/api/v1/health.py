from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from tristhana import __version__
from tristhana.api.deps import app_settings, storage

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: Literal["ok"]
    version: str
    commit: str


@router.get("/health")
async def health(request: Request) -> Health:
    """Liveness check. Touches no external services, so it stays fast on a cold start."""
    return Health(status="ok", version=__version__, commit=app_settings(request).git_sha)


class DbHealth(BaseModel):
    status: Literal["ok"]


@router.get("/health/db", include_in_schema=False)
async def health_db(request: Request) -> DbHealth:
    """Keep-warm target (every 10 min): keeps an instance warm and the Supabase free tier
    active. `StorageUnavailable` becomes a 503."""
    await storage(request).ping()
    return DbHealth(status="ok")
