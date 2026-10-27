"""Day status (PR-01, PR-04): what kind of day a practitioner had, per local date.

Rest days are part of the practice (01 Domain Context): rest, moon, ladies' holiday, sick
and travel are all "rest-like"; only `practiced` and `skipped` ("No practice") say whether
the person practised on a day they could have.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from tristhana.domain.check_in import CheckIn
from tristhana.domain.locale import Locale
from tristhana.domain.practice import Practice

MIN_LOG_DATE = date(2000, 1, 1)
MAX_RANGE_DAYS = 371  # a heatmap year plus a week
# The latest calendar date anywhere on Earth (UTC+14): an unknown zone never blocks "today".
_LATEST_ZONE = "Pacific/Kiritimati"
# A guess used only to pick "today" for people whose device zone we don't know yet. Never
# stored on the account and never used for reminders (06 Time Zones).
_PROVISIONAL_ZONES: dict[Locale, str] = {"ru": "Europe/Moscow", "en": "UTC"}


class DayStatus(StrEnum):
    PRACTICED = "practiced"
    REST = "rest"
    MOON = "moon"
    LADIES = "ladies"  # private: others only ever see REST (WH-02)
    SICK = "sick"
    TRAVEL = "travel"
    SKIPPED = "skipped"  # shown as "No practice": never a judgment


REST_LIKE = frozenset(
    {DayStatus.REST, DayStatus.MOON, DayStatus.LADIES, DayStatus.SICK, DayStatus.TRAVEL}
)


@dataclass(frozen=True, slots=True)
class DayLog:
    local_date: date
    status: DayStatus
    practices: tuple[Practice, ...] = ()  # only on a practiced day
    check_ins: tuple[CheckIn, ...] = ()  # PR-06: only on a practiced day, never empty ones


class DateInFuture(ValueError):
    pass


class DateTooEarly(ValueError):
    pass


class InvalidRange(ValueError):
    pass


def public_status(status: DayStatus) -> DayStatus:
    """What anyone but the person may see (and what the database stores in plain text)."""
    return DayStatus.REST if status is DayStatus.LADIES else status


def provisional_zone(locale: Locale) -> str:
    return _PROVISIONAL_ZONES[locale]


def local_today(now: datetime, zone: str) -> date:
    return now.astimezone(ZoneInfo(zone)).date()


def latest_loggable(now: datetime, zone: str | None) -> date:
    """Today in the person's zone; with no known zone, the latest date on Earth, so a wrong
    guess can't refuse a real "today"."""
    return local_today(now, zone or _LATEST_ZONE)


def check_loggable(day: date, now: datetime, zone: str | None) -> None:
    if day > latest_loggable(now, zone):
        raise DateInFuture(day.isoformat())
    if day < MIN_LOG_DATE:
        raise DateTooEarly(day.isoformat())


def check_range(start: date, end: date) -> None:
    if start > end or end - start >= timedelta(days=MAX_RANGE_DAYS):
        raise InvalidRange(f"{start.isoformat()}..{end.isoformat()}")
