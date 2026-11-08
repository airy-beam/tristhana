"""Classes, the use cases on fakes (SC-02 spec §3, §7, §8): one window read per schedule,
expanded in the shala's zone (an online class may name another city, Q124); bounds from the
shala's local today, not the viewer's; 1:1 for staff only (Q121); the moon city with its
fallback; writes guarded by `can_manage_schedule` (Q118), the day off and the moon policy by
`can_edit_shala`; a split with `from`; caps; swaps validated at creation (Q125); the one-tap
day-off adoption through PR-09's `SetDayOff` (Q109, Q119); and no log port. A frozen clock.

Constructor and result shapes the spec leaves open are assumed in `World` and documented in
`tests/schedule_fakes.py`: `Schedule(zone, city, moon_policy, days_off, days, occurrences)`,
`ScheduleDay(date, moon, day_off, swap_from)`.
"""

import ast
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from tests.fakes import FixedClock, InMemoryMoon, cities
from tests.moon_follow_fakes import person
from tests.schedule_fakes import InMemorySchedule
from tests.shala_fakes import InMemoryShalas, ShalaAccounts, ShalaLinks
from tristhana.application.classes import (
    AddClosure,
    AddSwap,
    AdoptShalaDayOff,
    ClearOverride,
    CreateClass,
    DeleteClass,
    GetMyClasses,
    GetSchedule,
    ListClasses,
    RemoveClosure,
    RemoveSwap,
    SetOverride,
    Teaching,
    UpdateClass,
)
from tristhana.application.moon import UnknownLocation
from tristhana.application.policies import NotAllowed, NotFound, Principal
from tristhana.application.ports.classes import ClassDraft
from tristhana.application.ports.shalas import CapReached
from tristhana.application.rest_days import SetDayOff
from tristhana.application.shalas import ShalaPatch, UpdateShala
from tristhana.domain.accounts import Account
from tristhana.domain.classes import (
    MAX_CLASSES,
    MAX_FUTURE_CLOSURES,
    MAX_FUTURE_SWAPS,
    ClassType,
    InvalidClass,
    MoonPolicy,
    Override,
    OverrideStatus,
    Reason,
)
from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.domain.rest_days import DayOff, InvalidDayOff
from tristhana.domain.shalas import ShalaRole

NOW = datetime(2026, 11, 7, 6, 0, tzinfo=UTC)  # Sat 7 Nov, 11:00 in Almaty
TODAY = date(2026, 11, 7)
NOV = {d: date(2026, 11, d) for d in range(1, 31)}
TEACHER, ASSISTANT, OFFICE, ADMIN = (
    ShalaRole.TEACHER,
    ShalaRole.ASSISTANT,
    ShalaRole.OFFICE,
    ShalaRole.ADMIN,
)
MON_FRI = frozenset({1, 2, 3, 4, 5})


def _draft(**kw: Any) -> ClassDraft:
    fields: dict[str, Any] = {
        "type": ClassType.MYSORE,
        "title": None,
        "online": False,
        "city": None,
        "teacher_id": None,
        "start": time(6, 0),
        "minutes": 210,
        "weekdays": MON_FRI,
        "every": 1,
        "starts_on": NOV[9],
        "ends_on": None,
    }
    fields.update(kw)
    return ClassDraft(**fields)


def _ov(on: date, status: OverrideStatus | None = None, **kw: Any) -> Override:
    values: dict[str, Any] = {"moved_to": None, "start": None, "minutes": None, "teacher_id": None}
    values.update(kw)
    return Override(on_date=on, status=status, **values)


@dataclass
class World:
    instant: datetime = NOW
    clock: FixedClock = field(init=False)
    accounts: ShalaAccounts = field(init=False)
    shalas: InMemoryShalas = field(init=False)
    moon: InMemoryMoon = field(init=False)
    schedule: InMemorySchedule = field(init=False)

    def __post_init__(self) -> None:
        self.clock = FixedClock(self.instant)
        self.accounts = ShalaAccounts(clock=self.clock)
        links = ShalaLinks(self.accounts)
        self.shalas = InMemoryShalas(self.accounts, links)
        links.shalas = self.shalas
        self.accounts.links = links
        self.accounts.shalas = self.shalas
        self.moon = InMemoryMoon()
        self.schedule = InMemorySchedule(self.shalas, self.moon)

    def person(self, telegram_id: str, name: str = "Person", zone: str = "Asia/Almaty") -> Account:
        return person(self.accounts, telegram_id, name, zone=zone)

    def me(self, account: Account) -> Principal:
        return Principal(self.accounts.inputs(self.accounts.accounts[account.id]))

    def shala(self, owner: Account, city: str = "almaty", **kw: Any) -> UUID:
        return self.shalas.add_shala(owner.id, city=city, **kw).id

    def moon_days(self, city: str, *days: date) -> None:
        self.moon.days_by_location[city] = [MoonDay(d, MoonDayKind.PURNIMA) for d in days]

    # The use cases, as the adapters build them.

    def get(self) -> GetSchedule:
        return GetSchedule(self.schedule, self.clock, cities())

    def create(self) -> CreateClass:
        return CreateClass(self.schedule, self.clock, cities())

    def update(self) -> UpdateClass:
        return UpdateClass(self.schedule, self.clock, cities())

    def override(self) -> SetOverride:
        return SetOverride(self.schedule, self.clock)

    def closure(self) -> AddClosure:
        return AddClosure(self.schedule, self.clock)

    def swap(self) -> AddSwap:
        return AddSwap(self.schedule, self.clock)

    def mine(self) -> GetMyClasses:
        return GetMyClasses(self.schedule, self.clock, cities())

    def adopt(self) -> AdoptShalaDayOff:
        return AdoptShalaDayOff(self.shalas, SetDayOff(self.accounts, self.clock))


@pytest.fixture
def world() -> World:
    return World()


@dataclass
class Cast:
    owner: Account
    teacher: Account
    assistant: Account
    office: Account
    admin: Account
    student: Account
    stranger: Account
    shala: UUID


@pytest.fixture
def cast(world: World) -> Cast:
    owner = world.person("1", "Anna")
    shala = world.shala(owner, days_off=frozenset({6}))
    people = {
        role: world.person(str(10 + i), role.value.title())
        for i, role in enumerate((TEACHER, ASSISTANT, OFFICE, ADMIN))
    }
    for role, who in people.items():
        world.shalas.add_staff(shala, who.id, role)
    student, stranger = world.person("20", "Sam"), world.person("21", "Stranger")
    world.shalas.add_student(shala, student.id)
    return Cast(
        owner,
        people[TEACHER],
        people[ASSISTANT],
        people[OFFICE],
        people[ADMIN],
        student,
        stranger,
        shala,
    )


# GetSchedule


async def test_a_week_is_one_window_read_in_the_shalas_zone(world: World, cast: Cast) -> None:
    world.schedule.add_class(cast.shala, teacher_id=cast.teacher.id)
    world.schedule.reads.clear()

    out = await world.get().execute(world.me(cast.student), cast.shala, NOV[9], 7)

    assert world.schedule.reads == ["window"]
    assert out.zone == "Asia/Almaty"
    assert [o.on for o in out.occurrences] == [NOV[d] for d in (9, 10, 11, 12, 13)]
    first = out.occurrences[0]
    assert (first.start, first.end) == (time(6, 0), time(9, 30))
    assert first.starts_at == datetime(2026, 11, 9, 1, 0, tzinfo=UTC)


async def test_the_days_list_marks_the_day_off(world: World, cast: Cast) -> None:
    out = await world.get().execute(world.me(cast.student), cast.shala, NOV[9], 7)

    assert [d.date for d in out.days] == [NOV[d] for d in range(9, 16)]
    assert [d.date for d in out.days if d.day_off] == [NOV[14]]
    assert out.days_off == frozenset({6})


async def test_an_online_class_may_run_in_another_listed_city(world: World, cast: Cast) -> None:
    world.schedule.add_class(
        cast.shala, type=ClassType.LED, online=True, city="berlin", start=time(18, 30), minutes=90
    )

    out = await world.get().execute(world.me(cast.student), cast.shala, NOV[9], 1)

    [o] = out.occurrences
    assert o.starts_at == datetime(2026, 11, 9, 17, 30, tzinfo=UTC)  # 18:30 Berlin (UTC+1)


async def test_private_classes_are_shown_to_staff_only(world: World, cast: Cast) -> None:
    world.schedule.add_class(cast.shala, type=ClassType.PRIVATE, start=time(12, 0), minutes=60)
    world.schedule.add_class(cast.shala)

    seen = {}
    for who in (cast.student, cast.assistant, cast.owner):
        out = await world.get().execute(world.me(who), cast.shala, NOV[9], 1)
        seen[who.display_name] = {o.type for o in out.occurrences}

    assert seen["Sam"] == {ClassType.MYSORE}
    assert seen["Assistant"] == {ClassType.MYSORE, ClassType.PRIVATE}
    assert seen["Anna"] == {ClassType.MYSORE, ClassType.PRIVATE}


async def test_a_non_member_gets_not_found_as_for_an_unknown_shala(
    world: World, cast: Cast
) -> None:
    for shala in (cast.shala, uuid4()):
        with pytest.raises(NotFound):
            await world.get().execute(world.me(cast.stranger), shala, NOV[9], 7)


async def test_members_see_four_weeks(world: World, cast: Cast) -> None:
    world.schedule.add_class(cast.shala)

    out = await world.get().execute(world.me(cast.student), cast.shala, NOV[9], 28)

    assert len(out.occurrences) == 20
    assert out.days[-1].date == date(2026, 12, 6)


@pytest.mark.parametrize("days", [0, 32])
async def test_the_window_is_one_to_31_days(world: World, cast: Cast, days: int) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 (the use case's window error)
        await world.get().execute(world.me(cast.student), cast.shala, NOV[9], days)
    assert world.schedule.reads == []


async def test_bounds_use_the_shalas_local_today_not_the_viewers() -> None:
    """07:30 UTC on 8 Nov: 23:30 on 7 Nov in Los Angeles (the shala), 15:30 on 8 Nov in Bali
    (the viewer). `from` may be 7 days back and 365 ahead of the shala's today."""
    world = World(instant=datetime(2026, 11, 8, 7, 30, tzinfo=UTC))
    owner = world.person("1", "Anna", zone="America/Los_Angeles")
    shala = world.shala(owner, city="los-angeles")
    viewer = world.person("2", "Ash", zone="Asia/Makassar")
    world.shalas.add_student(shala, viewer.id)
    get = world.get()

    for ok in (date(2026, 10, 31), date(2027, 11, 7)):
        await get.execute(world.me(viewer), shala, ok, 1)
    for bad in (date(2026, 10, 30), date(2027, 11, 8)):
        with pytest.raises(ValueError):  # noqa: PT011
            await get.execute(world.me(viewer), shala, bad, 1)


async def test_moon_days_follow_the_policy(world: World, cast: Cast) -> None:
    world.moon_days("almaty", NOV[13])
    world.schedule.add_class(cast.shala)
    world.schedule.add_class(
        cast.shala, type=ClassType.PRANAYAMA, weekdays=frozenset({5}), start=time(7, 0), minutes=60
    )
    row = world.shalas.shalas[cast.shala]

    found: dict[str, dict[ClassType, Reason | None]] = {}
    for policy in ("closed", "pranayama", "open"):
        row.moon_policy = policy
        out = await world.get().execute(world.me(cast.student), cast.shala, NOV[13], 1)
        assert [d.moon for d in out.days] == [True]  # 🌙 shown under every policy
        found[policy] = {o.type: o.cancelled for o in out.occurrences}

    assert found["closed"] == {ClassType.MYSORE: Reason.MOON, ClassType.PRANAYAMA: Reason.MOON}
    assert found["pranayama"] == {ClassType.MYSORE: Reason.MOON, ClassType.PRANAYAMA: None}
    assert found["open"] == {ClassType.MYSORE: None, ClassType.PRANAYAMA: None}


async def test_the_moon_city_is_the_shalas_not_the_viewers(world: World) -> None:
    """A Mysuru-following shala in Almaty cancels on the Mysuru date (MD-02)."""
    owner = world.person("1", "Anna")
    shala = world.shala(owner, moon_city="mysuru")
    world.moon_days("almaty", NOV[12])
    world.moon_days("mysuru", NOV[13])
    world.schedule.add_class(shala)

    out = await world.get().execute(world.me(owner), shala, NOV[12], 2)

    assert {o.on: o.cancelled for o in out.occurrences} == {NOV[12]: None, NOV[13]: Reason.MOON}


async def test_a_swap_shows_on_both_days(world: World, cast: Cast) -> None:
    world.moon_days("almaty", NOV[13])
    mysore = world.schedule.add_class(cast.shala)
    await world.swap().execute(world.me(cast.teacher), cast.shala, NOV[13], NOV[14])

    out = await world.get().execute(world.me(cast.student), cast.shala, NOV[13], 2)

    [moved] = [o for o in out.occurrences if o.class_id == mysore.id]
    assert (moved.key, moved.on, moved.swapped_from) == (NOV[13], NOV[14], NOV[13])
    assert {d.date: d.swap_from for d in out.days} == {NOV[13]: None, NOV[14]: NOV[13]}


# ListClasses, CreateClass, UpdateClass, DeleteClass


@pytest.mark.parametrize("role", [TEACHER, OFFICE, ADMIN])
async def test_staff_who_manage_create_a_class(world: World, cast: Cast, role: ShalaRole) -> None:
    who = {TEACHER: cast.teacher, OFFICE: cast.office, ADMIN: cast.admin}[role]

    created = await world.create().execute(world.me(who), cast.shala, _draft(title="Early"))

    assert (created.type, created.title, created.weekdays) == (
        ClassType.MYSORE,
        "Early",
        MON_FRI,
    )
    assert world.schedule.of(cast.shala) == [created]


async def test_an_assistant_may_not_create(world: World, cast: Cast) -> None:
    with pytest.raises(NotAllowed):
        await world.create().execute(world.me(cast.assistant), cast.shala, _draft())
    assert world.schedule.writes == []


async def test_a_student_may_not_list_classes(world: World, cast: Cast) -> None:
    with pytest.raises(NotAllowed):
        await ListClasses(world.schedule).execute(world.me(cast.student), cast.shala)


async def test_a_non_member_creating_gets_not_found(world: World, cast: Cast) -> None:
    with pytest.raises(NotFound):
        await world.create().execute(world.me(cast.stranger), cast.shala, _draft())


@pytest.mark.parametrize(
    "bad",
    [
        {"minutes": 481},
        {"start": time(22, 0), "minutes": 121},
        {"every": 5},
        {"ends_on": NOV[8]},
        {"weekdays": frozenset[int](), "ends_on": NOV[20]},
        {"city": "berlin"},  # an offline class always runs in the shala's zone (Q124)
    ],
    ids=[
        "481-min",
        "past-midnight",
        "every-5",
        "until-before-from",
        "one-off-until",
        "offline-city",
    ],
)
async def test_an_invalid_class_writes_nothing(
    world: World, cast: Cast, bad: dict[str, Any]
) -> None:
    with pytest.raises(InvalidClass):
        await world.create().execute(world.me(cast.owner), cast.shala, _draft(**bad))
    assert world.schedule.writes == []


async def test_an_unknown_city_is_refused(world: World, cast: Cast) -> None:
    with pytest.raises(UnknownLocation):
        await world.create().execute(
            world.me(cast.owner), cast.shala, _draft(online=True, city="atlantis")
        )


async def test_the_live_series_cap(world: World, cast: Cast) -> None:
    world.schedule.add_class(cast.shala, ends_on=NOV[1], starts_on=date(2026, 10, 1))  # ended
    for _ in range(MAX_CLASSES):
        world.schedule.add_class(cast.shala)

    with pytest.raises(CapReached):
        await world.create().execute(world.me(cast.owner), cast.shala, _draft())


async def test_one_ended_series_does_not_count_toward_the_cap(world: World, cast: Cast) -> None:
    world.schedule.add_class(cast.shala, ends_on=NOV[1], starts_on=date(2026, 10, 1))
    for _ in range(MAX_CLASSES - 1):
        world.schedule.add_class(cast.shala)

    await world.create().execute(world.me(cast.owner), cast.shala, _draft())


async def test_an_edit_from_a_date_splits_and_carries_later_overrides(
    world: World, cast: Cast
) -> None:
    old = world.schedule.add_class(cast.shala, starts_on=NOV[2])
    world.schedule.add_override(old.id, _ov(NOV[6], OverrideStatus.CANCELLED))
    world.schedule.add_override(old.id, _ov(NOV[20], OverrideStatus.CANCELLED))

    new = await world.update().execute(
        world.me(cast.owner),
        cast.shala,
        old.id,
        _draft(start=time(7, 0), starts_on=NOV[2]),
        from_date=NOV[16],
    )

    assert new.id != old.id
    assert new.starts_on == NOV[16]
    rows = {c.id: c for c in world.schedule.of(cast.shala)}
    assert rows[old.id].ends_on == NOV[15]
    out = await world.get().execute(world.me(cast.owner), cast.shala, NOV[2], 28)
    by_day = {o.on: o for o in out.occurrences}
    assert (by_day[NOV[6]].start, by_day[NOV[6]].cancelled) == (time(6, 0), Reason.CANCELLED)
    assert (by_day[NOV[13]].start, by_day[NOV[13]].class_id) == (time(6, 0), old.id)
    assert (by_day[NOV[16]].start, by_day[NOV[16]].class_id) == (time(7, 0), new.id)
    assert (by_day[NOV[20]].cancelled, by_day[NOV[20]].class_id) == (Reason.CANCELLED, new.id)


async def test_an_edit_of_all_dates_keeps_the_id(world: World, cast: Cast) -> None:
    old = world.schedule.add_class(cast.shala)

    new = await world.update().execute(
        world.me(cast.owner), cast.shala, old.id, _draft(minutes=180), from_date=None
    )

    assert (new.id, new.minutes) == (old.id, 180)


async def test_editing_an_unknown_class_is_not_found(world: World, cast: Cast) -> None:
    with pytest.raises(NotFound):
        await world.update().execute(world.me(cast.owner), cast.shala, uuid4(), _draft())


async def test_delete_is_idempotent(world: World, cast: Cast) -> None:
    row = world.schedule.add_class(cast.shala)
    delete = DeleteClass(world.schedule)

    await delete.execute(world.me(cast.teacher), cast.shala, row.id)
    await delete.execute(world.me(cast.teacher), cast.shala, row.id)

    assert world.schedule.of(cast.shala) == []


# Overrides


async def test_cancel_then_restore(world: World, cast: Cast) -> None:
    row = world.schedule.add_class(cast.shala)
    me = world.me(cast.office)

    await world.override().execute(
        me, cast.shala, row.id, NOV[9], _ov(NOV[9], OverrideStatus.CANCELLED)
    )
    cancelled = await world.get().execute(me, cast.shala, NOV[9], 1)
    await ClearOverride(world.schedule).execute(me, cast.shala, row.id, NOV[9])
    restored = await world.get().execute(me, cast.shala, NOV[9], 1)

    assert [o.cancelled for o in cancelled.occurrences] == [Reason.CANCELLED]
    assert [o.cancelled for o in restored.occurrences] == [None]


async def test_hold_anyway_on_a_moon_day(world: World, cast: Cast) -> None:
    world.moon_days("almaty", NOV[13])
    row = world.schedule.add_class(cast.shala)

    await world.override().execute(
        world.me(cast.teacher), cast.shala, row.id, NOV[13], _ov(NOV[13], OverrideStatus.HELD)
    )
    out = await world.get().execute(world.me(cast.student), cast.shala, NOV[13], 1)

    assert [o.cancelled for o in out.occurrences] == [None]


@pytest.mark.parametrize("moved_to", [NOV[9] + timedelta(days=7), NOV[9] - timedelta(days=7)])
async def test_a_move_beyond_six_days_is_invalid(world: World, cast: Cast, moved_to: date) -> None:
    row = world.schedule.add_class(cast.shala)

    with pytest.raises(InvalidClass):
        await world.override().execute(
            world.me(cast.owner), cast.shala, row.id, NOV[9], _ov(NOV[9], moved_to=moved_to)
        )
    assert world.schedule.writes == []


@pytest.mark.parametrize(
    "key", [NOV[5], TODAY + timedelta(days=366)], ids=["before-yesterday", "horizon"]
)
async def test_an_override_outside_today_to_the_horizon_is_invalid(
    world: World, cast: Cast, key: date
) -> None:
    row = world.schedule.add_class(cast.shala, starts_on=NOV[2], weekdays=frozenset(range(1, 8)))

    with pytest.raises(InvalidClass):
        await world.override().execute(
            world.me(cast.owner), cast.shala, row.id, key, _ov(key, OverrideStatus.CANCELLED)
        )


async def test_an_assistant_may_not_cancel(world: World, cast: Cast) -> None:
    row = world.schedule.add_class(cast.shala)

    with pytest.raises(NotAllowed):
        await world.override().execute(
            world.me(cast.assistant),
            cast.shala,
            row.id,
            NOV[9],
            _ov(NOV[9], OverrideStatus.CANCELLED),
        )


# Closures


async def test_a_closure_cancels_and_can_be_removed(world: World, cast: Cast) -> None:
    world.schedule.add_class(cast.shala)
    me = world.me(cast.owner)

    closure = await world.closure().execute(me, cast.shala, NOV[10], NOV[11])
    closed = await world.get().execute(me, cast.shala, NOV[9], 3)
    await RemoveClosure(world.schedule).execute(me, cast.shala, closure.id)
    reopened = await world.get().execute(me, cast.shala, NOV[9], 3)

    assert [o.cancelled for o in closed.occurrences] == [None, Reason.CLOSURE, Reason.CLOSURE]
    assert [o.cancelled for o in reopened.occurrences] == [None, None, None]


@pytest.mark.parametrize(
    ("start", "end"),
    [(NOV[11], NOV[10]), (NOV[10], NOV[10] + timedelta(days=92))],
    ids=["end-before-start", "93-days"],
)
async def test_an_invalid_closure(world: World, cast: Cast, start: date, end: date) -> None:
    with pytest.raises(InvalidClass):
        await world.closure().execute(world.me(cast.owner), cast.shala, start, end)


async def test_a_92_day_closure_is_fine(world: World, cast: Cast) -> None:
    await world.closure().execute(
        world.me(cast.owner), cast.shala, NOV[10], NOV[10] + timedelta(days=91)
    )


async def test_the_future_closure_cap(world: World, cast: Cast) -> None:
    world.schedule.seed_closure(cast.shala, date(2026, 10, 1), date(2026, 10, 2))  # past
    for i in range(MAX_FUTURE_CLOSURES):
        world.schedule.seed_closure(
            cast.shala, NOV[9] + timedelta(days=i), NOV[9] + timedelta(days=i)
        )

    with pytest.raises(CapReached):
        await world.closure().execute(
            world.me(cast.owner), cast.shala, date(2027, 1, 1), date(2027, 1, 2)
        )


# Swaps (Q125)


async def test_a_swap_onto_a_class_day_of_the_same_type_is_invalid(
    world: World, cast: Cast
) -> None:
    world.moon_days("almaty", NOV[13])
    world.schedule.add_class(cast.shala)  # Mon-Fri Mysore: Thu 12 already has one

    with pytest.raises(InvalidClass):
        await world.swap().execute(world.me(cast.owner), cast.shala, NOV[13], NOV[12])
    assert world.schedule.writes == []


async def test_a_swap_onto_a_moon_day_is_invalid(world: World, cast: Cast) -> None:
    world.moon_days("almaty", NOV[13], NOV[14])
    world.schedule.add_class(cast.shala)

    with pytest.raises(InvalidClass):
        await world.swap().execute(world.me(cast.owner), cast.shala, NOV[13], NOV[14])


async def test_removing_a_swap_puts_the_class_back_on_a(world: World, cast: Cast) -> None:
    world.moon_days("almaty", NOV[13])
    world.schedule.add_class(cast.shala)
    me = world.me(cast.owner)
    await world.swap().execute(me, cast.shala, NOV[13], NOV[14])

    await RemoveSwap(world.schedule).execute(me, cast.shala, NOV[13])
    out = await world.get().execute(me, cast.shala, NOV[13], 2)

    assert [(o.on, o.cancelled) for o in out.occurrences] == [(NOV[13], Reason.MOON)]


async def test_the_future_swap_cap(world: World, cast: Cast) -> None:
    from tristhana.domain.classes import Swap

    for i in range(MAX_FUTURE_SWAPS):
        a = NOV[9] + timedelta(days=7 * i)
        world.schedule.swaps[(cast.shala, a)] = Swap(a, a + timedelta(days=1))

    with pytest.raises(CapReached):
        await world.swap().execute(
            world.me(cast.owner), cast.shala, date(2027, 6, 1), date(2027, 6, 5)
        )


async def test_an_assistant_may_not_swap(world: World, cast: Cast) -> None:
    world.moon_days("almaty", NOV[13])
    with pytest.raises(NotAllowed):
        await world.swap().execute(world.me(cast.assistant), cast.shala, NOV[13], NOV[14])


# The shala's day off and moon policy (UpdateShala, `can_edit_shala`)


async def test_the_owner_sets_the_day_off_and_moon_policy(world: World, cast: Cast) -> None:
    patch = ShalaPatch(days_off=frozenset({7}), moon_policy=MoonPolicy.PRANAYAMA)  # pyright: ignore[reportCallIssue]

    card = await UpdateShala(world.shalas, cities()).execute(
        world.me(cast.owner), cast.shala, patch
    )

    assert (card.days_off, card.moon_policy) == (frozenset({7}), MoonPolicy.PRANAYAMA)  # pyright: ignore[reportAttributeAccessIssue]


async def test_a_teacher_may_not_set_the_moon_policy(world: World, cast: Cast) -> None:
    patch = ShalaPatch(moon_policy=MoonPolicy.OPEN)  # pyright: ignore[reportCallIssue]

    with pytest.raises(NotAllowed):
        await UpdateShala(world.shalas, cities()).execute(world.me(cast.teacher), cast.shala, patch)


async def test_at_most_two_days_off(world: World, cast: Cast) -> None:
    patch = ShalaPatch(days_off=frozenset({5, 6, 7}))  # pyright: ignore[reportCallIssue]

    with pytest.raises(InvalidDayOff):
        await UpdateShala(world.shalas, cities()).execute(world.me(cast.owner), cast.shala, patch)


# AdoptShalaDayOff (Q109, Q119)


async def test_a_never_chose_member_adopts_the_shalas_day_off(world: World, cast: Cast) -> None:
    assert cast.student.day_off.days is None

    await world.adopt().execute(world.me(cast.student), cast.shala)

    assert world.accounts.accounts[cast.student.id].day_off.days == frozenset({6})


async def test_someone_who_chose_keeps_their_day_off(world: World, cast: Cast) -> None:
    chosen = DayOff(frozenset({7}))
    world.accounts.accounts[cast.student.id] = replace(cast.student, day_off=chosen)

    await world.adopt().execute(world.me(cast.student), cast.shala)

    assert world.accounts.accounts[cast.student.id].day_off == chosen


async def test_no_shala_day_off_writes_nothing(world: World, cast: Cast) -> None:
    world.shalas.shalas[cast.shala].days_off = None

    await world.adopt().execute(world.me(cast.student), cast.shala)

    assert world.accounts.accounts[cast.student.id].day_off.days is None


async def test_adopting_from_a_shala_i_am_not_in_is_not_found(world: World, cast: Cast) -> None:
    with pytest.raises(NotFound):
        await world.adopt().execute(world.me(cast.stranger), cast.shala)
    assert world.accounts.accounts[cast.stranger.id].day_off.days is None


# No log data


def test_no_class_use_case_reads_a_log() -> None:
    import tristhana.application.classes as module

    tree = ast.parse(Path(module.__file__).read_text())
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    banned = {
        "tristhana.application.ports.days",
        "tristhana.application.ports.practice",
        "tristhana.application.ports.progression",
        "tristhana.application.ports.check_in",
        "tristhana.application.ports.diary",
        "tristhana.application.ports.teacher_view",
        "tristhana.application.days",
        "tristhana.application.practice",
        "tristhana.application.progression",
        "dateutil",
    }
    assert imported & banned == set()
    assert not any(name.startswith("dateutil") for name in imported)


# GetMyClasses: the teacher's own week across their shalas


async def test_my_classes_are_the_next_week_of_mine_in_one_read(world: World, cast: Cast) -> None:
    world.schedule.add_class(cast.shala, teacher_id=cast.teacher.id)
    world.schedule.add_class(cast.shala, type=ClassType.LED, teacher_id=cast.assistant.id)
    world.schedule.reads.clear()

    out = await world.mine().execute(world.me(cast.teacher))

    assert world.schedule.reads == ["staff_windows"]
    [shala] = out
    assert (shala.shala_id, shala.zone, shala.today) == (cast.shala, "Asia/Almaty", TODAY)
    assert [c.occurrence.on for c in shala.classes] == [NOV[d] for d in (9, 10, 11, 12, 13)]
    assert {c.occurrence.type for c in shala.classes} == {ClassType.MYSORE}
    assert {c.role for c in shala.classes} == {Teaching.TEACHING}


async def test_a_substitute_covers_and_the_usual_teacher_sees_it(world: World, cast: Cast) -> None:
    mysore = world.schedule.add_class(cast.shala, teacher_id=cast.teacher.id)
    world.schedule.add_override(mysore.id, _ov(NOV[10], teacher_id=cast.office.id))

    teacher = await world.mine().execute(world.me(cast.teacher))
    office = await world.mine().execute(world.me(cast.office))

    roles = {c.occurrence.on: c.role for c in teacher[0].classes}
    assert roles[NOV[10]] is Teaching.COVERED
    assert roles[NOV[9]] is Teaching.TEACHING
    [covering] = office[0].classes
    assert (covering.occurrence.on, covering.role) == (NOV[10], Teaching.COVERING)
    assert office[0].staff[cast.teacher.id] == "Teacher"


async def test_cancelled_classes_stay_with_their_reason(world: World, cast: Cast) -> None:
    world.moon_days("almaty", NOV[11])
    world.schedule.add_class(cast.shala, teacher_id=cast.teacher.id)

    [shala] = await world.mine().execute(world.me(cast.teacher))

    cancelled = {c.occurrence.on: c.occurrence.cancelled for c in shala.classes}
    assert cancelled[NOV[11]] is Reason.MOON
    assert cancelled[NOV[10]] is None


async def test_no_classes_of_mine_and_no_staff_seat_read_as_nothing(
    world: World, cast: Cast
) -> None:
    world.schedule.add_class(cast.shala, teacher_id=cast.teacher.id)

    assert await world.mine().execute(world.me(cast.assistant)) == ()
    assert await world.mine().execute(world.me(cast.student)) == ()
    assert await world.mine().execute(world.me(cast.stranger)) == ()


async def test_every_staff_shala_is_read_by_name_in_its_own_today(world: World) -> None:
    teacher = world.person("30", "Tara")
    owner = world.person("31", "Olga")
    west = world.shala(owner, city="los-angeles", name="B Los Angeles")
    almaty = world.shala(owner, name="A Almaty")
    for shala in (west, almaty):
        world.shalas.add_staff(shala, teacher.id, TEACHER)
        world.schedule.add_class(
            shala, teacher_id=teacher.id, weekdays=frozenset(range(1, 8)), starts_on=NOV[1]
        )

    out = await world.mine().execute(world.me(teacher))

    assert [s.shala_id for s in out] == [almaty, west]
    assert [s.today for s in out] == [NOV[7], NOV[6]]  # 06:00 UTC: still Friday in Los Angeles
    assert out[1].classes[0].occurrence.on == NOV[6]
    assert len(out[0].classes) == 7


async def test_a_substitute_on_a_held_moon_day_keeps_the_hold(world: World, cast: Cast) -> None:
    world.moon_days("almaty", NOV[11])
    mysore = world.schedule.add_class(cast.shala, teacher_id=cast.teacher.id)
    me = world.me(cast.owner)
    await world.override().execute(
        me, cast.shala, mysore.id, NOV[11], _ov(NOV[11], OverrideStatus.HELD)
    )

    sub = _ov(NOV[11], OverrideStatus.HELD, teacher_id=cast.assistant.id)
    await world.override().execute(me, cast.shala, mysore.id, NOV[11], sub)

    out = await world.get().execute(me, cast.shala, NOV[11], 1)
    [o] = out.occurrences
    assert (o.cancelled, o.held, o.teacher_id, o.substitute) == (
        None,
        True,
        cast.assistant.id,
        True,
    )


async def test_my_week_is_the_shalas_dates_for_an_online_class_elsewhere(
    world: World, cast: Cast
) -> None:
    # 20:00 in Los Angeles: the next morning in Almaty (UTC+5 vs UTC-8).
    world.schedule.add_class(
        cast.shala, teacher_id=cast.teacher.id, online=True, city="los-angeles",
        start=time(20, 0), minutes=60, weekdays=frozenset(range(1, 8)), starts_on=NOV[1],
    )  # fmt: skip

    [shala] = await world.mine().execute(world.me(cast.teacher))

    local = [c.occurrence.starts_at.astimezone(ZoneInfo("Asia/Almaty")) for c in shala.classes]
    assert [d.date() for d in local] == [NOV[d] for d in range(7, 14)]
    assert {d.hour for d in local} == {9}
