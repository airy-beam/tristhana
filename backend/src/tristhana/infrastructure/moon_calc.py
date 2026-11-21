"""`MoonCalculator` over the verified generator port (`tristhana.moon`), in a thread so a
tick doesn't block webhook requests (one city-year per hop: 0.04 to 0.26 s measured)."""

import asyncio
from datetime import date, datetime

from tristhana.domain.moon import MoonDay, MoonLocation
from tristhana.moon import ALGO_VERSION, MoonError, compute_moon_days, sunrise_at


class GeneratorMoonCalculator:
    version = ALGO_VERSION

    async def compute_year(self, location: MoonLocation, year: int) -> list[MoonDay]:
        return await asyncio.to_thread(
            compute_moon_days, location, date(year, 1, 1), date(year, 12, 31)
        )

    async def sunrise(self, location: MoonLocation, day: date) -> datetime | None:
        """ST-10 (ADR-0052): one sunrise for a moon card; None rather than a failed card."""
        try:
            return await asyncio.to_thread(sunrise_at, location, day)
        except MoonError:
            return None
