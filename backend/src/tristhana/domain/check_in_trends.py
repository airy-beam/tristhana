"""Check-in trends (ST-05): the person's own mood, energy and effort averages over the last
12 calendar months, by month, by weekday, and near a full or new moon. Pure.

Under a minimum the answer is None, decided here, so no small-sample average ever leaves the
domain. The module holds no words and no comparisons: no "highest", no differences, no order
by value. Nothing here describes absence, so no 🌸 day can show through.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from tristhana.domain.moon import MoonDay, MoonPhase

MONTHS = 12  # the window: the 1st of the month 11 months before today's month .. today
MIN_TOTAL = 10  # check-ins with at least one scale in the window, before anything is shown
MIN_BUCKET = 5  # values of one scale in one month / weekday / moon bucket, before its average
NEAR_DAYS = 1  # "near" a full or new moon: |local_date - moon date| <= 1


class Scale(StrEnum):
    MOOD = "mood"
    ENERGY = "energy"
    EFFORT = "effort"


class MoonBucket(StrEnum):
    FULL = "full"
    NEW = "new"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class ScaleDay:
    """One check-in's scales on a practiced day; each scale is optional (PR-06)."""

    local_date: date
    mood: int | None
    energy: int | None
    effort: int | None

    def value(self, scale: Scale) -> int | None:
        return {Scale.MOOD: self.mood, Scale.ENERGY: self.energy, Scale.EFFORT: self.effort}[scale]

    @property
    def scaled(self) -> bool:
        return self.mood is not None or self.energy is not None or self.effort is not None


@dataclass(frozen=True, slots=True)
class TrendFacts:
    days: tuple[ScaleDay, ...]
    moon: tuple[MoonDay, ...]  # the followed calendar, the window widened by NEAR_DAYS


@dataclass(frozen=True, slots=True)
class Average:
    tenths: int  # the mean x 10, rounded half up in integer arithmetic
    n: int


Averages = Mapping[Scale, Average | None]  # None: under MIN_BUCKET


@dataclass(frozen=True, slots=True)
class Trends:
    start: date
    end: date
    total: int  # check-ins with at least one scale
    enough: bool
    months: tuple[tuple[date, Averages], ...]  # 12, oldest first; () unless enough
    weekdays: tuple[Averages, ...] | None  # 7, Monday first
    moon: Mapping[MoonBucket, Averages] | None


def window(today: date) -> tuple[date, date]:
    back = today.year * 12 + today.month - 1 - (MONTHS - 1)
    return date(back // 12, back % 12 + 1, 1), today


def average(values: Sequence[int], minimum: int = MIN_BUCKET) -> Average | None:
    n = len(values)
    if n < minimum or n == 0:
        return None
    return Average((20 * sum(values) + n) // (2 * n), n)


def _near(moon: Iterable[MoonDay], near: int) -> dict[date, MoonBucket]:
    found: dict[date, MoonBucket] = {}
    for m in moon:
        bucket = MoonBucket.FULL if m.kind.phase is MoonPhase.PURNIMA else MoonBucket.NEW
        for offset in range(-near, near + 1):
            found[m.date + timedelta(days=offset)] = bucket
    return found


def moon_bucket(day: date, moon: Iterable[MoonDay], near: int = NEAR_DAYS) -> MoonBucket:
    """The moon day itself is inside "near": most people rest on it, so a bucket of that day
    alone would stay empty, and would single out who practised on it."""
    return _near(moon, near).get(day, MoonBucket.OTHER)


def _averages(days: Iterable[ScaleDay]) -> Averages:
    listed = tuple(days)
    return {
        scale: average([v for d in listed if (v := d.value(scale)) is not None]) for scale in Scale
    }


def _shown(averages: Averages) -> set[Scale]:
    return {scale for scale, found in averages.items() if found is not None}


def trends(facts: TrendFacts, today: date) -> Trends:
    start, end = window(today)
    days = tuple(d for d in facts.days if d.scaled and start <= d.local_date <= end)
    total = len(days)
    if total < MIN_TOTAL:
        return Trends(start, end, total, False, (), None, None)

    firsts = [
        date((back := start.year * 12 + start.month - 1 + i) // 12, back % 12 + 1, 1)
        for i in range(MONTHS)
    ]
    months = tuple(
        (
            first,
            _averages(
                d
                for d in days
                if (d.local_date.year, d.local_date.month) == (first.year, first.month)
            ),
        )
        for first in firsts
    )

    by_weekday = tuple(
        _averages(d for d in days if d.local_date.isoweekday() == iso) for iso in range(1, 8)
    )
    # One weekday alone is a single figure, not a view by weekday.
    several = any(sum(scale in _shown(a) for a in by_weekday) >= 2 for scale in Scale)

    near = _near(facts.moon, NEAR_DAYS)
    by_moon = {
        bucket: _averages(d for d in days if near.get(d.local_date, MoonBucket.OTHER) is bucket)
        for bucket in MoonBucket
    }
    # Days near a moon are only worth setting beside the others when both sides have a figure.
    beside = _shown(by_moon[MoonBucket.OTHER]) & (
        _shown(by_moon[MoonBucket.FULL]) | _shown(by_moon[MoonBucket.NEW])
    )
    return Trends(
        start,
        end,
        total,
        True,
        months,
        by_weekday if several else None,
        by_moon if facts.moon and beside else None,
    )
