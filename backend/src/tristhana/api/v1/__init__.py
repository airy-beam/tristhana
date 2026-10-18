"""Versioned REST API: `/api/v1`."""

from fastapi import APIRouter

from tristhana.api.v1 import days, health, me

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
router.include_router(me.router)
router.include_router(days.router)
