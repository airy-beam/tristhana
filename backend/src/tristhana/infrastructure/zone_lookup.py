"""`ZoneLookup` with tzfpy (MD-04, ADR-0029): offline, no third-party call.

tzfpy's code is MIT; its boundary data (timezone-boundary-builder, from OpenStreetMap) is
ODbL, credited in the README and /privacy. It is imported on the first shared location, not
at startup: the first lookup builds an index (~50 ms, ~15 MB), so it runs off the event loop.
Coordinates are never stored or logged.
"""

import asyncio
from collections.abc import Callable
from functools import cache


@cache
def _get_tz() -> Callable[[float, float], str]:
    import tzfpy

    return tzfpy.get_tz


def _zone_at(lat: float, lon: float) -> str | None:
    return _get_tz()(lon, lat) or None  # tzfpy takes (longitude, latitude)


class TzfpyZoneLookup:
    async def zone_at(self, lat: float, lon: float) -> str | None:
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            return None
        return await asyncio.to_thread(_zone_at, lat, lon)
