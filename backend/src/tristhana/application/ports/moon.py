from collections.abc import Sequence
from datetime import date
from typing import Protocol

from tristhana.domain.moon import MoonDay, MoonLocation


class MoonCalendarRepository(Protocol):
    async def days(self, location: str, start: date, end: date) -> list[MoonDay]: ...

    async def days_for(
        self, locations: Sequence[str], start: date, end: date
    ) -> dict[str, list[MoonDay]]:
        """Several cities in one statement (MD-04); every asked location is a key."""
        ...

    async def coverage(self) -> dict[tuple[str, int], str]:
        """{(location, year): algo_version} of the stored calendars."""
        ...

    async def replace_year(
        self, location: str, year: int, days: list[MoonDay], algo_version: str
    ) -> None:
        """Atomically store one city-year (job path only)."""
        ...


class MoonCalculator(Protocol):
    """The verified generator port (`tristhana.moon`), off the event loop."""

    version: str  # changes when the algorithm, ephemeris library or tz data change

    async def compute_year(self, location: MoonLocation, year: int) -> list[MoonDay]: ...
