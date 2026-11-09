"""Class attendance (SC-05, ADR-0039): who was at an occurrence. Pure.

One row per (class, rule date, person), with a snapshot of the occurrence so history survives
rule edits. Two states: `claimed` (the person marked it) and `confirmed` (staff marked or
confirmed it). There is no absent or declined state: removing a mark is silent. Attendance is
presence, never a log entry: nothing here reads or writes a day, a practice or a rest.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from tristhana.domain.classes import ClassType, Occurrence
from tristhana.domain.days import local_today

BACK_DAYS = 6  # today and the 6 days before, in the class zone (Q184)
REGULAR_DAYS = 28  # "regulars" sort a roster (Q191); never shown as a label
PRACTISES_HERE_DAYS = 90  # staff with a mark this recent appear on rosters (Q187)
MAX_DELTA = 100  # ids per side of one staff write
BOT_PAGE = 8
API_PAGE = 50
MY_LIST = 10  # rows on the bot's "I was there…" and staff picker lists

# Q196 (ashtanga-expert): "Log this day" after asana or pranayama practice only; Conference
# and Chanting are not practice, so the shortcut would read oddly there.
LOG_DAY_TYPES = frozenset(
    {
        ClassType.MYSORE,
        ClassType.LED,
        ClassType.PRIVATE,
        ClassType.WORKSHOP,
        ClassType.PRANAYAMA,
    }
)


class AttendanceState(StrEnum):
    CLAIMED = "claimed"
    CONFIRMED = "confirmed"


class NotAttendable(ValueError):
    """Not started, cancelled, older than the window, or no such occurrence."""


class InvalidAttendance(ValueError):
    """A staff write: too many ids, an id on both sides, or an id that isn't a member."""


@dataclass(frozen=True, slots=True)
class Snapshot:
    """What a later read needs, copied from the occurrence when the row is written."""

    shala_id: UUID
    class_id: UUID
    key: date  # the rule date (the occurrence identity, ADR-0034)
    on: date  # where it took place, local to the class zone
    starts_at: datetime  # UTC
    zone: str  # IANA, never an offset
    type: ClassType


@dataclass(frozen=True, slots=True)
class Counts:
    confirmed: int
    claimed: int


def attendable(o: Occurrence, zone: str, now: datetime) -> bool:
    """Not cancelled, started, and on or after the class zone's today - 6. The kept original
    of a swap (on A) is cancelled, so it is out."""
    if o.cancelled is not None or o.swapped_to is not None:
        return False
    if o.starts_at > now:
        return False
    return o.on >= local_today(now, zone) - timedelta(days=BACK_DAYS)


def snapshot(o: Occurrence, shala_id: UUID, zone: str) -> Snapshot:
    return Snapshot(shala_id, o.class_id, o.key, o.on, o.starts_at, zone, o.type)


def claim_state(may_take: bool) -> AttendanceState:
    """A staff member's own claim is confirmed at once (Q182)."""
    return AttendanceState.CONFIRMED if may_take else AttendanceState.CLAIMED


def merge(current: AttendanceState | None, new: AttendanceState) -> AttendanceState:
    """A write never downgrades `confirmed`."""
    if current is AttendanceState.CONFIRMED:
        return current
    return new


def offers_log_day(type: ClassType) -> bool:
    return type in LOG_DAY_TYPES
