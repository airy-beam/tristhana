"""The only module that touches Swiss Ephemeris. `swisseph` is imported lazily."""

from __future__ import annotations

import datetime as dt
import threading
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from tristhana.moon.errors import EphemerisMissingError, MoonError, NoSunriseError
from tristhana.moon.rules import tithi

if TYPE_CHECKING:
    from types import ModuleType

    from tristhana.domain.moon import MoonLocation

BUNDLED_EPHE = Path(__file__).parent / "ephe"

# Swiss Ephemeris keeps global state (open files); serialize access.
lock = threading.Lock()
# The ephemeris path, however, is per thread in this build (thread-local storage in the C
# library): a call from a new thread (asyncio.to_thread workers) must set it again.
_thread = threading.local()

_swe: ModuleType | None = None
_ephe_path: Path = BUNDLED_EPHE


def set_ephemeris_path(path: Path | None) -> None:
    """Use other ephemeris files (None restores the bundled ones). Mainly for tests."""
    global _ephe_path
    with lock:
        _ephe_path = path or BUNDLED_EPHE
        if _swe is not None:
            _swe.set_ephe_path(str(_ephe_path))
            _thread.path = _ephe_path  # other threads re-apply it on their next call


def _lib() -> ModuleType:
    global _swe
    if _swe is None:
        import swisseph

        _swe = swisseph
    if getattr(_thread, "path", None) != _ephe_path:
        _swe.set_ephe_path(str(_ephe_path))
        _thread.path = _ephe_path
    return _swe


def _julian_day(utc: dt.datetime) -> float:
    swe = _lib()
    return swe.julday(utc.year, utc.month, utc.day, utc.hour + utc.minute / 60 + utc.second / 3600)


def local_date_exists(day: dt.date, location: MoonLocation) -> bool:
    """False for dates a zone skipped entirely, e.g. Pacific/Apia on 2011-12-30."""
    tz = ZoneInfo(location.tz)
    midnight = dt.datetime(day.year, day.month, day.day, tzinfo=tz)
    return midnight.astimezone(dt.UTC).astimezone(tz).date() == day


def sunrise_jd(day: dt.date, location: MoonLocation) -> float:
    """Julian day (UT) of sunrise on the local date, cut to whole seconds as generator.py does."""
    swe = _lib()
    tz = ZoneInfo(location.tz)
    local_midnight = dt.datetime(day.year, day.month, day.day, tzinfo=tz)
    jd0 = _julian_day(local_midnight.astimezone(dt.UTC))

    try:
        res, tret = swe.rise_trans(
            jd0, swe.SUN, swe.CALC_RISE, (location.lon, location.lat, 0), atpress=0, attemp=0
        )
    except swe.Error as e:
        raise MoonError(f"sunrise failed on {day.isoformat()}: {e}") from e
    if res != 0:
        raise NoSunriseError(day)

    y, m, d, h = swe.revjul(tret[0], swe.GREG_CAL)
    hh = int(h)
    mm = int((h - hh) * 60)
    ss = int((((h - hh) * 60) - mm) * 60)
    rise = dt.datetime(y, m, d, hh, mm, ss, tzinfo=dt.UTC)
    # Added guard (not in generator.py): near polar day/night the next rise is on a later date.
    if rise.astimezone(tz).date() != day:
        raise NoSunriseError(day)
    return _julian_day(rise)


def tithi_at(jd: float) -> int:
    swe = _lib()
    try:
        sun, sun_flags = swe.calc_ut(jd, swe.SUN)
        moon, moon_flags = swe.calc_ut(jd, swe.MOON)
    except swe.Error as e:
        raise MoonError(f"ephemeris calculation failed: {e}") from e
    # rise_trans silently falls back to Moshier when files are missing; it always runs
    # against the same ephemeris path as these calls, so this check also guards sunrise.
    if not sun_flags & moon_flags & swe.FLG_SWIEPH:
        raise EphemerisMissingError(f"Swiss Ephemeris files not found in {_ephe_path}")
    return tithi(moon[0], sun[0])
