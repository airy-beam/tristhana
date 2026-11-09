"""Port for badges (GM-02, ADR-0041): the facts they are read from, in one statement."""

from datetime import date
from typing import Protocol
from uuid import UUID

from tristhana.domain.badges import BadgeFacts


class BadgeFactsRepository(Protocol):
    async def facts(self, account_id: UUID, moon_location: str, today: date) -> BadgeFacts:
        """One statement over plain columns only: the logged dates with their plain status
        (never `sealed_status`), slot-1 Led / self-practice dates and start times, rest-period
        date ranges (never their sealed kind), the `moon_location` calendar's dates from the
        first logged date to `today`, the GM-01 ledger thresholds, and the position and
        item events, oldest first."""
        ...
