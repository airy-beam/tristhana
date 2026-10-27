"""Versioned REST API: `/api/v1`."""

from fastapi import APIRouter

from tristhana.api.v1 import (
    check_in,
    days,
    diary,
    health,
    me,
    moon,
    practice,
    progression,
    rest_periods,
    stats,
)

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
router.include_router(me.router)
router.include_router(days.router)
router.include_router(rest_periods.router)
router.include_router(practice.router)
router.include_router(check_in.router)
router.include_router(diary.router)
router.include_router(progression.router)
router.include_router(moon.router)
router.include_router(stats.router)
