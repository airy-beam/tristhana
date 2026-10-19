from datetime import date
from typing import Protocol

from tristhana.domain.moon import MoonDay, MoonLocation


class MoonCalendarRepository(Protocol):
    async def days(self, location: str, start: date, end: date) -> list[MoonDay]: ...

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
