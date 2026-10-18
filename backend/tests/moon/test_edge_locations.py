"""Locations outside the 10 verified cities: no golden data, but they must behave sanely."""

from datetime import date
from itertools import pairwise

import pytest

from tristhana.domain.moon import MoonLocation
from tristhana.moon import compute_moon_days

EDGE_LOCATIONS = {
    "Sydney (southern hemisphere, DST)": MoonLocation(-33.87, 151.21, "Australia/Sydney"),
    "Santiago (DST switch at midnight)": MoonLocation(-33.45, -70.67, "America/Santiago"),
    "Kathmandu (UTC+5:45)": MoonLocation(27.72, 85.32, "Asia/Kathmandu"),
    "Chatham (UTC+12:45)": MoonLocation(-43.95, -176.56, "Pacific/Chatham"),
    "Kiritimati (UTC+14)": MoonLocation(1.87, -157.36, "Pacific/Kiritimati"),
    "Honolulu (lon near -180 side)": MoonLocation(21.31, -157.86, "Pacific/Honolulu"),
}


@pytest.mark.parametrize("location", EDGE_LOCATIONS.values(), ids=EDGE_LOCATIONS.keys())
def test_edge_location_has_a_moon_day_about_every_fortnight(location: MoonLocation) -> None:
    days = compute_moon_days(location, date(2026, 1, 1), date(2026, 12, 31))

    assert 24 <= len(days) <= 26
    gaps = [(b.date - a.date).days for a, b in pairwise(days)]
    assert all(13 <= g <= 17 for g in gaps), gaps


def test_skipped_local_date_is_not_a_missing_sunrise() -> None:
    # Samoa crossed the date line: 2011-12-30 never happened in Pacific/Apia.
    apia = MoonLocation(-13.83, -171.76, "Pacific/Apia")

    days = compute_moon_days(apia, date(2011, 12, 1), date(2012, 1, 31))

    assert len(days) == 4
    assert date(2011, 12, 30) not in {d.date for d in days}
