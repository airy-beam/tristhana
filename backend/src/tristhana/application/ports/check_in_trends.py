"""Port for check-in trends (ST-05): the window's facts, in one statement."""

from datetime import date
from typing import Protocol
from uuid import UUID

from tristhana.domain.check_in_trends import TrendFacts


class CheckInTrendsRepository(Protocol):
    async def facts(
        self, account_id: UUID, moon_location: str, start: date, end: date
    ) -> TrendFacts:
        """One statement over plain columns only: the slot-1 check-ins with at least one scale
        on days whose plain status is `practiced` (ADR-0024; never `sealed_status`, never
        `tags`) from `start` to `end`, and the `moon_location` calendar's days from the day
        before `start` to the day after `end`."""
        ...
