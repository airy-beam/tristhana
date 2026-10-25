"""SetDayOff / DismissDayOffQuestion on fakes (PR-09)."""

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from tests.fakes import FixedClock, InMemoryStorage
from tristhana.application.policies import Principal
from tristhana.application.rest_days import DismissDayOffQuestion, SetDayOff
from tristhana.domain.accounts import Account, IdentityKey, IdentityProvider, NewAccount
from tristhana.domain.rest_days import DayOff, InvalidDayOff

NOW = datetime(2026, 10, 25, 4, tzinfo=UTC)  # Sunday 09:00 in Almaty
TODAY = date(2026, 10, 25)


async def _me(storage: InMemoryStorage) -> Account:
    a = await storage.accounts.create_with_identity(
        IdentityKey(IdentityProvider.TELEGRAM, "42"), NewAccount(display_name="A", locale="ru")
    )
    return await storage.accounts.set_timezone_if_unset(a.id, "Asia/Almaty")


def _set(storage: InMemoryStorage) -> SetDayOff:
    return SetDayOff(storage.accounts, FixedClock(NOW))


async def test_first_choice_applies_to_all_history() -> None:
    storage = InMemoryStorage()
    me = await _me(storage)
    saved = await _set(storage).execute(Principal(me), [7])
    assert saved.account.day_off == DayOff(frozenset({7}), TODAY)  # no "before": all history
    assert saved.practice_days == frozenset({1, 2, 3, 4, 5, 6})


async def test_two_days_off_leave_five_practice_days() -> None:
    storage = InMemoryStorage()
    me = await _me(storage)
    saved = await _set(storage).execute(Principal(me), [6, 7])
    assert saved.account.day_off.days == frozenset({6, 7})
    assert saved.practice_days == frozenset({1, 2, 3, 4, 5})


async def test_a_later_change_applies_from_local_today() -> None:
    storage = InMemoryStorage()
    me = await _me(storage)
    chosen = replace(me, day_off=DayOff(frozenset({6}), date(2026, 10, 18)))
    saved = await _set(storage).execute(Principal(chosen), [7])
    assert saved.account.day_off == DayOff(frozenset({7}), TODAY, frozenset({6}))


async def test_a_same_day_correction_of_the_first_choice_stays_retroactive() -> None:
    storage = InMemoryStorage()
    me = await _me(storage)
    first = await _set(storage).execute(Principal(me), [6])
    saved = await _set(storage).execute(Principal(first.account), [7])
    assert saved.account.day_off == DayOff(frozenset({7}), TODAY)


async def test_re_tapping_the_current_day_off_writes_nothing() -> None:
    storage = InMemoryStorage()
    me = await _me(storage)
    chosen = (await _set(storage).execute(Principal(me), [6])).account
    writes = storage.accounts.writes
    await _set(storage).execute(Principal(chosen), [6])
    assert storage.accounts.writes == writes


async def test_no_fixed_day_off_means_reminders_every_day() -> None:
    storage = InMemoryStorage()
    me = await _me(storage)
    saved = await _set(storage).execute(Principal(me), [])
    assert saved.account.day_off == DayOff(frozenset(), TODAY)
    assert saved.practice_days == frozenset(range(1, 8))


@pytest.mark.parametrize("days", [[5, 6, 7], [8], [6, 6]])
async def test_invalid_day_off_is_refused_before_any_write(days: list[int]) -> None:
    storage = InMemoryStorage()
    me = await _me(storage)
    writes = storage.accounts.writes
    with pytest.raises(InvalidDayOff):
        await _set(storage).execute(Principal(me), days)
    assert storage.accounts.writes == writes


async def test_dismiss_is_idempotent() -> None:
    storage = InMemoryStorage()
    me = await _me(storage)
    dismiss = DismissDayOffQuestion(storage.accounts)
    await dismiss.execute(Principal(me))
    await dismiss.execute(Principal(me))
    assert storage.accounts.accounts[me.id].day_off_dismissed is True
