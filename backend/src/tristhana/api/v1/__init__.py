"""Versioned REST API: `/api/v1`."""

from fastapi import APIRouter

from tristhana.api.v1 import (
    account_data,
    announcements,
    attendance,
    badges,
    calendar_feed,
    check_in,
    classes,
    days,
    diary,
    directory_listing,
    health,
    links,
    me,
    moon,
    practice,
    progression,
    rest_periods,
    shalas,
    share_cards,
    stats,
)

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
router.include_router(me.router)
router.include_router(account_data.router)
router.include_router(days.router)
router.include_router(rest_periods.router)
router.include_router(practice.router)
router.include_router(check_in.router)
router.include_router(diary.router)
router.include_router(progression.router)
router.include_router(moon.router)
router.include_router(stats.router)
router.include_router(badges.router)
router.include_router(links.router)
router.include_router(shalas.router)
router.include_router(classes.router)
router.include_router(calendar_feed.router)
router.include_router(directory_listing.router)
router.include_router(share_cards.router)
router.include_router(announcements.router)
router.include_router(attendance.router)
