from typing import Protocol


class ZoneLookup(Protocol):
    """The IANA zone at a point, offline (MD-04, ADR-0029). Coordinates are never stored."""

    async def zone_at(self, lat: float, lon: float) -> str | None:
        """None: no zone there (open sea) or the lookup isn't available."""
        ...
