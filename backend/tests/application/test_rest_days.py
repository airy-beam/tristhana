"""SetDayOff / DismissDayOffQuestion on fakes (PR-09)."""

from dataclasses import replace
from datetime import UTC, date, datetime, time

import pytest

from tests.fakes import FixedClock, InMemoryStorage
from tristhana.application.policies import Principal
from tristhana.application.ports.notifications import ReminderPatch
from tristhana.application.rest_days import DismissDayOffQuestion, SetDayOff
from tristhana.domain.accounts import Account, IdentityKey, IdentityProvider, NewAccount
from tristhana.domain.notifications import defaults_for
from tristhana.domain.rest_days import DayOff, InvalidDayOff

NOW = datetime(2026, 10, 25, 4, tzinfo=UTC)  # Sunday 09:00 in Almaty
TODAY = date(2026, 10, 25)


async def _me(storage: InMemoryStorage) -> Account:
    a = await storage.accounts.create_with_identity(
        IdentityKey(IdentityProvider.TELEGRAM, "42"), NewAccount(display_name="A", locale="ru")
    )
    return await storage.accounts.set_timezone_if_unset(a.id, "Asia/Almaty")


def _set(storage: InMemoryStorage) -> SetDayOff:
    return SetDayOff(storage.accounts, storage.notifications, FixedClock(NOW))


async def test_first_choice_applies_to_all_history() -> None:
    storage = InMemoryStorage()
    me = await _me(storage)
    saved = await _set(storage).execute(Principal(me), [7])
    assert saved.account.day_off == DayOff(frozenset({7}), TODAY)  # no "before": all history
    assert saved.settings.practice.days == frozenset({1, 2, 3, 4, 5, 6})
    assert saved.reminders_reset is False  # nothing was stored


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


async def test_custom_reminder_days_are_reset_with_a_note() -> None:
    storage = InMemoryStorage()
    me = await _me(storage)
    custom = frozenset({1, 3, 5})
    await storage.notifications.patch_practice(
        me.id, ReminderPatch(on=True, at=time(10), days=custom), defaults_for(None)
    )
    saved = await _set(storage).execute(Principal(me), [7])
    assert saved.reminders_reset is True
    assert saved.settings.practice.days == frozenset({1, 2, 3, 4, 5, 6})
    assert saved.settings.practice.on is True


async def test_re_tapping_the_current_day_off_keeps_custom_reminder_days() -> None:
    storage = InMemoryStorage()
    me = await _me(storage)
    chosen = (await _set(storage).execute(Principal(me), [6])).account
    custom = frozenset({1, 3, 5})
    await storage.notifications.patch_practice(
        me.id, ReminderPatch(days=custom), defaults_for(frozenset({6}))
    )
    saved = await _set(storage).execute(Principal(chosen), [6])
    assert saved.reminders_reset is False
    assert saved.settings.practice.days == custom


async def test_stored_days_equal_to_the_new_ones_need_no_note() -> None:
    storage = InMemoryStorage()
    me = await _me(storage)
    await storage.notifications.patch_practice(
        me.id, ReminderPatch(days=frozenset({1, 2, 3, 4, 5, 7})), defaults_for(None)
    )
    assert (await _set(storage).execute(Principal(me), [6])).reminders_reset is False


async def test_no_fixed_day_off_means_reminders_every_day() -> None:
    storage = InMemoryStorage()
    me = await _me(storage)
    saved = await _set(storage).execute(Principal(me), [])
    assert saved.account.day_off == DayOff(frozenset(), TODAY)
    assert saved.settings.practice.days == frozenset(range(1, 8))


@pytest.mark.parametrize("days", [[6, 7], [8], [6, 6]])
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
