"""ST-05 fakes: trend facts set by the test per account (empty by default)."""

from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from tristhana.domain.check_in_trends import TrendFacts


@dataclass
class InMemoryCheckInTrends:
    by_account: dict[UUID, TrendFacts] = field(default_factory=dict[UUID, TrendFacts])
    calls: list[tuple[UUID, str, date, date]] = field(
        default_factory=list[tuple[UUID, str, date, date]]
    )

    async def facts(
        self, account_id: UUID, moon_location: str, start: date, end: date
    ) -> TrendFacts:
        self.calls.append((account_id, moon_location, start, end))
        return self.by_account.get(account_id, TrendFacts((), ()))
