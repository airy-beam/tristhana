from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from tristhana import __version__

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: Literal["ok"]
    version: str


@router.get("/health")
async def health() -> Health:
    """Liveness check. Touches no external services, so it stays fast on a cold start."""
    return Health(status="ok", version=__version__)
