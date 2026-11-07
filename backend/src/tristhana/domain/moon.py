"""Moon days (Purnima/Amavasya) as observed at a location. See notes `07 Moon Days`."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from uuid import UUID
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


# `account.moon_location` for "Follow my teacher" (MD-02, ADR-0032) and "Follow my shala"
# (SC-01, ADR-0033). Never a slug: the loader takes kebab-case only, so nothing listed starts
# with "-". NULL = never chosen.
FOLLOW_TEACHER = "-teacher"
FOLLOW_SHALA = "-shala"


class MoonSource(StrEnum):
    CHOSEN = "chosen"
    TEACHER = "teacher"
    SHALA = "shala"
    DEFAULT = "default"


@dataclass(frozen=True, slots=True)
class TeacherMoon:
    """The main teacher (ID-04 `effective_primary`) and their own stored moon value."""

    id: UUID
    name: str | None
    moon_location: str | None


@dataclass(frozen=True, slots=True)
class ShalaMoon:
    """The main shala (SC-01): its moon city (`moon_city`, else its city; maybe since removed
    from the list), whether the person is staff there, and whether their main teacher is.
    `city` is the shala's own city: the fallback when its moon city was removed (Q111)."""

    id: UUID
    name: str
    moon_city: str
    staff: bool
    teacher_on_staff: bool
    city: str | None = None


@dataclass(frozen=True, slots=True)
class MoonFollow:
    """The effective moon city and where it comes from. `teacher` is set for TEACHER, and
    for a chosen follow whose teacher has no city (`moon-source-teacher-none`); `shala` is
    set for SHALA only."""

    city: City
    source: MoonSource
    teacher: TeacherMoon | None
    follow_chosen: bool  # "Follow my teacher"
    shala: ShalaMoon | None = None
    shala_chosen: bool = False  # "Follow my shala"

    @property
    def explicit(self) -> bool:
        """A city, "Follow my teacher" or "Follow my shala" was chosen."""
        return self.source is MoonSource.CHOSEN or self.follow_chosen or self.shala_chosen


def moon_follow(
    own: str | None,
    teaches: bool,
    teacher: TeacherMoon | None,
    shala: ShalaMoon | None,
    cities: Cities,
) -> MoonFollow:
    """MD-02 + SC-01 (Q99, Q108), read time, one hop: a listed own choice wins; "Follow my
    shala" takes the shala's city; "Follow my teacher" the main teacher's own listed city.
    Never chose: staff follow their shala; a student whose main teacher staffs the shala
    follows it; without students (Q76) the teacher's own listed city; then a student's shala;
    otherwise the default. A teacher's NULL, sentinel or removed slug gives nothing (Q77); a
    shala whose moon slug was removed falls back to its own city (Q111), else gives nothing."""
    chosen = cities.find(own)
    if chosen is not None:
        return MoonFollow(chosen, MoonSource.CHOSEN, None, False)
    by_shala = None
    if (
        shala is not None
        and (city := cities.find(shala.moon_city) or cities.find(shala.city)) is not None
    ):
        by_shala = MoonFollow(city, MoonSource.SHALA, None, False, shala, own == FOLLOW_SHALA)
    if own == FOLLOW_SHALA:
        return by_shala or MoonFollow(
            cities.default, MoonSource.DEFAULT, None, False, shala_chosen=True
        )
    follow_chosen = own == FOLLOW_TEACHER
    if (
        not follow_chosen
        and shala is not None
        and by_shala
        and (shala.staff or shala.teacher_on_staff)
    ):
        return by_shala
    if teacher is not None and (follow_chosen or not teaches):
        theirs = cities.find(teacher.moon_location)
        if theirs is not None:
            return MoonFollow(theirs, MoonSource.TEACHER, teacher, follow_chosen)
    if not follow_chosen and by_shala is not None:
        return by_shala
    shown = teacher if follow_chosen else None
    return MoonFollow(cities.default, MoonSource.DEFAULT, shown, follow_chosen)


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
