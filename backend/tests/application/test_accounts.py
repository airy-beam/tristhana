from datetime import timedelta

import pytest

from tests.fakes import FixedClock, InMemoryAccounts
from tristhana.application.accounts import EnsureAccount, RecordDeviceTimezone
from tristhana.application.policies import Principal
from tristhana.application.ports.storage import StorageUnavailable
from tristhana.domain.accounts import (
    ExternalProfile,
    IdentityKey,
    IdentityProvider,
    InvalidTimezone,
)

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
