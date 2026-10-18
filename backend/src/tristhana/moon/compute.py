from collections.abc import Iterator
from datetime import date, timedelta

from tristhana.domain.moon import MoonDay, MoonLocation
from tristhana.moon import _ephemeris
from tristhana.moon.errors import MoonRangeError
from tristhana.moon.rules import classify, dedup

# Coverage of the bundled sepl_18/semo_18 files is 1800-2399, minus look-back/next-sunrise margins.
FIRST_SUPPORTED = date(1800, 1, 5)
LAST_SUPPORTED = date(2399, 12, 30)

# Dedup must see the same history as one continuous run. Detections never chain for more
# than 2 consecutive days (a tithi lasts at most ~26.8 h), so 3 days of look-back suffice.
_LOOK_BACK = timedelta(days=3)
_ONE_DAY = timedelta(days=1)


def compute_moon_days(location: MoonLocation, start: date, end: date) -> list[MoonDay]:
    """Moon days observed at `location` between `start` and `end` (inclusive), in date order.

    A 1:1 port of the owner-verified generator.py: the tithi at local sunrise, kshaya
    detection between consecutive sunrises, and a 2-day dedup.
    """
    if start > end or start < FIRST_SUPPORTED or end > LAST_SUPPORTED:
        raise MoonRangeError(f"unsupported range {start}..{end}")

    with _ephemeris.lock:
        candidates: list[MoonDay] = []
        days = _local_days(start - _LOOK_BACK, location)
        day = next(days)
        t0 = _ephemeris.tithi_at(_ephemeris.sunrise_jd(day, location))
        while day <= end:
            next_day = next(days)
            t1 = _ephemeris.tithi_at(_ephemeris.sunrise_jd(next_day, location))
            kind = classify(t0, t1)
            if kind is not None:
                candidates.append(MoonDay(day, kind))
            day, t0 = next_day, t1

    return [d for d in dedup(candidates) if d.date >= start]


def _local_days(first: date, location: MoonLocation) -> Iterator[date]:
    """Consecutive local dates from `first`, skipping dates the zone never had."""
    day = first
    while True:
        if _ephemeris.local_date_exists(day, location):
            yield day
        day += _ONE_DAY
