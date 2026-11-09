"""Announcements from a teacher to their students, or to a shala (NT-03, ADR-0038).

Plain text, relayed as written: nothing here parses it, so an announcement never changes a
day, a rest day or a reminder. The tick delivers it from the live audience; quiet hours decide
only the sound, never the timing (Q165: a 22:00 "no Mysore tomorrow" must arrive before 6:00).
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from uuid import UUID
from zoneinfo import ZoneInfo

from tristhana.domain.notifications import QuietHours

TEXT_MAX = 1000  # code points (Q169)
PER_SOURCE_PER_DAY = 3  # rolling 24 h, deleted ones don't count (Q173)
RATE_WINDOW = timedelta(hours=24)
STALE = timedelta(hours=24)  # a safety bound after a tick outage, not a hold
FEED_DAYS = 30
FEED_WINDOW = timedelta(days=FEED_DAYS)
KEEP = timedelta(days=90)  # then pruned by the tick (Q174)
PIN_DAYS = frozenset({7, 30})

_BIDI_CONTROLS = re.compile("[‪-‮⁦-⁩‎‏]")
_BLANK_RUN = re.compile(r"\n{4,}")  # 3+ blank lines


class SourceKind(StrEnum):
    TEACHER = "t"
    SHALA = "h"


@dataclass(frozen=True, slots=True)
class Source:
    """Who it comes from: a teacher's account id, or a shala id."""

    kind: SourceKind
    id: UUID


class InvalidAnnouncement(ValueError):
    """Blank or too long text, an unknown pin length, or no one to send it to."""


class AnnouncementLimit(Exception):
    """PER_SOURCE_PER_DAY reached for this source."""


def normalize_text(raw: str) -> str | None:
    """Stripped, control characters dropped (line breaks kept, tabs become spaces), at most
    two blank lines in a row; None when blank or over TEXT_MAX code points."""
    text = _BIDI_CONTROLS.sub("", raw.replace("\r\n", "\n").replace("\r", "\n"))
    text = "".join(
        " " if ch == "\t" else ch for ch in text if ch in "\n\t" or unicodedata.category(ch) != "Cc"
    )
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = _BLANK_RUN.sub("\n\n\n", text).strip()
    if not text or len(text) > TEXT_MAX:
        return None
    return text


def announcement_key(id: UUID) -> str:
    """The delivery ledger's dedupe key."""
    return f"ann:{id}"


@dataclass(frozen=True, slots=True)
class Send:
    silent: bool  # in the recipient's quiet hours, or no known zone
    local_date: date  # the recipient's date (the UTC date with no zone), for the ledger


def due(now: datetime, created_at: datetime, zone: str | None, quiet: QuietHours) -> Send | None:
    """How to push it now: never held for quiet hours (Q165), only silent in them. None only
    when it is STALE (a tick outage): it stays in the feed. The daily cap is not consulted
    (Q166): a person is speaking."""
    if now >= created_at + STALE:
        return None
    if zone is None:
        return Send(silent=True, local_date=now.astimezone(UTC).date())
    local = now.astimezone(ZoneInfo(zone))
    return Send(silent=quiet.contains(local.time().replace(tzinfo=None)), local_date=local.date())


def pinned(pinned_until: datetime | None, now: datetime) -> bool:
    return pinned_until is not None and now < pinned_until


def pin_until(now: datetime, days: int) -> datetime | None:
    """0 = no pin; else one of PIN_DAYS."""
    if days == 0:
        return None
    if days not in PIN_DAYS:
        raise InvalidAnnouncement("pin for 7 or 30 days")
    return now + timedelta(days=days)
