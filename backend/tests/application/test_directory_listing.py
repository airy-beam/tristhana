"""ID-05 use cases on fakes (spec §3, §5, §6; ADR-0042): who is told what, the admin gate,
the check date in the admin's own zone, stale revisions, and the policies."""

import inspect
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest

from tests.directory_listing_fakes import InMemoryListings
from tests.fakes import FakeNotifier, FixedClock
from tests.moon_follow_fakes import FollowingAccounts, person
from tristhana.application import policies
from tristhana.application.directory_listing import (
    DecideListing,
    GetListing,
    GetRequest,
    ListingUnavailable,
    ListingUseCases,
    ListRequests,
    RequestListing,
    WithdrawListing,
)
from tristhana.application.policies import (
    NotFound,
    Principal,
    can_check_listings,
    can_manage_listing,
)
from tristhana.application.ports.notifications import DeliveryResult, DeliveryStatus, Recipient
from tristhana.domain.accounts import Account
from tristhana.domain.directory_listing import (
    DeclaredLevel,
    Details,
    ListingStatus,
    ListingWait,
    Outcome,
    Step,
)

NOW = datetime(2026, 11, 11, 10, 30, tzinfo=UTC)
ANNA = Details("Anna Petrova", "Russia", DeclaredLevel.AUTHORISED_2, "anna.example in the list")


class World:
    def __init__(self, *, with_admin: bool = True) -> None:
        accounts = FollowingAccounts()
        self.teacher = person(accounts, "1001", "Anna")
        self.admin = person(accounts, "9001", "Admin", locale="ru")
        self.other = person(accounts, "1002", "Boris")
        self.clock = FixedClock(NOW)
        self.listings = InMemoryListings()
        self.listings.telegram = {
            self.teacher.id: Recipient("1001", "en"),
            self.admin.id: Recipient("9001", "ru"),
        }
        self.notifier = FakeNotifier()
        admins = frozenset({self.admin.id}) if with_admin else frozenset[UUID]()
        self.use = ListingUseCases(
            get=GetListing(self.listings),
            request=RequestListing(self.listings, self.notifier, self.clock, admins),
            withdraw=WithdrawListing(self.listings),
            requests=ListRequests(self.listings, admins),
            card=GetRequest(self.listings, admins),
            decide=DecideListing(self.listings, self.notifier, self.clock, admins),
            admins=admins,
            clock=self.clock,
        )

    async def send(self, details: Details = ANNA, who: Account | None = None) -> Step:
        saved = await self.use.request.execute(Principal(who or self.teacher), details)
        return saved.step

    async def decide(self, outcome: Outcome, revision: int | None = None) -> object:
        row = self.listings.rows[self.teacher.id]
        return await self.use.decide.execute(
            Principal(self.admin), self.teacher.id, revision or row.revision, outcome
        )


async def test_a_new_request_tells_each_admin_once_and_carries_no_name() -> None:
    w = World()
    assert await w.send() is Step.SEND
    assert w.notifier.listing_requests == [Recipient("9001", "ru")]
    stored = w.listings.rows[w.teacher.id]
    assert (stored.status, stored.note, stored.requested_at) == (
        ListingStatus.PENDING,
        "anna.example in the list",
        NOW,
    )


async def test_editing_a_waiting_request_tells_no_one() -> None:
    w = World()
    await w.send()
    w.clock.instant = NOW + timedelta(minutes=5)
    assert await w.send(replace(ANNA, name_as_listed="Anna Petrova-Smith")) is Step.EDIT
    assert len(w.notifier.listing_requests) == 1
    stored = w.listings.rows[w.teacher.id]
    assert (stored.name_as_listed, stored.revision, stored.requested_at) == (
        "Anna Petrova-Smith",
        2,
        NOW,
    )


async def test_no_admin_configured_is_unavailable_and_writes_nothing() -> None:
    w = World(with_admin=False)
    with pytest.raises(ListingUnavailable):
        await w.send()
    assert w.listings.rows == {}
    assert not w.use.available


async def test_sending_again_within_a_day_is_refused_and_writes_nothing() -> None:
    w = World()
    await w.send()
    await w.decide(Outcome.NOT_FOUND)
    before = w.listings.rows[w.teacher.id]
    w.clock.instant = NOW + timedelta(hours=23)
    with pytest.raises(ListingWait) as caught:
        await w.send()
    assert caught.value.wait == timedelta(hours=1)
    assert w.listings.rows[w.teacher.id] == before
    assert len(w.notifier.listing_requests) == 1


async def test_a_blocked_admin_note_still_saves() -> None:
    w = World()
    w.notifier.listing_outcomes = [DeliveryResult(DeliveryStatus.BLOCKED)]
    assert await w.send() is Step.SEND
    assert w.listings.rows[w.teacher.id].status is ListingStatus.PENDING


async def test_listed_sets_the_admins_local_date_clears_the_note_and_tells_the_teacher() -> None:
    w = World()
    await w.send()
    decided = await w.decide(Outcome.LISTED)
    assert decided is not None
    stored = w.listings.rows[w.teacher.id]
    assert (stored.status, stored.note, stored.checked_on) == (
        ListingStatus.LISTED,
        None,
        date(2026, 11, 11),
    )
    assert w.listings.checked_by[w.teacher.id] == w.admin.id
    assert w.notifier.listing_checks == [
        (Recipient("1001", "en"), Outcome.LISTED, "Anna Petrova", False)
    ]


@pytest.mark.parametrize(
    ("zone", "expected"),
    [("Pacific/Kiritimati", date(2026, 11, 12)), ("Pacific/Honolulu", date(2026, 11, 11))],
)
async def test_the_check_date_is_the_admins_own_day(zone: str, expected: date) -> None:
    w = World()
    await w.send()
    admin = replace(w.admin, timezone=zone)
    row = w.listings.rows[w.teacher.id]
    await w.use.decide.execute(Principal(admin), w.teacher.id, row.revision, Outcome.LISTED)
    assert w.listings.rows[w.teacher.id].checked_on == expected


async def test_not_found_tells_the_teacher_and_keeps_no_note() -> None:
    w = World()
    await w.send()
    await w.decide(Outcome.NOT_FOUND)
    stored = w.listings.rows[w.teacher.id]
    assert (stored.status, stored.note, stored.checked_on) == (ListingStatus.NOT_FOUND, None, None)
    assert w.notifier.listing_checks[0][1:] == (Outcome.NOT_FOUND, "Anna Petrova", False)


async def test_a_stale_revision_decides_nothing_and_tells_no_one() -> None:
    w = World()
    await w.send()
    w.clock.instant = NOW + timedelta(minutes=1)
    await w.send(replace(ANNA, name_as_listed="Somebody Else"))  # an edit after the card
    assert await w.decide(Outcome.LISTED, revision=1) is None
    assert w.listings.rows[w.teacher.id].status is ListingStatus.PENDING
    assert w.notifier.listing_checks == []


async def test_still_listed_moves_the_date_and_tells_no_one() -> None:
    w = World()
    await w.send()
    await w.decide(Outcome.LISTED)
    w.clock.instant = datetime(2027, 5, 2, 10, 0, tzinfo=UTC)
    await w.decide(Outcome.LISTED)
    assert w.listings.rows[w.teacher.id].checked_on == date(2027, 5, 2)
    assert len(w.notifier.listing_checks) == 1


async def test_no_longer_listed_tells_only_the_teacher() -> None:
    w = World()
    await w.send()
    await w.decide(Outcome.LISTED)
    await w.decide(Outcome.NOT_FOUND)
    assert w.listings.rows[w.teacher.id].status is ListingStatus.NOT_FOUND
    assert w.notifier.listing_checks[-1] == (
        Recipient("1001", "en"),
        Outcome.NOT_FOUND,
        "Anna Petrova",
        True,
    )
    assert len(w.notifier.listing_requests) == 1  # admins hear nothing about their own taps


async def test_a_blocked_teacher_note_still_decides() -> None:
    w = World()
    await w.send()
    w.notifier.listing_outcomes = [DeliveryResult(DeliveryStatus.BLOCKED)]
    assert await w.decide(Outcome.LISTED) is not None
    assert w.listings.rows[w.teacher.id].status is ListingStatus.LISTED


async def test_a_level_only_change_stays_listed_and_tells_no_one() -> None:
    w = World()
    await w.send()
    await w.decide(Outcome.LISTED)
    assert await w.send(replace(ANNA, level=DeclaredLevel.CERTIFIED)) is Step.LEVEL_ONLY
    stored = w.listings.rows[w.teacher.id]
    assert (stored.status, stored.level) == (ListingStatus.LISTED, DeclaredLevel.CERTIFIED)
    assert len(w.notifier.listing_requests) == 1


async def test_a_listed_name_change_hides_the_line_and_tells_the_admins() -> None:
    w = World()
    await w.send()
    await w.decide(Outcome.LISTED)
    w.clock.instant = NOW + timedelta(days=2)
    assert await w.send(replace(ANNA, name_as_listed="Anna Smith")) is Step.RECHECK
    stored = w.listings.rows[w.teacher.id]
    assert (stored.status, stored.checked_on) == (ListingStatus.PENDING, None)
    assert len(w.notifier.listing_requests) == 2


async def test_withdraw_clears_the_details_keeps_the_send_time_and_tells_no_one() -> None:
    w = World()
    await w.send()
    await w.use.withdraw.execute(Principal(w.teacher))
    stored = w.listings.rows[w.teacher.id]
    assert (stored.status, stored.name_as_listed, stored.region, stored.level, stored.note) == (
        ListingStatus.WITHDRAWN,
        None,
        None,
        None,
        None,
    )
    assert stored.requested_at == NOW
    assert w.notifier.listing_checks == []
    assert len(w.notifier.listing_requests) == 1
    await w.use.withdraw.execute(Principal(w.teacher))  # idempotent
    await w.use.withdraw.execute(Principal(w.other))  # no row: nothing happens
    assert w.other.id not in w.listings.rows


async def test_get_returns_my_own_row_only() -> None:
    w = World()
    await w.send()
    assert await w.use.get.execute(Principal(w.other)) is None
    mine = await w.use.get.execute(Principal(w.teacher))
    assert mine is not None
    assert mine.name_as_listed == "Anna Petrova"


async def test_a_non_admin_gets_not_found_from_every_review_use_case() -> None:
    w = World()
    await w.send()
    w.listings.calls.clear()
    stranger = Principal(w.other)
    with pytest.raises(NotFound):
        await w.use.requests.execute(stranger, False, 0)
    with pytest.raises(NotFound):
        await w.use.card.execute(stranger, w.teacher.id)
    with pytest.raises(NotFound):
        await w.use.decide.execute(stranger, w.teacher.id, 1, Outcome.LISTED)
    with pytest.raises(NotFound):  # the teacher can't answer their own request
        await w.use.decide.execute(Principal(w.teacher), w.teacher.id, 1, Outcome.LISTED)
    assert w.listings.calls == []  # refused before any read
    assert w.listings.rows[w.teacher.id].status is ListingStatus.PENDING


async def test_an_admin_may_answer_their_own_request() -> None:
    w = World()
    await w.send(who=w.admin)
    row = w.listings.rows[w.admin.id]
    decided = await w.use.decide.execute(
        Principal(w.admin), w.admin.id, row.revision, Outcome.LISTED
    )
    assert decided is not None
    assert w.listings.rows[w.admin.id].status is ListingStatus.LISTED


async def test_the_admin_lists_waiting_and_listed_requests() -> None:
    w = World()
    await w.send()
    page = await w.use.requests.execute(Principal(w.admin), False, 0)
    assert (page.waiting, page.listed, page.oldest_check) == (1, 0, None)
    assert [r.account_id for r in page.rows] == [w.teacher.id]
    await w.decide(Outcome.LISTED)
    page = await w.use.requests.execute(Principal(w.admin), True, 0)
    assert (page.waiting, page.listed, page.oldest_check) == (0, 1, date(2026, 11, 11))
    card = await w.use.card.execute(Principal(w.admin), w.teacher.id)
    assert card is not None
    assert card.listing.status is ListingStatus.LISTED


def test_policies() -> None:
    w = World()
    assert can_manage_listing(w.teacher, w.teacher)
    assert not can_manage_listing(w.other, w.teacher)
    assert can_check_listings(w.admin, frozenset({w.admin.id}))
    assert not can_check_listings(w.teacher, frozenset({w.admin.id}))
    assert not can_check_listings(w.admin, frozenset())
    assert w.use.checks(Principal(w.admin))
    assert not w.use.checks(Principal(w.teacher))


def test_no_other_policy_takes_the_admin_set() -> None:
    """ADR-0042: a platform admin sees no one's practice, students or shalas. Pinned: only
    `can_check_listings` has a parameter that could carry the admin set."""
    takers = [
        name
        for name, fn in inspect.getmembers(policies, inspect.isfunction)
        if fn.__module__ == policies.__name__
        and any(
            "admins" in p.name or "frozenset[UUID]" in str(p.annotation)
            for p in inspect.signature(fn).parameters.values()
        )
    ]
    assert takers == ["can_check_listings"]
