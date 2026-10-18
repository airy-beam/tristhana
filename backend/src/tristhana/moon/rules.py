"""Pure moon-day rules, ported 1:1 from the owner-verified generator.py. No ephemeris here."""

from collections.abc import Iterable

from tristhana.domain.moon import MoonDay, MoonDayKind

TITHI_DEG = 12.0
PURNIMA = 15
AMAVASYA = 30
MIN_GAP_DAYS = 2


def tithi(moon_lon: float, sun_lon: float) -> int:
    """Lunar day 1..30 from tropical ecliptic longitudes in degrees."""
    return int(((moon_lon - sun_lon) % 360.0) // TITHI_DEG) + 1


def classify(t0: int, t1: int) -> MoonDayKind | None:
    """Moon-day kind of a date, given the tithi at its sunrise (t0) and the next sunrise (t1)."""
    if t0 == PURNIMA:
        return MoonDayKind.PURNIMA
    if t0 == AMAVASYA:
        return MoonDayKind.AMAVASYA

    diff = (t1 - t0) % 30
    if diff > 1:
        skipped = [(t0 + i - 1) % 30 + 1 for i in range(1, diff)]
        if PURNIMA in skipped:
            return MoonDayKind.KSHAYA_PURNIMA
        if AMAVASYA in skipped:
            return MoonDayKind.KSHAYA_AMAVASYA
    return None


def dedup(candidates: Iterable[MoonDay]) -> list[MoonDay]:
    """Drop a candidate less than 2 days after the last accepted one (either phase).

    This keeps the first day when a tithi spans two sunrises (vriddhi).
    """
    accepted: list[MoonDay] = []
    for day in candidates:
        if not accepted or (day.date - accepted[-1].date).days >= MIN_GAP_DAYS:
            accepted.append(day)
    return accepted
