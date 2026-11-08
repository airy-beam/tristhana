"""What a teacher sees of a student (ST-06, ADR-0031). Two states: blank is absence, so a rest
kind or "No practice" has no value here. Pure.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from uuid import UUID

from tristhana.domain.days import DayStatus
from tristhana.domain.practice import PracticeLength
from tristhana.domain.progression import Position

CARD_DAYS = 7
QUIET_DAYS = 21  # a judgement: ordinary holidays and illness shouldn't raise the note


class SharedDay(StrEnum):
    PRACTICED = "practiced"
    REST = "rest"


# Exhaustive, and the SQL is built from it, so a new status stays hidden until it is mapped here.
SHARED: Mapping[DayStatus, SharedDay | None] = {
    DayStatus.PRACTICED: SharedDay.PRACTICED,
    DayStatus.REST: SharedDay.REST,
    DayStatus.MOON: SharedDay.REST,
    DayStatus.LADIES: SharedDay.REST,
    DayStatus.SICK: SharedDay.REST,
    DayStatus.TRAVEL: SharedDay.REST,
    DayStatus.SKIPPED: None,
}


@dataclass(frozen=True, slots=True)
class StudentToday:
    id: UUID
    name: str | None
    today: SharedDay | None


@dataclass(frozen=True, slots=True)
class DayCell:
    date: date
    shown: SharedDay | None
    length: PracticeLength | None


@dataclass(frozen=True, slots=True)
class StudentCard:
    id: UUID
    name: str | None
    days: tuple[DayCell, ...]
    last_asana: Position | None
    quiet: bool
    # PR-08 Phase 3: the stops the teacher may mark (`teacher_targets`), from `last_asana` only.
    next_asanas: tuple[Position, ...] = ()


def card_days(
    shown: Mapping[date, SharedDay], lengths: Mapping[date, PracticeLength], today: date
) -> tuple[DayCell, ...]:
    """The last 7 days, oldest first, ending on the student's today. Later days never appear, so
    a planned rest end can't be read."""
    cells: list[DayCell] = []
    for back in range(CARD_DAYS - 1, -1, -1):
        day = today - timedelta(days=back)
        state = shown.get(day)
        cells.append(
            DayCell(day, state, lengths.get(day) if state is SharedDay.PRACTICED else None)
        )
    return tuple(cells)


def is_quiet(shown_dates: Collection[date], today: date, linked_on: date, agreed: bool) -> bool:
    """Nothing shown for `QUIET_DAYS`, on a link whose consent names the note. Takes projected
    dates only, so it can't vary with a rest kind or with "No practice" (ADR-0031)."""
    if not agreed or (today - linked_on).days < QUIET_DAYS:
        return False
    first = today - timedelta(days=QUIET_DAYS - 1)
    return not any(first <= d <= today for d in shown_dates)
