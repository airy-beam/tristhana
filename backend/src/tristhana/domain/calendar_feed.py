"""The calendar feed (SC-06, ADR-0036): what a subscribed calendar gets, as plain values.

A feed is expanded instances over a bounded window (no RRULE): classes in UTC instants, my
moon days as all-day dates. A class keeps the identity of its rule date (ADR-0034), so a
moved or swapped occurrence keeps its UID and calendars update it in place.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from tristhana.domain.moon import MoonDayKind

MAX_EVENTS = 2000  # Q148: the furthest-future events are dropped first
TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{43}")  # secrets.token_urlsafe(32): 256 bits


class FeedWindow:
    """Days around the UTC today (Q148)."""

    CLASSES_BACK = 14
    CLASSES_AHEAD = 56
    MOON_BACK = 30
    MOON_AHEAD = 365


@dataclass(frozen=True, slots=True)
class FeedEvent:
    uid: str
    summary: str
    description: str
    location: str | None
    start: datetime | date  # an aware instant, or a date for an all-day event
    end: datetime | date  # exclusive: the next day for an all-day event
    all_day: bool


def uid_class(class_id: UUID, key: date) -> str:
    """The class and its rule date: stable when the occurrence moves or is swapped."""
    return f"{class_id}-{key:%Y%m%d}@tristhana"


def uid_moon(day: date, phase: MoonDayKind) -> str:
    return f"moon-{day:%Y%m%d}-{phase.value}@tristhana"
