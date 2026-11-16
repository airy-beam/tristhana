"""UI-06 stage 2 `GetNextSteps` on a fake (spec §6, §10): the caller's own facts only, in one
read; `today` in the account's zone (Kiritimati vs Honolulu; provisional without one), which
is what the 30-day limit on the invite is measured against; a storage outage surfaces."""

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


def use_case(accounts: InMemoryAccounts) -> GetNextSteps:
    return GetNextSteps(accounts, FixedClock(NOW))


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


@pytest.mark.parametrize(
    ("zone", "offered"),
    [("Pacific/Honolulu", True), ("Pacific/Kiritimati", False)],
)
async def test_the_30_days_are_counted_to_today_in_the_accounts_zone(
    zone: str, offered: bool
) -> None:
    """A link of 17 Oct is 30 days old on 16 Nov and 31 days old on 17 Nov."""
    accounts = InMemoryAccounts()
    me = await person(accounts, "1", timezone=zone)
    accounts.journey[me.id] = JourneyFacts(invite_made_on=date(2026, 10, 17))

    steps = await use_case(accounts).execute(Principal(me))

    assert (steps == (Step(NextStep.INVITE_STUDENT),)) is offered


async def test_without_a_zone_today_is_the_provisional_one() -> None:
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
