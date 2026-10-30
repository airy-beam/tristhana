"""GM-01 part 2: practice-count milestones through the day-write use cases (ADR-0028)."""

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from tests.fakes import FixedClock, InMemoryDays, InMemoryPractices
from tristhana.application.days import ClearDayStatus, SetDayStatus
from tristhana.application.policies import Principal
from tristhana.application.remind import LogFromReminder, QuickLogSameAsLast
from tristhana.domain.accounts import Account
from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.milestones import PracticeCounts
from tristhana.domain.progression import Celebration, CelebrationKind

NOW = datetime(2026, 10, 30, 6, 0, tzinfo=UTC)
TODAY = date(2026, 10, 30)  # in UTC
COUNTS = PracticeCounts((100, 365, 1000))
P = DayStatus.PRACTICED


def _hundred() -> tuple[Celebration, ...]:
    return (Celebration(CelebrationKind.PRACTICE_COUNT, count=100),)


@pytest.fixture
def days() -> InMemoryDays:
    return InMemoryDays()


@pytest.fixture
def me() -> Principal:
    account = Account(
        id=uuid4(),
        display_name="A",
        locale="en",
        timezone="UTC",
        last_seen_at=NOW,  # type: ignore[arg-type]
    )
    return Principal(account)


def _seed(days: InMemoryDays, me: Principal, n: int, status: DayStatus = P) -> None:
    """`n` days before yesterday, so today and yesterday stay free."""
    for i in range(n):
        when = TODAY - timedelta(days=2 + i)
        days.rows[(me.account.id, when)] = (DayLog(when, status), "UTC")


def _set(days: InMemoryDays) -> SetDayStatus:
    return SetDayStatus(days, FixedClock(NOW), COUNTS)


async def test_the_hundredth_practice_celebrates_once(days: InMemoryDays, me: Principal) -> None:
    _seed(days, me, 99)

    saved = await _set(days).execute(me, TODAY, P)
    again = await _set(days).execute(me, TODAY, P)

    assert saved.celebrations == _hundred()
    assert again.celebrations == ()
    assert days.milestone_rows == {(me.account.id, 100): True}


async def test_no_celebration_below_or_after_a_threshold(days: InMemoryDays, me: Principal) -> None:
    _seed(days, me, 98)

    assert (await _set(days).execute(me, TODAY, P)).celebrations == ()
    assert (await _set(days).execute(me, TODAY - timedelta(1), P)).celebrations == _hundred()
    assert (await _set(days).execute(me, date(2025, 1, 1), P)).celebrations == ()


async def test_rest_like_days_never_count(days: InMemoryDays, me: Principal) -> None:
    _seed(days, me, 99)
    for status in (DayStatus.REST, DayStatus.MOON, DayStatus.LADIES, DayStatus.SKIPPED):
        saved = await _set(days).execute(me, TODAY, status)
        assert saved.celebrations == ()
    assert days.milestone_rows == {}


async def test_practiced_rest_practiced_at_100_is_quiet(days: InMemoryDays, me: Principal) -> None:
    _seed(days, me, 99)
    await _set(days).execute(me, TODAY, P)

    await _set(days).execute(me, TODAY, DayStatus.REST)
    saved = await _set(days).execute(me, TODAY, P)

    assert saved.celebrations == ()


async def test_cleared_then_logged_again_is_quiet(days: InMemoryDays, me: Principal) -> None:
    _seed(days, me, 99)
    await _set(days).execute(me, TODAY, P)

    await ClearDayStatus(days).execute(me, TODAY)
    saved = await _set(days).execute(me, TODAY, P)

    assert saved.celebrations == ()


async def test_a_backfill_crossing_100_celebrates(days: InMemoryDays, me: Principal) -> None:
    _seed(days, me, 99)

    saved = await _set(days).execute(me, date(2025, 1, 1), P)

    assert saved.celebrations == _hundred()


async def test_already_past_a_threshold_is_seeded_silently(
    days: InMemoryDays, me: Principal
) -> None:
    _seed(days, me, 249)

    saved = await _set(days).execute(me, TODAY, P)

    assert saved.celebrations == ()
    assert days.milestone_rows == {(me.account.id, 100): False}


async def test_a_threshold_added_later_is_silent(days: InMemoryDays, me: Principal) -> None:
    _seed(days, me, 699)
    later = SetDayStatus(days, FixedClock(NOW), PracticeCounts((100, 365, 500, 1000)))

    saved = await later.execute(me, TODAY, P)

    assert saved.celebrations == ()
    assert {t for (_, t) in days.milestone_rows} == {100, 365, 500}


async def test_without_counts_nothing_is_recorded(days: InMemoryDays, me: Principal) -> None:
    _seed(days, me, 99)

    saved = await SetDayStatus(days, FixedClock(NOW)).execute(me, TODAY, P)

    assert (saved.celebrations, days.milestone_rows) == ((), {})


async def test_reminder_taps_celebrate_on_an_empty_day(days: InMemoryDays, me: Principal) -> None:
    _seed(days, me, 98)
    quick = QuickLogSameAsLast(days, InMemoryPractices(days), FixedClock(NOW), COUNTS)
    log = LogFromReminder(days, FixedClock(NOW), COUNTS)

    first = await quick.execute(me, TODAY - timedelta(1))
    second = await log.execute(me, TODAY, P)
    already = await log.execute(me, TODAY, P)

    assert first.celebrations == ()
    assert second.celebrations == _hundred()
    assert (already.already, already.celebrations) == (True, ())


async def test_a_reminder_rest_tap_never_counts(days: InMemoryDays, me: Principal) -> None:
    _seed(days, me, 99)

    rest = await LogFromReminder(days, FixedClock(NOW), COUNTS).execute(me, TODAY, DayStatus.REST)

    assert (rest.celebrations, days.milestone_rows) == ((), {})
