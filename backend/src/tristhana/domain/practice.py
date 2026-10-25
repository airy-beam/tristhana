"""Practice details on a practiced day (PR-02 context, PR-03 length, PR-05 duration/start).

A practice is always opening → standing → [series…] → [backbending] → finishing; only the
series part varies, so a length is the series range plus where it ended (natural keys,
ADR-0010; validated against the in-memory catalog, ADR-0017).
"""

from collections import Counter
from dataclasses import dataclass, replace
from datetime import time
from enum import StrEnum
from typing import Literal

from tristhana.domain.catalog import AsanaNames, Catalog, SequenceKind, SequenceStatus
from tristhana.domain.locale import Locale

MAX_DURATION_MIN = 600
RECENT_LIMIT = 60  # practices looked at for presets
RECENT_PRESETS = 3

type FirstPart = Literal["first_half", "second_half"]
# Series taught in halves: the first half ends at this item, the second starts right after.
SERIES_HALVES: dict[str, str] = {"primary": "navasana"}


class PracticeContext(StrEnum):
    MYSORE = "mysore"
    LED = "led"
    PRIVATE = "private"  # 1:1
    SELF = "self"  # self-practice: home, hotel, shala outside class hours


class InvalidLength(ValueError):
    pass


class InvalidPractice(ValueError):
    pass


class TimezoneUnknown(ValueError):
    """A start time needs the person's real zone; a provisional guess is never stored."""


@dataclass(frozen=True, slots=True)
class PracticeLength:
    """`series` in practice order (empty = short practice: no series; backbending optional);
    every series is full except: the first may be one half (`first_part`, only when another
    series follows: "Primary, 2nd half + Intermediate"), the last may end early (`end`, a
    stop point; None = full)."""

    series: tuple[str, ...] = ()
    end: str | None = None
    first_part: FirstPart | None = None


SHORT = PracticeLength()


@dataclass(frozen=True, slots=True)
class Practice:
    context: PracticeContext | None = None
    online: bool = False
    length: PracticeLength | None = None  # None: not given
    duration_min: int | None = None
    start_time: time | None = None  # wall clock in `timezone` (ADR-0005)
    timezone: str | None = None
    slot: int = 1


@dataclass(frozen=True, slots=True)
class StopPoint:
    key: str  # natural key, e.g. "janu-sirsasana-c"
    names: AsanaNames
    variant: str | None

    def label(self, locale: Locale) -> str:
        name = self.names.ru if locale == "ru" else self.names.latin
        return f"{name} {self.variant.upper()}" if self.variant else name


@dataclass(frozen=True, slots=True)
class Series:
    slug: str
    number: int
    name_en: str
    name_ru: str
    items: tuple[str, ...]  # every item key, in order
    stops: tuple[StopPoint, ...]  # where a practice may end, in order


class PracticeCatalog:
    """The confirmed series of the catalog, indexed for lengths and pickers."""

    def __init__(self, catalog: Catalog) -> None:
        names = {a.slug: a.names for a in catalog.asanas}
        series: list[Series] = []
        for seq in catalog.sequences:
            if seq.kind is not SequenceKind.SERIES or seq.status is not SequenceStatus.CONFIRMED:
                continue
            assert seq.number is not None  # noqa: S101 - validated by the catalog loader
            stops = tuple(StopPoint(i.key, names[i.asana], i.variant) for i in seq.items if i.stop)
            series.append(
                Series(
                    seq.slug,
                    seq.number,
                    seq.names.en,
                    seq.names.ru,
                    tuple(i.key for i in seq.items),
                    stops,
                )
            )
        self.series = tuple(sorted(series, key=lambda s: s.number))
        self._by_slug = {s.slug: s for s in self.series}
        self._by_number = {s.number: s for s in self.series}

    def get(self, slug: str) -> Series | None:
        return self._by_slug.get(slug)

    def by_number(self, number: int) -> Series | None:
        return self._by_number.get(number)

    def stop(self, slug: str, key: str) -> StopPoint | None:
        series = self._by_slug.get(slug)
        return next((s for s in series.stops if s.key == key), None) if series else None


def check_length(catalog: PracticeCatalog, length: PracticeLength) -> PracticeLength:
    """The normalised length, or `InvalidLength`."""
    if not length.series:
        if length.end is not None or length.first_part is not None:
            raise InvalidLength("a short practice has no series end or half")
        return SHORT
    found = [catalog.get(slug) for slug in length.series]
    if any(s is None for s in found):
        raise InvalidLength("unknown or unconfirmed series")
    series = [s for s in found if s is not None]
    numbers = [s.number for s in series]
    if numbers != list(range(numbers[0], numbers[0] + len(numbers))):
        raise InvalidLength("series must be contiguous and in practice order")
    first, last = series[0], series[-1]
    split = SERIES_HALVES.get(first.slug)
    if length.first_part is not None and split is None:
        raise InvalidLength(f"{first.slug} has no halves")
    end = length.end
    if end is not None:
        stop_keys = [s.key for s in last.stops]
        if end not in stop_keys:
            raise InvalidLength(f"{end} is not a stop point of {last.slug}")
        if end == stop_keys[-1]:
            end = None  # the last stop means the full series
    first_part = length.first_part
    if first_part == "first_half" and len(series) == 1 and length.end not in (None, split):
        raise InvalidLength("first half alone already ends at the split")
    if first_part == "second_half" and len(series) == 1:
        # Not a recognised practice on its own (ashtanga-expert): only with the next series.
        raise InvalidLength("the second half needs the next series")
    if first_part == "first_half" and len(series) == 1:
        # First half alone is just "Primary → Navasana".
        return PracticeLength(length.series, split, None)
    return PracticeLength(length.series, end, first_part)


def check_practice(catalog: PracticeCatalog, practice: Practice) -> Practice:
    """The normalised practice, or `InvalidLength` / `InvalidPractice` / `TimezoneUnknown`."""
    if practice.context is PracticeContext.SELF and practice.online:
        raise InvalidPractice("self-practice is never online")
    if practice.duration_min is not None and not 1 <= practice.duration_min <= MAX_DURATION_MIN:
        raise InvalidPractice("duration must be 1-600 minutes")
    if practice.start_time is not None and practice.timezone is None:
        raise TimezoneUnknown("a start time needs a known time zone")
    if practice.slot != 1:
        raise InvalidPractice("one practice per day for now")
    length = check_length(catalog, practice.length) if practice.length is not None else None
    return replace(practice, length=length)


# Static presets (Q6): natural keys, checked against the catalog in tests.
HALF_PRIMARY = PracticeLength(("primary",), "navasana")
FULL_PRIMARY = PracticeLength(("primary",))
STATIC_PRESETS: tuple[tuple[str, PracticeLength], ...] = (
    ("short", SHORT),
    ("half_primary", HALF_PRIMARY),
    ("full_primary", FULL_PRIMARY),
)


@dataclass(frozen=True, slots=True)
class Presets:
    last: Practice | None  # for "same as last time"
    presets: tuple[tuple[str, PracticeLength], ...]  # (kind, length): static, then recent


def derive_presets(catalog: PracticeCatalog, recent: list[Practice]) -> Presets:
    """`recent` newest first. Recent lengths are ranked by use (ties: newest), so a weekly
    Friday Primary doesn't push out the usual length; statics and stale keys are skipped."""
    static = {length for _, length in STATIC_PRESETS}
    counts: Counter[PracticeLength] = Counter()
    first_seen: dict[PracticeLength, int] = {}
    for i, practice in enumerate(recent):
        if practice.length is None:
            continue
        try:
            length = check_length(catalog, practice.length)
        except InvalidLength:
            continue  # the catalog changed since
        if length in static:
            continue
        counts[length] += 1
        first_seen.setdefault(length, i)
    ranked = sorted(counts, key=lambda length: (-counts[length], first_seen[length]))
    recents = tuple(("recent", length) for length in ranked[:RECENT_PRESETS])
    return Presets(last=recent[0] if recent else None, presets=STATIC_PRESETS + recents)
