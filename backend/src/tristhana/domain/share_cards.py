"""Shareable cards (ST-07, ADR-0040): what a public card holds. Pure: no I/O, no clock.

A card is meant to be seen by strangers, so it holds less than any private screen:
- Days are two tones only (Q209): *practice* or *no practice*. Rest, moon, 🌸, sick, travel,
  auto-rest, pauses, "No practice" and unmarked days all look the same, so neither a 🌸
  pattern nor an "unlogged" day can be read from a card. The projection happens in the use
  case, before any builder here runs; builders accept tones only.
- No name, city, teacher, note, check-in, run, rest count or percentage (Q201, Q202).
- Moon days are rings from the account's own stored calendar (passed in, never computed).
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from tristhana.domain.days import DayStatus
from tristhana.domain.progression import (
    Celebration,
    CelebrationKind,
    Change,
    Earlier,
    EventKind,
    Progression,
    ProgressionEvent,
    Track,
    celebrations,
)
from tristhana.domain.stats import Summary


class CardFormat(StrEnum):
    STORY = "story"  # 9:16, Telegram stories
    SQUARE = "square"

    @property
    def size(self) -> tuple[int, int]:
        return (1080, 1920) if self is CardFormat.STORY else (1080, 1080)


class CardTone(StrEnum):
    PRACTICE = "practice"
    NO_PRACTICE = "no_practice"


def card_tone(status: DayStatus | None) -> CardTone:
    """The only projection a card ever sees: practiced or not (Q209)."""
    return CardTone.PRACTICE if status is DayStatus.PRACTICED else CardTone.NO_PRACTICE


@dataclass(frozen=True, slots=True)
class MonthCard:
    year: int
    month: int
    tones: tuple[CardTone, ...]  # day 1 … min(today, month end); later days are future
    moon_days: frozenset[int]  # days of the month (future ones too)
    practiced: int
    series: tuple[int, ...]  # series numbers practised, catalog order; never "short"
    minutes: int | None  # total time on the mat; None without any duration
    current: bool  # the month isn't over yet


@dataclass(frozen=True, slots=True)
class YearCard:
    year: int
    tones: tuple[CardTone, ...]  # Jan 1 … min(today, Dec 31)
    moon_days: frozenset[date]
    practiced: int
    finished: bool  # a past year: "214 practices in 2026", else "2026 so far: …"


class AsanaVariant(StrEnum):
    NEW_ASANA = "new_asana"
    SERIES_BEGINS = "series_begins"
    SERIES_COMPLETE = "series_complete"


@dataclass(frozen=True, slots=True)
class AsanaCard:
    variant: AsanaVariant
    series: str  # the catalog slug
    key: str | None  # the asana stop (NEW_ASANA only)
    year: int
    month: int


@dataclass(frozen=True, slots=True)
class CountCard:
    count: int


type Card = MonthCard | YearCard | AsanaCard | CountCard


def _check_tones(tones: Sequence[CardTone]) -> tuple[CardTone, ...]:
    if any(not isinstance(t, CardTone) for t in tones):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise TypeError("cards take projected tones only")
    return tuple(tones)


def month_card(
    year: int,
    month: int,
    today: date,
    tones: Sequence[CardTone],
    moon: Iterable[date],
    summary: Summary,
) -> MonthCard:
    """`summary` is the month's ST-01 summary: only its practice figures are used."""
    series = tuple(sorted(n for n, c in summary.series.items() if n > 0 and c > 0))
    return MonthCard(
        year=year,
        month=month,
        tones=_check_tones(tones),
        moon_days=frozenset(d.day for d in moon if (d.year, d.month) == (year, month)),
        practiced=summary.practiced,
        series=series,
        minutes=summary.duration_total if summary.duration_count else None,
        current=(year, month) == (today.year, today.month),
    )


def year_card(
    year: int, today: date, tones: Sequence[CardTone], moon: Iterable[date], practiced: int
) -> YearCard:
    return YearCard(
        year=year,
        tones=_check_tones(tones),
        moon_days=frozenset(d for d in moon if d.year == year),
        practiced=practiced,
        finished=year < today.year,
    )


_PRECEDENCE = (
    CelebrationKind.SERIES_BEGINS,
    CelebrationKind.SERIES_COMPLETE,
    CelebrationKind.NEW_ASANA,
)


def asana_card(track: Track, event: ProgressionEvent) -> AsanaCard | None:
    """A given asana as a card: series begins > full series > new asana (PR-08 order). None
    for a start, a correction, an item or a stale event. The event is judged on its own
    (before → after), so an older given asana in the history still makes a card."""
    if event.kind is not EventKind.GIVEN or event.before is None or event.after is None:
        return None
    start, end = track.rank(event.before), track.rank(event.after)
    if start is None or end is None or end <= start:
        return None  # stale catalog keys, or not forward (a GIVEN never goes back)
    change = Change(
        EventKind.GIVEN, event.occurred_on, Progression(event.after), event.before, event.after
    )
    found: tuple[Celebration, ...] = celebrations(track, Earlier(), change)
    for kind in _PRECEDENCE:
        # The furthest one wins when a jump crosses several series.
        picked = [c for c in found if c.kind is kind]
        if not picked:
            continue
        c = picked[-1]
        if kind is CelebrationKind.NEW_ASANA:
            if c.series is None or c.key is None:
                return None
            return AsanaCard(
                AsanaVariant.NEW_ASANA,
                c.series,
                c.key,
                event.occurred_on.year,
                event.occurred_on.month,
            )
        if c.series is None:
            continue
        variant = (
            AsanaVariant.SERIES_BEGINS
            if kind is CelebrationKind.SERIES_BEGINS
            else AsanaVariant.SERIES_COMPLETE
        )
        return AsanaCard(variant, c.series, None, event.occurred_on.year, event.occurred_on.month)
    return None


def count_card(count: int, seen: bool) -> CountCard | None:
    """Only a threshold already in the person's GM-01 ledger."""
    return CountCard(count) if seen else None


def is_empty(card: Card) -> bool:
    """Nothing to share: a month or year with no practice."""
    match card:
        case MonthCard() | YearCard():
            return card.practiced == 0
        case _:
            return False
