"""Moon days (Purnima/Amavasya) as observed at a location. See notes `07 Moon Days`."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class MoonPhase(StrEnum):
    PURNIMA = "purnima"  # full moon, tithi 15
    AMAVASYA = "amavasya"  # new moon, tithi 30


class MoonDayKind(StrEnum):
    PURNIMA = "purnima"
    AMAVASYA = "amavasya"
    # Kshaya: the tithi starts and ends between two sunrises; observed on the earlier day.
    KSHAYA_PURNIMA = "kshaya_purnima"
    KSHAYA_AMAVASYA = "kshaya_amavasya"

    @property
    def phase(self) -> MoonPhase:
        if self in (MoonDayKind.PURNIMA, MoonDayKind.KSHAYA_PURNIMA):
            return MoonPhase.PURNIMA
        return MoonPhase.AMAVASYA

    @property
    def is_kshaya(self) -> bool:
        return self in (MoonDayKind.KSHAYA_PURNIMA, MoonDayKind.KSHAYA_AMAVASYA)


@dataclass(frozen=True, slots=True)
class MoonLocation:
    """Where moon days are observed: coordinates in degrees and an IANA time zone."""

    lat: float
    lon: float
    tz: str

    def __post_init__(self) -> None:
        if not -90.0 <= self.lat <= 90.0:
            raise ValueError(f"latitude out of range: {self.lat}")
        if not -180.0 <= self.lon <= 180.0:
            raise ValueError(f"longitude out of range: {self.lon}")
        try:
            ZoneInfo(self.tz)
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise ValueError(f"not an IANA time zone: {self.tz!r}") from e
        if self.tz.startswith("Etc/") and self.tz != "Etc/UTC":
            raise ValueError(f"fixed offset zones are not allowed: {self.tz!r}")


@dataclass(frozen=True, slots=True)
class MoonDay:
    date: date
    kind: MoonDayKind


@dataclass(frozen=True, slots=True)
class City:
    """A place whose moon calendar people can follow (MD-03, ADR-0019)."""

    slug: str
    name_en: str
    name_ru: str
    location: MoonLocation

    def name(self, locale: str) -> str:
        return self.name_ru if locale == "ru" else self.name_en


class Cities:
    """The curated city list, in memory (`data/seed/cities.yaml`)."""

    def __init__(self, cities: tuple[City, ...], default: str) -> None:
        self.all = cities
        self._by_slug = {c.slug: c for c in cities}
        if default not in self._by_slug:
            raise ValueError(f"default city {default!r} is not in the list")
        self.default = self._by_slug[default]

    def get(self, slug: str | None) -> City | None:
        return self.default if slug is None else self._by_slug.get(slug)

    def find(self, slug: str | None) -> City | None:
        """The listed city, or None (never the default: `get(None)` is Mysuru)."""
        return None if slug is None else self._by_slug.get(slug)

    def ordered(self, locale: str) -> list[City]:
        """The default first, then by the localised name."""
        rest = sorted((c for c in self.all if c is not self.default), key=lambda c: c.name(locale))
        return [self.default, *rest]


def label_city(home: City | None, zone: str | None) -> City | None:
    """The city that names `zone` in a time label: the home city only in its own zone
    (ADR-0029). After a trip the label goes back to the zone's own name."""
    return home if home is not None and home.location.tz == zone else None


def home_dates(followed: Iterable[MoonDay], home: Iterable[MoonDay]) -> dict[date, date]:
    """MD-04: {followed date: the home city's date} where the same phase falls on another
    day. Paired by phase within ±1 day (kshaya is the same phase); an unpaired or ambiguous
    day is left out, never guessed."""
    by_date: dict[date, list[MoonDay]] = {}
    for h in home:
        by_date.setdefault(h.date, []).append(h)
    paired: dict[date, date] = {}
    for f in followed:
        near = [
            h
            for delta in (-1, 0, 1)
            for h in by_date.get(f.date + timedelta(days=delta), [])
            if h.kind.phase == f.kind.phase
        ]
        if len(near) == 1 and near[0].date != f.date:
            paired[f.date] = near[0].date
    return paired


def calendar_years(today: date) -> range:
    """Years kept in storage: the previous one (for a 12-month heatmap) … current + 2."""
    return range(today.year - 1, today.year + 3)
