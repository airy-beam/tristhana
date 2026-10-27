from datetime import UTC, date, datetime, time
from functools import cache
from pathlib import Path
from uuid import uuid4

import pytest

from tests.fakes import FixedClock, InMemoryDays, InMemoryPractices
from tristhana.application.days import SetDayStatus
from tristhana.application.policies import Principal
from tristhana.application.practice import (
    ClearPractice,
    CopyLastPractice,
    DayNotPracticed,
    GetPracticePresets,
    NoPreviousPractice,
    SavePractice,
)
from tristhana.application.practice_patch import PracticePatch
from tristhana.domain.accounts import Account
from tristhana.domain.days import DayStatus
from tristhana.domain.practice import (
    FULL_PRIMARY,
    InvalidLength,
    Practice,
    PracticeCatalog,
    PracticeContext,
    PracticeLength,
    TimezoneUnknown,
)
from tristhana.infrastructure.seed.catalog_yaml import load_catalog

SEED = Path(__file__).resolve().parents[3] / "data" / "seed"
NOW = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)
MON, FRI = date(2026, 10, 19), date(2026, 10, 16)


@cache
def catalog() -> PracticeCatalog:
    return PracticeCatalog(load_catalog(SEED / "asanas.yaml", SEED / "sequences.yaml"))


def _me(timezone: str | None = "Asia/Almaty") -> Principal:
    return Principal(
        Account(id=uuid4(), display_name="A", locale="ru", timezone=timezone, last_seen_at=NOW)
    )


@pytest.fixture
def days() -> InMemoryDays:
    return InMemoryDays()


async def _practiced(days: InMemoryDays, me: Principal, *on: date) -> None:
    for day in on:
        await SetDayStatus(days, FixedClock(NOW)).execute(me, day, DayStatus.PRACTICED)


async def test_each_tap_patches_one_field(days: InMemoryDays) -> None:
    me = _me()
    await _practiced(days, me, MON)
    save = SavePractice(InMemoryPractices(days), catalog())

    await save.execute(me, MON, PracticePatch.of(context=PracticeContext.MYSORE))
    saved = await save.execute(me, MON, PracticePatch.of(duration_min=90))

    assert (saved.practice.context, saved.practice.duration_min, saved.practice.timezone) == (
        PracticeContext.MYSORE,
        90,
        None,  # the zone is stamped only together with a start time
    )
    timed = await save.execute(me, MON, PracticePatch.of(start_time=time(6, 30)))
    assert timed.practice.timezone == "Asia/Almaty"


async def test_choosing_self_practice_turns_online_off(days: InMemoryDays) -> None:
    me = _me()
    await _practiced(days, me, MON)
    save = SavePractice(InMemoryPractices(days), catalog())
    await save.execute(me, MON, PracticePatch.of(context=PracticeContext.LED, online=True))

    saved = await save.execute(me, MON, PracticePatch.of(context=PracticeContext.SELF))

    assert saved.practice.online is False


async def test_details_need_a_practiced_day(days: InMemoryDays) -> None:
    me = _me()
    await SetDayStatus(days, FixedClock(NOW)).execute(me, MON, DayStatus.REST)

    with pytest.raises(DayNotPracticed):
        await SavePractice(InMemoryPractices(days), catalog()).execute(
            me, MON, PracticePatch.of(duration_min=60)
        )


async def test_lengths_are_validated_and_normalised(days: InMemoryDays) -> None:
    me = _me()
    await _practiced(days, me, MON)
    save = SavePractice(InMemoryPractices(days), catalog())

    saved = await save.execute(
        me, MON, PracticePatch.of(length=PracticeLength(("primary",), "setu-bandhasana"))
    )

    assert saved.practice.length == FULL_PRIMARY
    with pytest.raises(InvalidLength):
        await save.execute(me, MON, PracticePatch.of(length=PracticeLength(("advanced-c",))))


async def test_start_time_needs_a_known_zone(days: InMemoryDays) -> None:
    me = _me(timezone=None)
    await _practiced(days, me, MON)

    with pytest.raises(TimezoneUnknown):
        await SavePractice(InMemoryPractices(days), catalog()).execute(
            me, MON, PracticePatch.of(start_time=time(6, 30))
        )


async def test_status_change_removes_details(days: InMemoryDays) -> None:
    me = _me()
    await _practiced(days, me, MON)
    await SavePractice(InMemoryPractices(days), catalog()).execute(
        me, MON, PracticePatch.of(duration_min=60)
    )

    await SetDayStatus(days, FixedClock(NOW)).execute(me, MON, DayStatus.MOON)

    assert days.practice_rows == {}


async def test_copy_last_uses_the_newest_earlier_practice_without_start_time(
    days: InMemoryDays,
) -> None:
    me = _me()
    await _practiced(days, me, FRI, MON)
    practices = InMemoryPractices(days)
    await SavePractice(practices, catalog()).execute(
        me,
        FRI,
        PracticePatch.full(
            Practice(PracticeContext.LED, length=FULL_PRIMARY, duration_min=90, start_time=time(6))
        ),
    )

    copied = (await CopyLastPractice(practices).execute(me, MON)).practice

    assert (copied.context, copied.length, copied.duration_min, copied.start_time) == (
        PracticeContext.LED,
        FULL_PRIMARY,
        90,
        None,
    )


async def test_copy_last_errors(days: InMemoryDays) -> None:
    me = _me()
    await _practiced(days, me, MON)
    with pytest.raises(NoPreviousPractice):
        await CopyLastPractice(InMemoryPractices(days)).execute(me, MON)

    await _practiced(days, me, FRI)
    await SavePractice(InMemoryPractices(days), catalog()).execute(
        me, FRI, PracticePatch.of(duration_min=60)
    )
    with pytest.raises(DayNotPracticed):
        await CopyLastPractice(InMemoryPractices(days)).execute(me, date(2026, 10, 17))


async def test_clear_and_presets(days: InMemoryDays) -> None:
    me = _me()
    await _practiced(days, me, FRI, MON)
    practices = InMemoryPractices(days)
    await SavePractice(practices, catalog()).execute(
        me, FRI, PracticePatch.of(length=PracticeLength(("intermediate",), "karandavasana"))
    )

    presets = await GetPracticePresets(practices, catalog()).execute(me, MON)
    await ClearPractice(practices).execute(me, FRI)
    await ClearPractice(practices).execute(me, FRI)

    assert presets.last is not None
    assert presets.presets[-1] == ("recent", PracticeLength(("intermediate",), "karandavasana"))
    assert days.practice_rows == {}
