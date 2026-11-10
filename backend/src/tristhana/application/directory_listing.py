"""The directory listing (ID-05, ADR-0042): a teacher asks, a platform admin looks the name up
in the public directory by hand and answers. The bot and the API share these use cases.

Admins come from settings at wiring; nothing here reads the environment. A non-admin gets
`NotFound` from the review use cases, never `NotAllowed`, so the review can't be probed. Notes
are direct and best effort: `/admin` is the record, so a lost note loses nothing. Logs carry
the account id and the outcome only.
"""

import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID

from tristhana.application.policies import (
    NotAllowed,
    NotFound,
    Principal,
    can_check_listings,
    can_manage_listing,
)
from tristhana.application.ports.directory_listing import (
    Decided,
    ListingRepository,
    RequestCard,
    RequestsPage,
    Saved,
)
from tristhana.application.ports.notifications import Notifier
from tristhana.application.ports.storage import Clock, StorageUnavailable
from tristhana.application.settings import caller_today
from tristhana.domain.directory_listing import (
    Details,
    Listing,
    Outcome,
    Step,
    next_state,
)

log = logging.getLogger(__name__)


class ListingUnavailable(Exception):
    """No admin is configured: nobody could answer a request."""


class GetListing:
    def __init__(self, listings: ListingRepository) -> None:
        self._listings = listings

    async def execute(self, principal: Principal) -> Listing | None:
        account = principal.account
        if not can_manage_listing(account, account):
            raise NotAllowed
        return await self._listings.get(account.id)


class RequestListing:
    def __init__(
        self,
        listings: ListingRepository,
        notifier: Notifier,
        clock: Clock,
        admins: frozenset[UUID],
    ) -> None:
        self._listings = listings
        self._notifier = notifier
        self._clock = clock
        self._admins = admins

    async def execute(self, principal: Principal, details: Details) -> Saved:
        """Send or edit. Admins get one silent note for a new request or a listed name that
        changed; an edit of a waiting request or of the level tells no one. Raises
        `ListingWait`, `ListingUnavailable`."""
        account = principal.account
        if not can_manage_listing(account, account):
            raise NotAllowed
        if not self._admins:
            raise ListingUnavailable
        now = self._clock.now()
        saved = await self._listings.save(
            account.id, details, lambda current: next_state(current, details, now), now
        )
        if saved.step in (Step.SEND, Step.RECHECK):
            log.info("directory listing requested by %s", account.id)
            try:  # the row is saved and `/admin` is the record: a lost note loses nothing
                admins = await self._listings.recipients(self._admins)
            except StorageUnavailable:
                admins = ()
            await asyncio.gather(*(self._notifier.tell_listing_requested(a) for a in admins))
        return saved


class WithdrawListing:
    def __init__(self, listings: ListingRepository) -> None:
        self._listings = listings

    async def execute(self, principal: Principal) -> None:
        """The line goes at once and no one is told. Idempotent."""
        account = principal.account
        if not can_manage_listing(account, account):
            raise NotAllowed
        await self._listings.withdraw(account.id)


class ListRequests:
    def __init__(self, listings: ListingRepository, admins: frozenset[UUID]) -> None:
        self._listings = listings
        self._admins = admins

    async def execute(self, principal: Principal, listed: bool, page: int) -> RequestsPage:
        if not can_check_listings(principal.account, self._admins):
            raise NotFound
        return await self._listings.requests(listed, page)


class GetRequest:
    def __init__(self, listings: ListingRepository, admins: frozenset[UUID]) -> None:
        self._listings = listings
        self._admins = admins

    async def execute(self, principal: Principal, account_id: UUID) -> RequestCard | None:
        if not can_check_listings(principal.account, self._admins):
            raise NotFound
        return await self._listings.request(account_id)


class DecideListing:
    def __init__(
        self,
        listings: ListingRepository,
        notifier: Notifier,
        clock: Clock,
        admins: frozenset[UUID],
    ) -> None:
        self._listings = listings
        self._notifier = notifier
        self._clock = clock
        self._admins = admins

    async def execute(
        self, principal: Principal, account_id: UUID, revision: int, outcome: Outcome
    ) -> Decided | None:
        """The check date is the admin's local date. None: the request changed since the
        card. The teacher gets one silent note, except for "still listed" (nothing changed
        for them); students are never told anything."""
        admin = principal.account
        if not can_check_listings(admin, self._admins):
            raise NotFound
        today = caller_today(principal, self._clock)
        decided = await self._listings.decide(account_id, revision, outcome, today, admin.id)
        if decided is None:
            return None
        log.info("directory listing of %s: %s", account_id, outcome.value)
        still_listed = decided.was_listed and outcome is Outcome.LISTED
        if decided.teacher is not None and not still_listed:
            await self._notifier.tell_listing_checked(
                decided.teacher, outcome, decided.name_as_listed, decided.was_listed
            )
        return decided


@dataclass(frozen=True, slots=True)
class ListingUseCases:
    get: GetListing
    request: RequestListing
    withdraw: WithdrawListing
    requests: ListRequests
    card: GetRequest
    decide: DecideListing
    admins: frozenset[UUID]
    clock: Clock

    @property
    def available(self) -> bool:
        """False: no admin is configured, so the feature is hidden."""
        return bool(self.admins)

    def checks(self, principal: Principal) -> bool:
        return can_check_listings(principal.account, self.admins)
