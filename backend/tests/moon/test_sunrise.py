"""ST-10 (ADR-0052): `sunrise_at` is the sunrise the calendar is computed with, for one day."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from tristhana.domain.moon import MoonLocation
from tristhana.moon import (
    MoonRangeError,
    NoSunriseError,
    _ephemeris,  # pyright: ignore[reportPrivateUsage]
    sunrise_at,
)

MYSURU = MoonLocation(12.2958, 76.6394, "Asia/Kolkata")


def test_mysuru_sunrise_on_its_next_full_moon() -> None:
    at = sunrise_at(MYSURU, date(2026, 11, 24))
    assert at.tzinfo is UTC
    local = at.astimezone(ZoneInfo("Asia/Kolkata"))
    assert (local.date(), local.hour, local.minute) == (date(2026, 11, 24), 6, 24)


def test_matches_the_calendars_own_sunrise() -> None:
    day = date(2025, 12, 4)
    with _ephemeris.lock:
        jd = _ephemeris.sunrise_jd(day, MYSURU)
    swe_y, swe_m, swe_d, hours = _ephemeris._lib().revjul(jd, _ephemeris._lib().GREG_CAL)  # pyright: ignore[reportPrivateUsage]
    expected = datetime(swe_y, swe_m, swe_d, tzinfo=UTC).timestamp() + hours * 3600
    assert abs(sunrise_at(MYSURU, day).timestamp() - expected) < 1


def test_polar_night_has_no_sunrise() -> None:
    with pytest.raises(NoSunriseError):
        sunrise_at(MoonLocation(78.22, 15.65, "Arctic/Longyearbyen"), date(2026, 12, 21))


def test_out_of_range() -> None:
    with pytest.raises(MoonRangeError):
        sunrise_at(MYSURU, date(1700, 1, 1))


async def test_the_adapter_gives_none_instead_of_failing_the_card() -> None:
    from tristhana.infrastructure.moon_calc import GeneratorMoonCalculator

    calc = GeneratorMoonCalculator()
    assert (
        await calc.sunrise(MoonLocation(78.22, 15.65, "Arctic/Longyearbyen"), date(2026, 12, 21))
        is None
    )
    assert await calc.sunrise(MYSURU, date(1700, 1, 1)) is None
    assert await calc.sunrise(MYSURU, date(2026, 11, 24)) == sunrise_at(MYSURU, date(2026, 11, 24))
