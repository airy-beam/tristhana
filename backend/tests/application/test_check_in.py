"""Check-in use cases on fakes (PR-06, ADR-0024): per-field patches, the practiced-day
guard, absolute tag toggles, clearing, reads through `GetDays` (an empty row reads as none),
the setting through `UpdateProfile`, the lifecycle with status changes, the today/yesterday
rule in the caller's zone, and no teacher or aggregate seam that could leak them.

The new modules are imported inside the tests (test-first: the suite keeps collecting)."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from tests.fakes import (
    FixedClock,
    InMemoryAccounts,
    InMemoryCheckIns,
    InMemoryDays,
    InMemoryMoon,
    InMemoryPractices,
    cities,
    practice_use_cases,
)
from tristhana.application import policies
from tristhana.application.days import ClearDayStatus, GetDays, SetDayStatus
from tristhana.application.policies import Principal
from tristhana.application.practice import ClearPractice, DayNotPracticed, SavePractice
from tristhana.application.practice_patch import PracticePatch
from tristhana.application.settings import UpdateProfile
from tristhana.application.stats import GetYearStats
from tristhana.domain.accounts import (
    Account,
    ExternalProfile,
    IdentityKey,
    IdentityProvider,
    NewAccount,
    ProfilePatch,
)
from tristhana.domain.days import DayStatus
from tristhana.domain.milestones import NO_COUNTS


def _uc() -> Any:
    from tristhana.application import check_in

    return check_in


def _dm() -> Any:
    from tristhana.domain import check_in

    return check_in


def _patch() -> Any:
    from tristhana.application.check_in_patch import CheckInPatch

    return CheckInPatch


def _c(**values: Any) -> Any:
    """A CheckIn; `tags` given as keys."""
    m = _dm()
    tags = values.pop("tags", ())
    return m.CheckIn(**values, tags=frozenset(m.CheckInTag(t) for t in tags))


def _of(**values: Any) -> Any:
    """CheckInPatch.of with `tags` given as keys."""
    if "tags" in values:
        values["tags"] = frozenset(_dm().CheckInTag(t) for t in values["tags"])
    return _patch().of(**values)


def _tag(key: str) -> Any:
    return _dm().CheckInTag(key)


NOW = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)  # Almaty: Mon Oct 19, 11:00
MON, SUN, FRI = date(2026, 10, 19), date(2026, 10, 18), date(2026, 10, 16)
TG = ExternalProfile(IdentityKey(IdentityProvider.TELEGRAM, "42"), "Ash", "en")


def _me(timezone: str | None = "Asia/Almaty", locale: str = "en") -> Principal:
    return Principal(
        Account(id=uuid4(), display_name="A", locale=locale, timezone=timezone, last_seen_at=NOW)  # type: ignore[arg-type]
    )


@pytest.fixture
def days() -> InMemoryDays:
    return InMemoryDays()


@pytest.fixture
def check_ins(days: InMemoryDays) -> InMemoryCheckIns:
    return InMemoryCheckIns(days)


async def _log(days: InMemoryDays, me: Principal, day: date, status: DayStatus) -> None:
    await SetDayStatus(days, FixedClock(NOW), NO_COUNTS).execute(me, day, status)


async def _practiced(days: InMemoryDays, me: Principal, *on: date) -> None:
    for day in on:
        await _log(days, me, day, DayStatus.PRACTICED)


def _stored(days: InMemoryDays, me: Principal, day: date) -> Any:
    return days.check_in_rows.get((me.account.id, day))


# SaveCheckIn


async def test_each_tap_patches_only_its_field(
    days: InMemoryDays, check_ins: InMemoryCheckIns
) -> None:
    me = _me()
    await _practiced(days, me, MON)
    save = _uc().SaveCheckIn(check_ins)

    await save.execute(me, MON, _of(mood=4))
    await save.execute(me, MON, _of(energy=2))
    saved = await save.execute(me, MON, _of(effort=5))

    assert saved == _c(mood=4, energy=2, effort=5)
    assert _stored(days, me, MON) == saved


async def test_a_zero_tap_clears_one_scale_and_keeps_the_rest(
    days: InMemoryDays, check_ins: InMemoryCheckIns
) -> None:
    me = _me()
    await _practiced(days, me, MON)
    save = _uc().SaveCheckIn(check_ins)
    await save.execute(me, MON, _of(mood=4, energy=3))

    saved = await save.execute(me, MON, _of(mood=None))

    assert saved == _c(mood=None, energy=3)


async def test_a_full_patch_replaces_everything(
    days: InMemoryDays, check_ins: InMemoryCheckIns
) -> None:
    me = _me()
    await _practiced(days, me, MON)
    save = _uc().SaveCheckIn(check_ins)
    await save.execute(me, MON, _of(mood=2, tags=["stiff"]))

    saved = await save.execute(me, MON, _patch().full(_c(energy=4)))

    assert saved == _c(energy=4)


def test_patch_names_only_known_fields() -> None:
    assert _of(mood=3).fields == {"mood"}
    assert _patch().full(_c()).fields == {"mood", "energy", "effort", "tags"}
    with pytest.raises(ValueError, match="unknown"):
        _of(note="hi")


@pytest.mark.parametrize("status", [s for s in DayStatus if s is not DayStatus.PRACTICED])
async def test_a_check_in_needs_a_practiced_day(
    days: InMemoryDays, check_ins: InMemoryCheckIns, status: DayStatus
) -> None:
    me = _me()
    await _log(days, me, MON, status)

    with pytest.raises(DayNotPracticed):
        await _uc().SaveCheckIn(check_ins).execute(me, MON, _of(mood=3))
    assert days.check_in_rows == {}


async def test_no_check_in_on_a_day_never_logged(check_ins: InMemoryCheckIns) -> None:
    with pytest.raises(DayNotPracticed):
        await _uc().SaveCheckIn(check_ins).execute(_me(), MON, _of(energy=3))
    with pytest.raises(DayNotPracticed):
        await _uc().SetCheckInTag(check_ins).execute(_me(), MON, _tag("calm"), True)


@pytest.mark.parametrize(
    ("values", "full"),
    [
        ({"mood": 6}, False),
        ({"energy": 0}, False),
        ({"effort": 7}, False),
        ({"mood": 3, "slot": 2}, True),
    ],
)
async def test_values_are_validated_before_any_write(
    days: InMemoryDays, check_ins: InMemoryCheckIns, values: dict[str, Any], full: bool
) -> None:
    me = _me()
    await _practiced(days, me, MON)
    patch = _patch().full(_c(**values)) if full else _of(**values)

    with pytest.raises(_dm().InvalidCheckIn):
        await _uc().SaveCheckIn(check_ins).execute(me, MON, patch)
    assert days.check_in_rows == {}


# SetCheckInTag: absolute, idempotent


async def test_a_tag_on_twice_is_on_once_and_off_is_off(
    days: InMemoryDays, check_ins: InMemoryCheckIns
) -> None:
    me = _me()
    await _practiced(days, me, MON)
    tag = _uc().SetCheckInTag(check_ins)

    await tag.execute(me, MON, _tag("light"), True)
    twice = await tag.execute(me, MON, _tag("light"), True)
    both = await tag.execute(me, MON, _tag("calm"), True)
    off = await tag.execute(me, MON, _tag("light"), False)
    off_again = await tag.execute(me, MON, _tag("light"), False)

    assert twice.tags == {_tag("light")}
    assert both.tags == {_tag("light"), _tag("calm")}
    assert off.tags == off_again.tags == {_tag("calm")}


async def test_tags_and_scales_live_together(
    days: InMemoryDays, check_ins: InMemoryCheckIns
) -> None:
    me = _me()
    await _practiced(days, me, MON)
    await _uc().SaveCheckIn(check_ins).execute(me, MON, _of(mood=5))

    saved = await _uc().SetCheckInTag(check_ins).execute(me, MON, _tag("steady_breath"), True)

    assert saved == _c(mood=5, tags=["steady_breath"])


# ClearCheckIn


async def test_clear_is_idempotent(days: InMemoryDays, check_ins: InMemoryCheckIns) -> None:
    me = _me()
    await _practiced(days, me, MON)
    await _uc().SaveCheckIn(check_ins).execute(me, MON, _of(mood=3))

    await _uc().ClearCheckIn(check_ins).execute(me, MON)
    await _uc().ClearCheckIn(check_ins).execute(me, MON)

    assert days.check_in_rows == {}
    [day] = days.rows.values()
    assert day[0].status is DayStatus.PRACTICED  # the day itself stays


# Reads through GetDays


def _get_days(days: InMemoryDays, now: datetime = NOW) -> GetDays:
    days.moon = days.moon or InMemoryMoon()
    return GetDays(days, cities(), FixedClock(now))


async def test_get_days_carries_the_check_in_of_a_practiced_day(
    days: InMemoryDays, check_ins: InMemoryCheckIns
) -> None:
    me = _me()
    await _practiced(days, me, SUN, MON)
    await _uc().SaveCheckIn(check_ins).execute(me, MON, _of(mood=4, tags=["calm"]))

    view = await _get_days(days).execute(me)

    by_date = {d.local_date: d for d in view.days}
    assert by_date[MON].check_ins == (_c(mood=4, tags=["calm"]),)
    assert by_date[SUN].check_ins == ()


async def test_get_days_reads_an_empty_row_as_no_check_in(
    days: InMemoryDays, check_ins: InMemoryCheckIns
) -> None:
    me = _me()
    await _practiced(days, me, MON)
    await _uc().SaveCheckIn(check_ins).execute(me, MON, _patch().full(_c()))
    assert _stored(days, me, MON) == _c()  # stored as an empty row

    view = await _get_days(days).execute(me)

    assert [d.check_ins for d in view.days] == [()]


async def test_clearing_every_field_one_by_one_reads_as_none(
    days: InMemoryDays, check_ins: InMemoryCheckIns
) -> None:
    me = _me()
    await _practiced(days, me, MON)
    await _uc().SaveCheckIn(check_ins).execute(me, MON, _of(mood=2))
    await _uc().SetCheckInTag(check_ins).execute(me, MON, _tag("sore"), True)
    await _uc().SaveCheckIn(check_ins).execute(me, MON, _of(mood=None))
    await _uc().SetCheckInTag(check_ins).execute(me, MON, _tag("sore"), False)

    view = await _get_days(days).execute(me)

    assert [d.check_ins for d in view.days] == [()]


# The lifecycle (the same rules the SQL keeps in one statement)


async def test_a_status_change_deletes_the_check_in_and_practiced_again_does_not_restore(
    days: InMemoryDays, check_ins: InMemoryCheckIns
) -> None:
    me = _me()
    await _practiced(days, me, MON)
    await _uc().SaveCheckIn(check_ins).execute(me, MON, _of(mood=4))

    await _log(days, me, MON, DayStatus.REST)
    assert days.check_in_rows == {}
    await _log(days, me, MON, DayStatus.PRACTICED)  # a mistaken 😌, then 🧘 (accepted)

    assert days.check_in_rows == {}


async def test_practiced_again_on_a_practiced_day_keeps_it(
    days: InMemoryDays, check_ins: InMemoryCheckIns
) -> None:
    me = _me()
    await _practiced(days, me, MON)
    await _uc().SaveCheckIn(check_ins).execute(me, MON, _of(mood=4))

    await _log(days, me, MON, DayStatus.PRACTICED)

    assert _stored(days, me, MON) == _c(mood=4)


async def test_remove_details_keeps_the_check_in(
    days: InMemoryDays, check_ins: InMemoryCheckIns
) -> None:
    me = _me()
    await _practiced(days, me, MON)
    practices = InMemoryPractices(days)
    await SavePractice(practices, practice_use_cases().catalog).execute(
        me, MON, PracticePatch.of(duration_min=90)
    )
    await _uc().SaveCheckIn(check_ins).execute(me, MON, _of(effort=3))

    await ClearPractice(practices).execute(me, MON)

    assert days.practice_rows == {}
    assert _stored(days, me, MON) == _c(effort=3)


async def test_clearing_the_day_removes_the_check_in(
    days: InMemoryDays, check_ins: InMemoryCheckIns
) -> None:
    me = _me()
    await _practiced(days, me, MON)
    await _uc().SaveCheckIn(check_ins).execute(me, MON, _of(energy=1))

    await ClearDayStatus(days).execute(me, MON)

    assert days.check_in_rows == {}


async def test_a_check_in_needs_no_details(days: InMemoryDays, check_ins: InMemoryCheckIns) -> None:
    me = _me()
    await _practiced(days, me, MON)

    await _uc().SaveCheckIn(check_ins).execute(me, MON, _of(mood=3))

    assert days.practice_rows == {}
    assert _stored(days, me, MON) == _c(mood=3)


async def test_check_ins_are_per_account(days: InMemoryDays, check_ins: InMemoryCheckIns) -> None:
    me, other = _me(), _me()
    await _practiced(days, me, MON)
    await _practiced(days, other, MON)
    await _uc().SaveCheckIn(check_ins).execute(me, MON, _of(mood=5))

    mine = await _get_days(days).execute(me)
    theirs = await _get_days(days).execute(other)

    assert [d.check_ins for d in mine.days] == [(_c(mood=5),)]
    assert [d.check_ins for d in theirs.days] == [()]


# The setting through UpdateProfile (ADR-0021: its own field group)


async def _account(accounts: InMemoryAccounts) -> Principal:
    account = await accounts.create_with_identity(TG.key, NewAccount("Ash", "en"))
    return Principal(account)


async def test_offer_check_in_is_on_for_a_new_account() -> None:
    me = await _account(InMemoryAccounts())

    assert me.account.offer_check_in is True  # type: ignore[attr-defined]


async def test_update_profile_patches_offer_check_in_alone() -> None:
    accounts = InMemoryAccounts()
    me = await _account(accounts)
    update = UpdateProfile(accounts)

    off = await update.execute(me, ProfilePatch(offer_check_in=False), TG)  # type: ignore[call-arg]
    named = await update.execute(Principal(off), ProfilePatch(display_name="Anna"), TG)
    default = await update.execute(Principal(named), ProfilePatch(offer_check_in=None), TG)  # type: ignore[call-arg]

    assert off.offer_check_in is False  # type: ignore[attr-defined]
    assert (off.display_name, off.locale) == ("Ash", "en")
    assert named.offer_check_in is False  # type: ignore[attr-defined]  # omitted = unchanged
    assert default.offer_check_in is True  # type: ignore[attr-defined]  # null = the default
    assert default.display_name == "Anna"


# Today / yesterday in the caller's zone (provisional allowed), from the clock


# One instant, two dates: Kiritimati (UTC+14) is already on Tue Oct 20, Honolulu (UTC-10)
# still on Mon Oct 19. Sun Oct 18 is Honolulu's yesterday but Kiritimati's day before.
EDGE = datetime(2026, 10, 19, 10, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("zone", "today", "offered"),
    [
        ("Pacific/Kiritimati", date(2026, 10, 20), False),
        ("Pacific/Honolulu", date(2026, 10, 19), True),
    ],
)
async def test_the_mood_row_follows_the_callers_own_date(
    days: InMemoryDays, zone: str, today: date, offered: bool
) -> None:
    me = _me(timezone=zone)
    local_today, known = _get_days(days, EDGE).today(me)

    assert (local_today, known) == (today, True)
    assert _dm().offer_mood_row(SUN, local_today, None, True) is offered


# 18:20 UTC on Sun Oct 18: Kathmandu (+5:45) is already on Mon 00:05, Kolkata (+5:30)
# still on Sun 23:50; Almaty, Moscow, Berlin (CEST) and New York are on Sunday too.
LATE_SUNDAY = datetime(2026, 10, 18, 18, 20, tzinfo=UTC)


@pytest.mark.parametrize(
    ("zone", "today"),
    [
        ("Asia/Kathmandu", MON),
        ("Asia/Kolkata", SUN),
        ("Asia/Almaty", SUN),
        ("Europe/Moscow", SUN),
        ("Europe/Berlin", SUN),
        ("America/New_York", SUN),
    ],
)
async def test_today_and_yesterday_per_zone(days: InMemoryDays, zone: str, today: date) -> None:
    me = _me(timezone=zone)
    local_today, _ = _get_days(days, LATE_SUNDAY).today(me)

    assert local_today == today
    for back, offered in ((0, True), (1, True), (2, False)):
        day = local_today - timedelta(days=back)
        assert _dm().offer_mood_row(day, local_today, None, True) is offered


async def test_a_provisional_zone_still_gives_a_today(days: InMemoryDays) -> None:
    # No device zone yet: ru → Europe/Moscow. 22:30 UTC on Sun is already Mon in Moscow.
    me = _me(timezone=None, locale="ru")
    local_today, known = _get_days(days, datetime(2026, 10, 18, 22, 30, tzinfo=UTC)).today(me)

    assert (local_today, known) == (MON, False)
    assert _dm().offer_mood_row(SUN, local_today, None, True) is True
    assert _dm().offer_mood_row(date(2026, 10, 17), local_today, None, True) is False


# Owner only: teachers and aggregates never see check-ins (ADR-0024)


def test_another_account_may_never_view_check_ins() -> None:
    me, teacher = _me(), _me()

    assert policies.can_view_check_ins(teacher.account, me.account) is False


async def test_year_stats_ignore_check_ins(days: InMemoryDays, check_ins: InMemoryCheckIns) -> None:
    accounts = InMemoryAccounts()
    me = await _account(accounts)
    me = Principal(await accounts.set_timezone_if_unset(me.account.id, "Asia/Almaty"))
    me = Principal(replace(me.account, created_at=datetime(2026, 1, 1, tzinfo=UTC)))
    await _practiced(days, me, FRI, MON)
    catalog = practice_use_cases().catalog
    stats = GetYearStats(days, InMemoryMoon(), cities(), catalog, FixedClock(NOW))
    before = await stats.execute(me)

    await (
        _uc()
        .SaveCheckIn(check_ins)
        .execute(me, MON, _of(mood=1, energy=1, effort=5, tags=list(_dm().CheckInTag)))
    )
    after = await stats.execute(me)

    assert after == before
