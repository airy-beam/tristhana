"""UI-06 stage 2 `GetNextSteps` on a fake (spec §6, §10): the caller's own facts only, in one
read; the 30-day limit on the invite counted between two UTC dates (the link's is UTC's, so
today's is too, wherever the person is); a storage outage surfaces."""

from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import UUID

import pytest

from tests.fakes import FixedClock, InMemoryAccounts
from tristhana.application.journey import GetNextSteps
from tristhana.application.policies import Principal
from tristhana.application.ports.storage import StorageUnavailable
from tristhana.domain.accounts import Account, IdentityKey, IdentityProvider, NewAccount
from tristhana.domain.journey import JourneyFacts, NextStep, OwnedShala, Step

# 10:30 UTC on 16 Nov: already 17 Nov in Kiritimati (UTC+14), still 16 Nov in Honolulu (UTC-10).
NOW = datetime(2026, 11, 16, 10, 30, tzinfo=UTC)
SHALA = UUID(int=31)


async def person(accounts: InMemoryAccounts, telegram_id: str, **changes: object) -> Account:
    created = await accounts.create_with_identity(
        IdentityKey(IdentityProvider.TELEGRAM, telegram_id), NewAccount("A", "en")
    )
    account = replace(created, **{"timezone": "Asia/Almaty"} | changes)  # type: ignore[arg-type]
    accounts.accounts[account.id] = account
    return account


def use_case(accounts: InMemoryAccounts, now: datetime = NOW) -> GetNextSteps:
    return GetNextSteps(accounts, FixedClock(now))


async def test_a_new_person_has_no_step() -> None:
    accounts = InMemoryAccounts()
    me = await person(accounts, "1")

    assert await use_case(accounts).execute(Principal(me)) == ()


async def test_the_steps_come_from_the_callers_own_facts_in_one_read() -> None:
    accounts = InMemoryAccounts()
    me = await person(accounts, "1")
    other = await person(accounts, "2")
    accounts.journey[me.id] = JourneyFacts(has_days=True, position_set=True)
    accounts.journey[other.id] = JourneyFacts(
        has_days=True, owned=(OwnedShala(SHALA, classes=0, students=0),)
    )

    mine = await use_case(accounts).execute(Principal(me))

    assert mine == (Step(NextStep.REMINDER),)
    assert accounts.journey_reads == [me.id]
    assert await use_case(accounts).execute(Principal(other)) == (
        Step(NextStep.ADD_CLASS, SHALA),
        Step(NextStep.REMINDER),
        Step(NextStep.POSITION),
    )


async def test_the_loaded_account_decides_who_teaches() -> None:
    """`teaches` comes with the principal: the read carries no link count."""
    accounts = InMemoryAccounts()
    me = await person(accounts, "1", teaches=True)
    accounts.journey[me.id] = JourneyFacts(invite_made_on=NOW.date())

    assert await use_case(accounts).execute(Principal(me)) == ()
    assert await use_case(accounts).execute(Principal(replace(me, teaches=False))) == (
        Step(NextStep.INVITE_STUDENT),
    )


@pytest.mark.parametrize("zone", ["Pacific/Honolulu", "Pacific/Kiritimati", None])
@pytest.mark.parametrize(
    ("now", "offered"),
    [
        (datetime(2026, 11, 16, 0, 0, tzinfo=UTC), True),
        (datetime(2026, 11, 16, 23, 59, tzinfo=UTC), True),  # the 30th day, to its last minute
        (datetime(2026, 11, 17, 0, 0, tzinfo=UTC), False),  # the 31st
    ],
)
async def test_the_30_days_are_counted_between_utc_dates(
    zone: str | None, now: datetime, offered: bool
) -> None:
    """The link's date is UTC's, so it is measured against today's UTC date: a link of
    17 Oct is offered through 16 Nov UTC for everyone. Against the account's own date it
    would end up to 14 hours early in Kiritimati and 10 hours late in Honolulu."""
    accounts = InMemoryAccounts()
    me = await person(accounts, "1", timezone=zone)
    accounts.journey[me.id] = JourneyFacts(invite_made_on=date(2026, 10, 17))

    steps = await use_case(accounts, now).execute(Principal(me))

    assert (steps == (Step(NextStep.INVITE_STUDENT),)) is offered


async def test_without_a_zone_the_other_steps_are_offered_as_usual() -> None:
    accounts = InMemoryAccounts()
    me = await person(accounts, "1", timezone=None)
    accounts.journey[me.id] = JourneyFacts(has_days=True, invite_made_on=date(2026, 10, 1))

    assert await use_case(accounts).execute(Principal(me)) == (
        Step(NextStep.REMINDER),
        Step(NextStep.POSITION),
    )


async def test_a_storage_outage_surfaces() -> None:
    accounts = InMemoryAccounts()
    me = await person(accounts, "1")
    accounts.down = True

    with pytest.raises(StorageUnavailable):
        await use_case(accounts).execute(Principal(me))
