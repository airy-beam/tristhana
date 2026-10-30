"""The tzfpy adapter (MD-04, ADR-0029): offline zone at a point."""

import pytest

from tristhana.infrastructure.zone_lookup import TzfpyZoneLookup


@pytest.mark.parametrize(
    ("lat", "lon", "zone"),
    [
        (43.2389, 76.8897, "Asia/Almaty"),
        (13.7563, 100.5018, "Asia/Bangkok"),
        (15.4909, 73.8278, "Asia/Kolkata"),  # Goa: a half-hour zone
        (51.5074, -0.1278, "Europe/London"),
    ],
)
async def test_zone_at_a_city(lat: float, lon: float, zone: str) -> None:
    assert await TzfpyZoneLookup().zone_at(lat, lon) == zone


async def test_the_open_sea_has_only_a_fixed_offset() -> None:
    zone = await TzfpyZoneLookup().zone_at(0.0, -30.0)

    assert zone is None or zone.startswith("Etc/")  # the use case rejects these


async def test_out_of_range_coordinates() -> None:
    assert await TzfpyZoneLookup().zone_at(91.0, 0.0) is None
