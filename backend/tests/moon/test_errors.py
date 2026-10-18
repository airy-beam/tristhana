from datetime import date
from pathlib import Path

import pytest

from tristhana.domain.moon import MoonLocation
from tristhana.moon import (
    EphemerisMissingError,
    MoonRangeError,
    NoSunriseError,
    compute_moon_days,
    set_ephemeris_path,
)

MYSURU = MoonLocation(lat=12.2958, lon=76.6394, tz="Asia/Kolkata")


def test_polar_night_raises_no_sunrise() -> None:
    longyearbyen = MoonLocation(lat=78.22, lon=15.65, tz="Arctic/Longyearbyen")

    with pytest.raises(NoSunriseError):
        compute_moon_days(longyearbyen, date(2026, 12, 1), date(2026, 12, 31))


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (date(1700, 1, 1), date(1700, 12, 31)),
        (date(2400, 1, 1), date(2400, 12, 31)),
        (date(2026, 2, 1), date(2026, 1, 1)),
    ],
)
def test_out_of_range_raises(start: date, end: date) -> None:
    with pytest.raises(MoonRangeError):
        compute_moon_days(MYSURU, start, end)


def test_missing_ephemeris_files_raise_instead_of_falling_back(tmp_path: Path) -> None:
    set_ephemeris_path(tmp_path)
    try:
        with pytest.raises(EphemerisMissingError):
            compute_moon_days(MYSURU, date(2026, 1, 1), date(2026, 1, 31))
    finally:
        set_ephemeris_path(None)
