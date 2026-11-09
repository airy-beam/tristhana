"""GM-02 fakes: badge facts set by the test per account (empty by default)."""

from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from tristhana.domain.badges import BadgeFacts


@dataclass
class InMemoryBadgeFacts:
    by_account: dict[UUID, BadgeFacts] = field(default_factory=dict[UUID, BadgeFacts])
    calls: list[tuple[UUID, str, date]] = field(default_factory=list[tuple[UUID, str, date]])

    async def facts(self, account_id: UUID, moon_location: str, today: date) -> BadgeFacts:
        self.calls.append((account_id, moon_location, today))
        return self.by_account.get(account_id, BadgeFacts(logged={}))
