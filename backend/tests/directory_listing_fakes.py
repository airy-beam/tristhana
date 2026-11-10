"""ID-05 fakes: `InMemoryListings` behaves as the SQL repository is specified to (spec §5):
`save` plans against the stored row and writes nothing when the plan raises; `withdraw` clears
the details and keeps the timestamps; `decide` matches the revision, clears the note and moves
the revision on."""

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Any
from uuid import UUID

from tristhana.application.ports.directory_listing import (
    PAGE,
    Decided,
    RequestCard,
    RequestRow,
    RequestsPage,
    Saved,
)
from tristhana.application.ports.notifications import Recipient
from tristhana.domain.directory_listing import (
    Details,
    Listing,
    ListingStatus,
    Outcome,
    Step,
    may_decide,
)


@dataclass
class InMemoryListings:
    rows: dict[UUID, Listing] = field(default_factory=dict[UUID, Listing])
    names: dict[UUID, str | None] = field(default_factory=dict[UUID, str | None])
    telegram: dict[UUID, Recipient] = field(default_factory=dict[UUID, Recipient])
    checked_by: dict[UUID, UUID] = field(default_factory=dict[UUID, UUID])
    calls: list[str] = field(default_factory=list[str])
    accounts: Any = None  # an `InMemoryAccounts`: names and Telegram ids come from it

    def _name(self, id_: UUID) -> str | None:
        if self.accounts is not None and id_ in self.accounts.accounts:
            return self.accounts.accounts[id_].display_name
        return self.names.get(id_)

    def _recipient(self, id_: UUID) -> Recipient | None:
        if self.accounts is not None:
            for key, owner in self.accounts.identities.items():
                if owner == id_ and key.provider == "telegram":
                    return Recipient(key.provider_user_id, self.accounts.accounts[id_].locale)
        return self.telegram.get(id_)

    async def get(self, me: UUID) -> Listing | None:
        self.calls.append("get")
        return self.rows.get(me)

    async def save(
        self,
        me: UUID,
        details: Details,
        plan: Callable[[Listing | None], Step],
        now: datetime,
    ) -> Saved:
        self.calls.append("save")
        current = self.rows.get(me)
        step = plan(current)
        revision = current.revision + 1 if current else 1
        if step is Step.LEVEL_ONLY and current is not None:
            listing = replace(current, level=details.level, revision=revision)
        else:
            fresh = step in (Step.SEND, Step.RECHECK)
            listing = Listing(
                status=ListingStatus.PENDING,
                name_as_listed=details.name_as_listed,
                region=details.region,
                level=details.level,
                note=details.note,
                revision=revision,
                requested_at=now if fresh or current is None else current.requested_at,
                checked_on=None,
            )
        self.rows[me] = listing
        return Saved(listing, step)

    async def withdraw(self, me: UUID) -> None:
        self.calls.append("withdraw")
        current = self.rows.get(me)
        if current is None:
            return
        self.rows[me] = Listing(
            status=ListingStatus.WITHDRAWN,
            name_as_listed=None,
            region=None,
            level=None,
            note=None,
            revision=current.revision + 1,
            requested_at=current.requested_at,
            checked_on=None,
        )

    async def recipients(self, accounts: frozenset[UUID]) -> tuple[Recipient, ...]:
        self.calls.append("recipients")
        found = (self._recipient(a) for a in sorted(accounts))
        return tuple(r for r in found if r is not None)

    async def requests(self, listed: bool, page: int) -> RequestsPage:
        self.calls.append("requests")
        waiting = [
            (id_, row) for id_, row in self.rows.items() if row.status is ListingStatus.PENDING
        ]
        shown = [(id_, row) for id_, row in self.rows.items() if row.status is ListingStatus.LISTED]
        checks = [row.checked_on for _, row in shown if row.checked_on]
        if listed:
            ordered = sorted(shown, key=lambda p: (p[1].checked_on or date.min, p[0]))
            rows = [
                RequestRow(i, r.name_as_listed or "", r.checked_on or date.min) for i, r in ordered
            ]
        else:
            ordered = sorted(waiting, key=lambda p: (p[1].requested_at, p[0]))
            rows = [
                RequestRow(i, r.name_as_listed or "", r.requested_at.date()) for i, r in ordered
            ]
        return RequestsPage(
            rows=tuple(rows[page * PAGE : (page + 1) * PAGE]),
            waiting=len(waiting),
            listed=len(shown),
            oldest_check=min(checks) if checks else None,
        )

    async def request(self, account_id: UUID) -> RequestCard | None:
        self.calls.append("request")
        row = self.rows.get(account_id)
        if row is None or row.status is ListingStatus.WITHDRAWN:
            return None
        return RequestCard(account_id, self._name(account_id), row)

    async def decide(
        self,
        account_id: UUID,
        revision: int,
        outcome: Outcome,
        checked_on: date,
        by: UUID,
    ) -> Decided | None:
        self.calls.append("decide")
        row = self.rows.get(account_id)
        if row is None or row.revision != revision or not may_decide(row):
            return None
        was_listed = row.status is ListingStatus.LISTED
        listed = outcome is Outcome.LISTED
        self.rows[account_id] = replace(
            row,
            status=ListingStatus.LISTED if listed else ListingStatus.NOT_FOUND,
            note=None,
            revision=row.revision + 1,
            checked_on=checked_on if listed else None,
        )
        self.checked_by[account_id] = by
        return Decided(self._recipient(account_id), row.name_as_listed or "", was_listed)


def always(step: Step) -> Callable[[Listing | None], Step]:
    """A `save` plan for seeding a test: this step, whatever is stored."""

    def plan(_current: Listing | None) -> Step:
        return step

    return plan
