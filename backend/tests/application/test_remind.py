"""PR-10 use cases and the tick's practice reminder, on in-memory fakes."""

from dataclasses import replace
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest

from tests.fakes import (
    FakeCalculator,
    FakeNotifier,
    FixedClock,
    InMemoryAccounts,
    InMemoryDays,
    InMemoryMoon,
    InMemoryNotifications,
    InMemoryPractices,
)
from tristhana.application.policies import Principal
from tristhana.application.ports.notifications import (
    DeliveryResult,
    DeliveryStatus,
    ReminderPatch,
)
from tristhana.application.remind import (
    AnswerPracticeOffer,
    QuickLogSameAsLast,
    UpdatePracticeReminder,
)
from tristhana.application.tick import RunTick
from tristhana.domain.accounts import Account, IdentityKey, IdentityProvider, NewAccount
from tristhana.domain.days import DateInFuture, DayLog, DayStatus
from tristhana.domain.milestones import NO_COUNTS
from tristhana.domain.moon import MoonDay, MoonDayKind, calendar_years
from tristhana.domain.notifications import (
    DEFAULTS,
    UNANSWERED_LIMIT,
    InvalidSettings,
    practice_key,
    send_instant,
)
from tristhana.domain.practice import Practice, PracticeContext, PracticeLength
from tristhana.domain.rest_days import DayOff
from tristhana.infrastructure.seed.cities_yaml import load_cities

CITIES = load_cities(Path(__file__).resolve().parents[3] / "data" / "seed" / "cities.yaml")
ZONE = "Asia/Almaty"
MON = date(2026, 10, 19)
MORNING = send_instant(MON, time(10), ZONE)
BUDGET = timedelta(seconds=40)
MYSORE = Practice(PracticeContext.MYSORE, length=PracticeLength(("primary",), "navasana"))
LED = Practice(PracticeContext.LED, length=PracticeLength(("primary",)))


@pytest.fixture
def accounts() -> InMemoryAccounts:
    return InMemoryAccounts()


@pytest.fixture
def days() -> InMemoryDays:
    return InMemoryDays()


@pytest.fixture
def notifications(accounts: InMemoryAccounts, days: InMemoryDays) -> InMemoryNotifications:
    return InMemoryNotifications(accounts, days=days)


@pytest.fixture
def moon() -> InMemoryMoon:
    m = InMemoryMoon()
    for city in CITIES.all:
        for year in calendar_years(MORNING.date()):
            m.ledger[(city.slug, year)] = "test-1"
    return m


async def _account(accounts: InMemoryAccounts, zone: str | None = ZONE) -> Account:
    created = await accounts.create_with_identity(
        IdentityKey(IdentityProvider.TELEGRAM, "42"), NewAccount(display_name="A", locale="ru")
    )
    return await accounts.set_timezone_if_unset(created.id, zone) if zone else created


def _practiced(days: InMemoryDays, me: Account, when: date, practice: Practice) -> None:
    days.rows[(me.id, when)] = (DayLog(when, DayStatus.PRACTICED), ZONE)
    days.practice_rows[(me.id, when)] = practice


def _quick(days: InMemoryDays, now: datetime = MORNING) -> QuickLogSameAsLast:
    return QuickLogSameAsLast(days, InMemoryPractices(days), FixedClock(now), NO_COUNTS)


# QuickLogSameAsLast


async def test_quick_log_copies_the_newest_non_led_practice(
    accounts: InMemoryAccounts, days: InMemoryDays
) -> None:
    me = await _account(accounts)
    _practiced(days, me, MON - timedelta(days=4), MYSORE)  # Thursday Mysore
    _practiced(days, me, MON - timedelta(days=1), LED)  # Sunday led class

    logged = await _quick(days).execute(Principal(me), MON)

    assert not logged.already
    assert logged.day is not None
    assert logged.day.status is DayStatus.PRACTICED
    assert logged.day.practices[0].context is PracticeContext.MYSORE
    assert logged.copied_from == MON - timedelta(days=4)
    assert days.practice_rows[(me.id, MON)].context is PracticeContext.MYSORE


async def test_quick_log_falls_back_to_a_led_practice(
    accounts: InMemoryAccounts, days: InMemoryDays
) -> None:
    me = await _account(accounts)
    _practiced(days, me, MON - timedelta(days=1), LED)

    logged = await _quick(days).execute(Principal(me), MON)

    assert logged.copied_from == MON - timedelta(days=1)


async def test_quick_log_without_history_still_logs_the_day(
    accounts: InMemoryAccounts, days: InMemoryDays
) -> None:
    me = await _account(accounts)

    logged = await _quick(days).execute(Principal(me), MON)

    assert logged.day == DayLog(MON, DayStatus.PRACTICED)
    assert logged.copied_from is None


@pytest.mark.parametrize("status", [DayStatus.LADIES, DayStatus.REST, DayStatus.PRACTICED])
async def test_quick_log_never_overwrites_a_logged_day(
    accounts: InMemoryAccounts, days: InMemoryDays, status: DayStatus
) -> None:
    me = await _account(accounts)
    _practiced(days, me, MON - timedelta(days=2), MYSORE)
    days.rows[(me.id, MON)] = (DayLog(MON, status), ZONE)

    logged = await _quick(days).execute(Principal(me), MON)

    assert logged.already
    assert logged.day is not None
    assert logged.day.status is status
    assert days.rows[(me.id, MON)][0].status is status
    assert (me.id, MON) not in days.practice_rows


async def test_quick_log_refuses_a_future_day(
    accounts: InMemoryAccounts, days: InMemoryDays
) -> None:
    me = await _account(accounts)

    with pytest.raises(DateInFuture):
        await _quick(days).execute(Principal(me), MON + timedelta(days=2))


# Settings and the offer


@pytest.mark.parametrize(("local", "expected"), [(time(7, 30), time(10)), (time(15), time(20))])
async def test_offer_yes_picks_the_time_from_when_it_was_tapped(
    accounts: InMemoryAccounts, notifications: InMemoryNotifications, local: time, expected: time
) -> None:
    me = await _account(accounts)
    tapped = send_instant(MON, local, ZONE)

    saved = await AnswerPracticeOffer(notifications, FixedClock(tapped)).execute(
        Principal(me), yes=True
    )

    assert (saved.practice.on, saved.practice.at) == (True, expected)
    assert saved.practice.days == DEFAULTS.practice.days


async def test_offer_no_records_the_choice(
    accounts: InMemoryAccounts, notifications: InMemoryNotifications
) -> None:
    me = await _account(accounts)

    saved = await AnswerPracticeOffer(notifications, FixedClock(MORNING)).execute(
        Principal(me), yes=False
    )

    assert saved.practice.on is False


async def test_update_patches_one_field_and_validates(
    accounts: InMemoryAccounts, notifications: InMemoryNotifications
) -> None:
    me = await _account(accounts)
    update = UpdatePracticeReminder(notifications)

    await update.execute(Principal(me), ReminderPatch(on=True))
    saved = await update.execute(Principal(me), ReminderPatch(at=time(9)))

    assert (saved.practice.on, saved.practice.at) == (True, time(9))
    assert saved.practice.days == {1, 2, 3, 4, 5, 7}  # the practice days (Sat off by default)
    for bad in (ReminderPatch(at=time(9, 5)), ReminderPatch(on=True, at=time(23))):
        with pytest.raises(InvalidSettings):
            await update.execute(Principal(me), bad)


# The tick


def _tick(
    notifications: InMemoryNotifications,
    moon: InMemoryMoon,
    notifier: FakeNotifier,
    now: datetime = MORNING,
) -> RunTick:
    return RunTick(FixedClock(now), CITIES, moon, FakeCalculator(), notifications, notifier)


async def _opted_in(
    accounts: InMemoryAccounts, notifications: InMemoryNotifications, **kw: object
) -> Account:
    me = await _account(accounts)
    practice = replace(DEFAULTS.practice, on=True, **kw)
    off_moon = replace(DEFAULTS.moon, offsets=frozenset[int]())
    await notifications.save(me.id, replace(DEFAULTS, moon=off_moon, practice=practice))
    return me


async def test_tick_sends_the_practice_reminder(
    accounts: InMemoryAccounts, notifications: InMemoryNotifications, moon: InMemoryMoon
) -> None:
    await _opted_in(accounts, notifications)
    notifier = FakeNotifier()

    result = await _tick(notifications, moon, notifier).execute(BUDGET)
    again = await _tick(notifications, moon, notifier).execute(BUDGET)

    assert (result.sent, again.sent) == (1, 0)
    [(recipient, reminder)] = notifier.practice
    assert (recipient.telegram_id, reminder.day, reminder.pause) == ("42", MON, False)


async def test_tick_skips_a_day_already_logged(
    accounts: InMemoryAccounts,
    notifications: InMemoryNotifications,
    moon: InMemoryMoon,
    days: InMemoryDays,
) -> None:
    me = await _opted_in(accounts, notifications)
    days.rows[(me.id, MON)] = (DayLog(MON, DayStatus.REST), ZONE)
    notifier = FakeNotifier()

    result = await _tick(notifications, moon, notifier).execute(BUDGET)

    assert result.sent == 0


async def test_tick_skips_a_moon_day_of_the_followed_calendar(
    accounts: InMemoryAccounts, notifications: InMemoryNotifications, moon: InMemoryMoon
) -> None:
    await _opted_in(accounts, notifications)
    moon.days_by_location["mysuru"] = [MoonDay(MON, MoonDayKind.AMAVASYA)]
    notifier = FakeNotifier()

    assert (await _tick(notifications, moon, notifier).execute(BUDGET)).sent == 0


async def test_moon_goes_first_under_one_cap(
    accounts: InMemoryAccounts, notifications: InMemoryNotifications, moon: InMemoryMoon
) -> None:
    me = await _account(accounts)
    # Moon reminder (day before) and practice reminder at the same hour, cap 1.
    moon.days_by_location["mysuru"] = [MoonDay(MON + timedelta(days=1), MoonDayKind.PURNIMA)]
    both = replace(
        DEFAULTS,
        moon=replace(DEFAULTS.moon, at=time(10)),
        practice=replace(DEFAULTS.practice, on=True),
        daily_cap=1,
    )
    await notifications.save(me.id, both)
    notifier = FakeNotifier()

    result = await _tick(notifications, moon, notifier).execute(BUDGET)

    assert result.sent == 1
    assert len(notifier.moon) == 1
    assert notifier.practice == []


async def test_after_ten_unanswered_reminders_one_note_then_off(
    accounts: InMemoryAccounts, notifications: InMemoryNotifications, moon: InMemoryMoon
) -> None:
    me = await _opted_in(accounts, notifications)
    for i in range(1, UNANSWERED_LIMIT + 1):
        day = MON - timedelta(days=i)
        notifications.deliveries[(me.id, practice_key(day))] = {
            "status": "sent",
            "attempts": 1,
            "local_date": day,
        }
    notifier = FakeNotifier()

    result = await _tick(notifications, moon, notifier).execute(BUDGET)

    [(_, note)] = notifier.practice
    assert note.pause
    assert result.paused == 1
    assert notifications.stored[me.id].practice.on is False


async def test_a_failed_pause_note_keeps_the_reminder_on(
    accounts: InMemoryAccounts, notifications: InMemoryNotifications, moon: InMemoryMoon
) -> None:
    me = await _opted_in(accounts, notifications)
    for i in range(1, UNANSWERED_LIMIT + 1):
        day = MON - timedelta(days=i)
        notifications.deliveries[(me.id, practice_key(day))] = {
            "status": "sent",
            "attempts": 1,
            "local_date": day,
        }
    notifier = FakeNotifier([DeliveryResult(DeliveryStatus.FAILED)])

    await _tick(notifications, moon, notifier).execute(BUDGET)

    assert notifications.stored[me.id].practice.on is True


async def test_no_zone_no_practice_reminder(
    accounts: InMemoryAccounts, notifications: InMemoryNotifications, moon: InMemoryMoon
) -> None:
    me = await _account(accounts, zone=None)
    await notifications.save(me.id, replace(DEFAULTS, practice=replace(DEFAULTS.practice, on=True)))

    assert (await _tick(notifications, moon, FakeNotifier()).execute(BUDGET)).sent == 0


async def test_turned_back_on_after_the_note_gets_a_normal_reminder_next_day(
    accounts: InMemoryAccounts, notifications: InMemoryNotifications, moon: InMemoryMoon
) -> None:
    me = await _opted_in(accounts, notifications)
    for i in range(1, UNANSWERED_LIMIT + 1):
        day = MON - timedelta(days=i)
        notifications.deliveries[(me.id, practice_key(day))] = {
            "status": "sent",
            "attempts": 1,
            "local_date": day,
        }
    notifier = FakeNotifier()
    await _tick(notifications, moon, notifier).execute(BUDGET)  # the note, then off
    await UpdatePracticeReminder(notifications).execute(Principal(me), ReminderPatch(on=True))

    tue = send_instant(MON + timedelta(days=1), time(10), ZONE)
    await _tick(notifications, moon, notifier, tue).execute(BUDGET)

    assert [n.pause for _, n in notifier.practice] == [True, False]


async def test_an_old_offer_tap_does_not_undo_a_later_choice(
    accounts: InMemoryAccounts, notifications: InMemoryNotifications
) -> None:
    me = await _account(accounts)
    await UpdatePracticeReminder(notifications).execute(
        Principal(me), ReminderPatch(on=True, at=time(18))
    )

    saved = await AnswerPracticeOffer(notifications, FixedClock(MORNING)).execute(
        Principal(me), yes=False
    )

    assert (saved.practice.on, saved.practice.at) == (True, time(18))


async def test_a_time_in_quiet_hours_is_refused_even_while_off(
    accounts: InMemoryAccounts, notifications: InMemoryNotifications
) -> None:
    me = await _account(accounts)

    with pytest.raises(InvalidSettings):
        await UpdatePracticeReminder(notifications).execute(
            Principal(me), ReminderPatch(at=time(3))
        )


async def test_tick_follows_the_day_off_when_reminder_days_are_not_custom(
    accounts: InMemoryAccounts, notifications: InMemoryNotifications, moon: InMemoryMoon
) -> None:
    """PR-09: reminders come on the practice days only (Monday is the day off here)."""
    me = await _account(accounts)
    await notifications.patch_practice(me.id, ReminderPatch(on=True), DEFAULTS)
    await accounts.set_day_off(me.id, DayOff(frozenset({1})))
    notifier = FakeNotifier()

    await _tick(notifications, moon, notifier).execute(BUDGET)

    assert notifier.practice == []
