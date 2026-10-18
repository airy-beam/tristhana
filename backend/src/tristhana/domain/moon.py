"""Moon days (Purnima/Amavasya) as observed at a location. See notes `07 Moon Days`."""

from dataclasses import dataclass
from datetime import date
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
