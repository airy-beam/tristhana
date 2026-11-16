from dataclasses import replace
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest

from tests.fakes import FixedClock, InMemoryAccounts
from tristhana.application.accounts import (
    EnsureAccount,
    MarkWelcomed,
    RecordDeviceTimezone,
    Welcome,
)
from tristhana.application.policies import Principal
from tristhana.application.ports.storage import StorageUnavailable
from tristhana.domain.accounts import (
    Account,
    ExternalProfile,
    IdentityKey,
    IdentityProvider,
    InvalidTimezone,
)
from tristhana.domain.moon import ShalaMoon, TeacherMoon

KEY = IdentityKey(IdentityProvider.TELEGRAM, "42")


def _profile(name: str = "Ash", language_code: str | None = "en") -> ExternalProfile:
    return ExternalProfile(KEY, display_name=name, language_code=language_code)


@pytest.fixture
def repo() -> InMemoryAccounts:
    return InMemoryAccounts()


@pytest.fixture
def ensure(repo: InMemoryAccounts) -> EnsureAccount:
    return EnsureAccount(repo, repo.clock)


async def test_first_contact_creates_the_account(
    ensure: EnsureAccount, repo: InMemoryAccounts
) -> None:
    account = await ensure.execute(_profile("Аня", "ru-RU"))

    assert (account.display_name, account.locale, account.timezone) == ("Аня", "ru", None)
    assert repo.identities == {KEY: account.id}


async def test_repeat_contact_does_not_write(ensure: EnsureAccount, repo: InMemoryAccounts) -> None:
    first = await ensure.execute(_profile())
    writes = repo.writes

    again = await ensure.execute(_profile())

    assert again == first
    assert repo.writes == writes


async def test_changed_name_is_refreshed(ensure: EnsureAccount, repo: InMemoryAccounts) -> None:
    first = await ensure.execute(_profile("Ash"))

    renamed = await ensure.execute(_profile("Ashley"))

    assert renamed.id == first.id
    assert renamed.display_name == "Ashley"


async def test_stale_last_seen_is_written_once(
    ensure: EnsureAccount, repo: InMemoryAccounts
) -> None:
    await ensure.execute(_profile())
    clock: FixedClock = repo.clock
    clock.instant += timedelta(hours=25)
    writes = repo.writes

    touched = await ensure.execute(_profile())
    await ensure.execute(_profile())

    assert touched.last_seen_at == clock.instant
    assert repo.writes == writes + 1


async def test_concurrent_first_contact_returns_the_winner(
    ensure: EnsureAccount, repo: InMemoryAccounts
) -> None:
    repo.steal_next_create = True

    account = await ensure.execute(_profile("Loser"))

    assert account.display_name == "Winner"
    assert len(repo.accounts) == 1


async def test_storage_failure_propagates(ensure: EnsureAccount, repo: InMemoryAccounts) -> None:
    repo.down = True

    with pytest.raises(StorageUnavailable):
        await ensure.execute(_profile())


async def test_device_timezone_is_set_only_when_unset(
    ensure: EnsureAccount, repo: InMemoryAccounts
) -> None:
    record = RecordDeviceTimezone(repo)
    account = await ensure.execute(_profile())

    first = await record.execute(Principal(account), "Asia/Almaty")
    second = await record.execute(Principal(first), "Europe/Moscow")

    assert first.timezone == "Asia/Almaty"
    assert second.timezone == "Asia/Almaty"


async def test_device_timezone_rejects_fixed_offsets(
    ensure: EnsureAccount, repo: InMemoryAccounts
) -> None:
    account = await ensure.execute(_profile())

    with pytest.raises(InvalidTimezone):
        await RecordDeviceTimezone(repo).execute(Principal(account), "Etc/GMT-5")


async def test_device_reporting_utc_leaves_the_zone_unset(
    ensure: EnsureAccount, repo: InMemoryAccounts
) -> None:
    account = await ensure.execute(_profile())

    result = await RecordDeviceTimezone(repo).execute(Principal(account), "UTC")

    assert result.timezone is None


# UI-06 (spec §3): the front door is shown once


@pytest.fixture
def welcome(repo: InMemoryAccounts) -> MarkWelcomed:
    return MarkWelcomed(repo, repo.clock)


async def _new(ensure: EnsureAccount) -> Account:
    return await ensure.execute(_profile())


async def test_the_first_call_marks_the_account_and_says_so(
    ensure: EnsureAccount, welcome: MarkWelcomed, repo: InMemoryAccounts
) -> None:
    account = await _new(ensure)
    assert account.welcomed is False

    result = await welcome.execute(Principal(account))

    assert result == Welcome(first=True, active=False)
    assert repo.accounts[account.id].welcomed is True
    assert repo.welcomed_at[account.id] == repo.clock.now()


async def test_the_second_call_is_not_the_first(
    ensure: EnsureAccount, welcome: MarkWelcomed, repo: InMemoryAccounts
) -> None:
    """A double `/start`: both requests loaded the account before either wrote."""
    stale = Principal(await _new(ensure))
    at = repo.clock.now()

    first = await welcome.execute(stale)
    repo.clock.instant = at + timedelta(minutes=1)
    second = await welcome.execute(stale)

    assert (first.first, second.first) == (True, False)
    assert repo.welcomed_at[stale.account.id] == at  # set once


async def test_an_account_already_welcomed_costs_no_write(
    ensure: EnsureAccount, welcome: MarkWelcomed, repo: InMemoryAccounts
) -> None:
    account = await _new(ensure)
    await welcome.execute(Principal(account))
    writes = repo.writes

    again = await welcome.execute(Principal(repo.accounts[account.id]))

    assert again.first is False
    assert repo.writes == writes


async def test_active_by_a_logged_day(
    ensure: EnsureAccount, welcome: MarkWelcomed, repo: InMemoryAccounts
) -> None:
    account = await _new(ensure)
    repo.has_days = lambda id: id == account.id

    assert await welcome.execute(Principal(account)) == Welcome(first=True, active=True)


@pytest.mark.parametrize(
    "activity",
    [
        {"main_teacher": TeacherMoon(UUID(int=7), "Anna", None)},
        {"teaches": True},
        {"shala": ShalaMoon(UUID(int=8), "Ashtanga Almaty", "almaty", False, False)},
        {"shala": ShalaMoon(UUID(int=8), "Ashtanga Almaty", "almaty", True, False)},
    ],
    ids=["link", "student", "shala", "staff"],
)
async def test_active_by_what_the_account_shows(
    ensure: EnsureAccount, welcome: MarkWelcomed, repo: InMemoryAccounts, activity: dict[str, Any]
) -> None:
    account = replace(await _new(ensure), **activity)
    repo.accounts[account.id] = account

    assert await welcome.execute(Principal(account)) == Welcome(first=True, active=True)


async def test_only_the_first_call_calls_for_the_front_door(
    ensure: EnsureAccount, welcome: MarkWelcomed
) -> None:
    stale = Principal(await _new(ensure))

    first = await welcome.execute(stale)
    second = await welcome.execute(stale)

    assert first.front_door is True
    assert second.front_door is False  # never twice, whatever the activity


async def test_an_active_person_never_gets_the_front_door(
    ensure: EnsureAccount, welcome: MarkWelcomed, repo: InMemoryAccounts
) -> None:
    account = await _new(ensure)
    repo.has_days = lambda _: True

    assert (await welcome.execute(Principal(account))).front_door is False


async def test_mark_welcomed_surfaces_a_storage_outage(
    ensure: EnsureAccount, welcome: MarkWelcomed, repo: InMemoryAccounts
) -> None:
    account = await _new(ensure)
    repo.down = True

    with pytest.raises(StorageUnavailable):
        await welcome.execute(Principal(account))
