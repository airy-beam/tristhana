"""Diary use cases on fakes (PR-07, ADR-0025): save normalises (blank deletes, too long is
refused), dates follow the logging rules in the caller's zone (provisional allowed), reads go
through `GetDays` (`DaysView.notes`, any status or none), the note is independent of the
status (status changes and clearing the day keep it), and the policy is owner-only.

The new modules are imported inside the tests (test-first: the suite keeps collecting)."""

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from tests.fakes import (
    FixedClock,
    InMemoryCheckIns,
    InMemoryDays,
    InMemoryDiary,
    InMemoryMoon,
    cities,
)
from tristhana.application import policies
from tristhana.application.days import ClearDayStatus, GetDays, SetDayStatus
from tristhana.application.policies import Principal
from tristhana.domain.accounts import Account
from tristhana.domain.days import DateInFuture, DateTooEarly, DayStatus
from tristhana.domain.milestones import NO_COUNTS
from tristhana.domain.moon import MoonDay, MoonDayKind

NOW = datetime(2026, 10, 27, 6, 0, tzinfo=UTC)  # Almaty: Tue Oct 27, 11:00
TUE, MON, SUN = date(2026, 10, 27), date(2026, 10, 26), date(2026, 10, 25)


def _uc() -> Any:
    from tristhana.application import diary

    return diary


def _dm() -> Any:
    from tristhana.domain import diary

    return diary


def _note(text: str | None) -> Any:
    return _dm().DiaryNote(text)


def _me(timezone: str | None = "Asia/Almaty", locale: str = "en") -> Principal:
    return Principal(
        Account(
            id=uuid4(),
            display_name="A",
            locale=locale,  # type: ignore[arg-type]
            timezone=timezone,
            last_seen_at=NOW,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )


@pytest.fixture
def days() -> InMemoryDays:
    return InMemoryDays()


@pytest.fixture
def diary(days: InMemoryDays) -> InMemoryDiary:
    return InMemoryDiary(days)


def _save(diary: InMemoryDiary, now: datetime = NOW) -> Any:
    return _uc().SaveDiaryNote(diary, FixedClock(now))


def _stored(days: InMemoryDays, me: Principal, day: date) -> Any:
    return days.diary_rows.get((me.account.id, day))


def _get_days(days: InMemoryDays, now: datetime = NOW) -> GetDays:
    days.moon = days.moon or InMemoryMoon()
    return GetDays(days, cities(), FixedClock(now))


# SaveDiaryNote


async def test_save_stores_the_normalised_text_and_returns_it(
    days: InMemoryDays, diary: InMemoryDiary
) -> None:
    me = _me()

    saved = await _save(diary).execute(me, TUE, "  Felt light.\r\nTeacher: keep the gaze.  \n")

    assert saved == "Felt light.\nTeacher: keep the gaze."
    assert _stored(days, me, TUE) == _note("Felt light.\nTeacher: keep the gaze.")


async def test_save_replaces_the_note(days: InMemoryDays, diary: InMemoryDiary) -> None:
    me = _me()
    await _save(diary).execute(me, TUE, "first")

    await _save(diary).execute(me, TUE, "second")

    assert _stored(days, me, TUE) == _note("second")


@pytest.mark.parametrize("blank", ["", "   ", "\n\t\r\n"])
async def test_blank_deletes(days: InMemoryDays, diary: InMemoryDiary, blank: str) -> None:
    me = _me()
    await _save(diary).execute(me, TUE, "something")

    saved = await _save(diary).execute(me, TUE, blank)

    assert saved is None
    assert days.diary_rows == {}


async def test_blank_on_a_day_without_a_note_is_fine(
    days: InMemoryDays, diary: InMemoryDiary
) -> None:
    assert await _save(diary).execute(_me(), TUE, " ") is None
    assert days.diary_rows == {}


async def test_too_long_is_refused_and_nothing_changes(
    days: InMemoryDays, diary: InMemoryDiary
) -> None:
    me = _me()
    await _save(diary).execute(me, TUE, "kept")

    with pytest.raises(_dm().NoteTooLong):
        await _save(diary).execute(me, TUE, "a" * 2001)

    assert _stored(days, me, TUE) == _note("kept")


async def test_2000_code_points_are_saved_whole(days: InMemoryDays, diary: InMemoryDiary) -> None:
    me = _me()

    saved = await _save(diary).execute(me, TUE, "🧘" * 2000)

    assert saved == "🧘" * 2000


async def test_a_future_date_is_refused(days: InMemoryDays, diary: InMemoryDiary) -> None:
    with pytest.raises(DateInFuture):
        await _save(diary).execute(_me(), TUE + timedelta(days=1), "tomorrow")
    assert days.diary_rows == {}


async def test_before_2000_is_refused(days: InMemoryDays, diary: InMemoryDiary) -> None:
    with pytest.raises(DateTooEarly):
        await _save(diary).execute(_me(), date(1999, 12, 31), "old")
    assert days.diary_rows == {}


async def test_the_first_day_and_any_past_day_are_fine(
    days: InMemoryDays, diary: InMemoryDiary
) -> None:
    me = _me()

    await _save(diary).execute(me, date(2000, 1, 1), "first")
    await _save(diary).execute(me, date(2019, 6, 1), "later")

    assert len(days.diary_rows) == 2


# One instant, two dates: Kiritimati (UTC+14) is already on Tue Oct 20, Honolulu (UTC-10)
# still on Mon Oct 19.
EDGE = datetime(2026, 10, 19, 10, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("zone", "allowed"), [("Pacific/Kiritimati", True), ("Pacific/Honolulu", False)]
)
async def test_today_is_the_callers_own_date(
    days: InMemoryDays, diary: InMemoryDiary, zone: str, allowed: bool
) -> None:
    me = _me(timezone=zone)
    save = _save(diary, EDGE).execute(me, date(2026, 10, 20), "Tuesday already?")

    if allowed:
        assert await save == "Tuesday already?"
    else:
        with pytest.raises(DateInFuture):
            await save


async def test_a_provisional_zone_never_refuses_a_real_today(
    days: InMemoryDays, diary: InMemoryDiary
) -> None:
    # No device zone yet: the latest date on Earth bounds it (as for logging a status).
    me = _me(timezone=None, locale="ru")

    saved = await _save(diary, EDGE).execute(me, date(2026, 10, 20), "Заметка")

    assert saved == "Заметка"


# GetDiaryNote / ClearDiaryNote


async def test_get_reads_the_one_day(days: InMemoryDays, diary: InMemoryDiary) -> None:
    me = _me()
    await _save(diary).execute(me, MON, "Monday")

    assert await _uc().GetDiaryNote(diary, FixedClock(NOW)).execute(me, MON) == _note("Monday")
    assert await _uc().GetDiaryNote(diary, FixedClock(NOW)).execute(me, TUE) is None


async def test_get_passes_an_unreadable_note_through(
    days: InMemoryDays, diary: InMemoryDiary
) -> None:
    me = _me()
    days.diary_rows[(me.account.id, MON)] = _note(None)

    assert await _uc().GetDiaryNote(diary, FixedClock(NOW)).execute(me, MON) == _note(None)


async def test_clear_is_idempotent(days: InMemoryDays, diary: InMemoryDiary) -> None:
    me = _me()
    await _save(diary).execute(me, MON, "Monday")

    await _uc().ClearDiaryNote(diary).execute(me, MON)
    await _uc().ClearDiaryNote(diary).execute(me, MON)
    await _uc().ClearDiaryNote(diary).execute(me, SUN)  # never had one

    assert days.diary_rows == {}


async def test_notes_are_per_account(days: InMemoryDays, diary: InMemoryDiary) -> None:
    me, other = _me(), _me()
    await _save(diary).execute(me, MON, "mine")

    assert await _uc().GetDiaryNote(diary, FixedClock(NOW)).execute(other, MON) is None
    assert (await _get_days(days).execute(other)).notes == {}  # type: ignore[attr-defined]


# Reads through GetDays: any status, or none


async def test_get_days_carries_notes_for_logged_and_unlogged_days(
    days: InMemoryDays, diary: InMemoryDiary
) -> None:
    me = _me()
    await SetDayStatus(days, FixedClock(NOW), NO_COUNTS).execute(me, MON, DayStatus.PRACTICED)
    await _save(diary).execute(me, MON, "practiced")
    await _save(diary).execute(me, SUN, "never logged")
    await _save(diary).execute(me, TUE - timedelta(days=30), "outside the window")

    view = await _get_days(days).execute(me)

    assert view.notes == {MON: _note("practiced"), SUN: _note("never logged")}  # type: ignore[attr-defined]
    assert [d.local_date for d in view.days] == [MON]  # notes never invent a logged day


async def test_get_days_without_notes_is_an_empty_dict(days: InMemoryDays) -> None:
    view = await _get_days(days).execute(_me())

    assert view.notes == {}  # type: ignore[attr-defined]


async def test_a_note_on_an_unlogged_auto_moon_day(
    days: InMemoryDays, diary: InMemoryDiary
) -> None:
    me = _me()
    days.moon = InMemoryMoon({"mysuru": [MoonDay(SUN, MoonDayKind.PURNIMA)]})
    await _save(diary).execute(me, SUN, "Full moon, rested.")

    view = await _get_days(days).execute(me)

    assert SUN in view.auto  # still shown as auto-rest: the note logs nothing
    assert view.days == []
    assert view.notes == {SUN: _note("Full moon, rested.")}  # type: ignore[attr-defined]


async def test_get_days_carries_an_unreadable_note(
    days: InMemoryDays, diary: InMemoryDiary
) -> None:
    me = _me()
    days.diary_rows[(me.account.id, MON)] = _note(None)

    view = await _get_days(days).execute(me)

    assert view.notes == {MON: _note(None)}  # type: ignore[attr-defined]


# Independent of the status (ADR-0025)


@pytest.mark.parametrize("status", list(DayStatus))
async def test_a_note_survives_every_status_change(
    days: InMemoryDays, diary: InMemoryDiary, status: DayStatus
) -> None:
    me = _me()
    set_status = SetDayStatus(days, FixedClock(NOW), NO_COUNTS)
    await set_status.execute(me, MON, DayStatus.PRACTICED)
    await _save(diary).execute(me, MON, "kept")

    await set_status.execute(me, MON, status)

    assert _stored(days, me, MON) == _note("kept")


async def test_a_status_change_that_deletes_the_check_in_keeps_the_note(
    days: InMemoryDays, diary: InMemoryDiary
) -> None:
    from tristhana.application.check_in import SaveCheckIn
    from tristhana.application.check_in_patch import CheckInPatch

    me = _me()
    set_status = SetDayStatus(days, FixedClock(NOW), NO_COUNTS)
    await set_status.execute(me, MON, DayStatus.PRACTICED)
    await SaveCheckIn(InMemoryCheckIns(days)).execute(me, MON, CheckInPatch.of(mood=4))
    await _save(diary).execute(me, MON, "kept")

    await set_status.execute(me, MON, DayStatus.REST)

    assert days.check_in_rows == {}
    assert _stored(days, me, MON) == _note("kept")


async def test_clearing_the_day_keeps_the_note(days: InMemoryDays, diary: InMemoryDiary) -> None:
    me = _me()
    await SetDayStatus(days, FixedClock(NOW), NO_COUNTS).execute(me, MON, DayStatus.SICK)
    await _save(diary).execute(me, MON, "kept")

    await ClearDayStatus(days).execute(me, MON)

    assert days.rows == {}
    assert _stored(days, me, MON) == _note("kept")
    assert (await _get_days(days).execute(me)).notes == {MON: _note("kept")}  # type: ignore[attr-defined]


async def test_a_note_never_logs_a_day(days: InMemoryDays, diary: InMemoryDiary) -> None:
    me = _me()

    await _save(diary).execute(me, MON, "Gave me Pasasana today!")

    assert days.rows == {}
    assert days.practice_rows == {}


# Owner only (ST-06 extends this one place)


def test_only_the_owner_may_view_the_diary() -> None:
    me, teacher = _me(), _me()

    assert policies.can_view_diary(me.account, me.account) is True  # type: ignore[attr-defined]
    assert policies.can_view_diary(teacher.account, me.account) is False  # type: ignore[attr-defined]
