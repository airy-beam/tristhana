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
    GetSchedule,
    ListClasses,
    RemoveClosure,
    RemoveSwap,
    SetOverride,
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
    ClassPatch,
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


async def test_a_title_is_kept_on_one_line(world: World, cast: Cast) -> None:
    """SC-05 review: line breaks and runs of spaces collapse (titles head the bot roster)."""
    draft = _draft(title="  Led\nPrimary \t  count ")
    created = await world.create().execute(world.me(cast.teacher), cast.shala, draft)
    assert created.title == "Led Primary count"


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
        world.me(cast.owner), cast.shala, old.id, ClassPatch(start=time(7, 0)), from_date=NOV[16]
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
        world.me(cast.owner), cast.shala, old.id, ClassPatch(minutes=180), from_date=None
    )

    assert (new.id, new.minutes) == (old.id, 180)


async def test_editing_an_unknown_class_is_not_found(world: World, cast: Cast) -> None:
    world.schedule.add_class(cast.shala)
    world.schedule.reads.clear()

    with pytest.raises(NotFound):
        await world.update().execute(
            world.me(cast.owner), cast.shala, uuid4(), ClassPatch(minutes=180)
        )

    assert (world.schedule.reads, world.schedule.writes) == (["classes_of"], [])


async def test_an_edit_before_the_first_class_changes_whole(world: World, cast: Cast) -> None:
    """Review fix: Mondays, first date set to Tue 3 Nov, so the first class is Mon 9 Nov.
    Changed "from 9 Nov" before it has ever run: there is nothing earlier to keep, so the
    row itself changes. No predecessor with no dates is left behind. The row now starts on
    the date asked, so a new weekday (Wednesday) adds no class on a day already past."""
    old = world.schedule.add_class(cast.shala, weekdays=frozenset({1}), starts_on=NOV[3])
    patch = ClassPatch(start=time(7, 0), weekdays=frozenset({1, 3}))

    new = await world.update().execute(
        world.me(cast.owner), cast.shala, old.id, patch, from_date=NOV[9]
    )

    assert (new.id, new.start, new.starts_on, new.ends_on) == (old.id, time(7, 0), NOV[9], None)
    assert world.schedule.of(cast.shala) == [new]
    out = await world.get().execute(world.me(cast.owner), cast.shala, NOV[2], 14)
    assert [o.on for o in out.occurrences] == [NOV[9], NOV[11]]  # no Wed 4 Nov


async def test_an_edit_after_the_first_class_still_splits(world: World, cast: Cast) -> None:
    old = world.schedule.add_class(cast.shala, weekdays=frozenset({1}), starts_on=NOV[3])

    new = await world.update().execute(
        world.me(cast.owner), cast.shala, old.id, ClassPatch(start=time(7, 0)), from_date=NOV[10]
    )

    assert new.id != old.id
    assert len(world.schedule.of(cast.shala)) == 2


async def test_a_stale_edit_from_an_earlier_date_does_not_double_the_class(
    world: World, cast: Cast, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review fix: two people edit the same class. The first applies "from 23 Nov" between
    the second's read and write; the second asks "from 16 Nov" with the row as it was read
    (no last date). The write requires the last date that was read: `NotFound`, and no
    second successor running beside the first from 23 Nov."""
    old = world.schedule.add_class(cast.shala, starts_on=NOV[2])
    read = world.schedule.classes_of

    async def then_someone_else_saves(shala: UUID, me: UUID) -> Any:
        found = await read(shala, me)
        monkeypatch.setattr(world.schedule, "classes_of", read)
        await world.update().execute(
            world.me(cast.teacher), shala, old.id, ClassPatch(start=time(7, 0)), NOV[23]
        )
        return found

    monkeypatch.setattr(world.schedule, "classes_of", then_someone_else_saves)

    with pytest.raises(NotFound):
        await world.update().execute(
            world.me(cast.owner), cast.shala, old.id, ClassPatch(minutes=180), from_date=NOV[16]
        )

    spans = sorted((c.starts_on, c.ends_on, c.minutes) for c in world.schedule.of(cast.shala))
    assert spans == [(NOV[2], NOV[22], 210), (NOV[23], None, 210)]


# UI-06 stage 4 (spec §3, §6; ADR-0048): the use case owns the read and the merge, an edit
# applies from a date, and the past is not rewritten.


async def test_only_the_sent_fields_change(world: World, cast: Cast) -> None:
    old = world.schedule.add_class(
        cast.shala,
        type=ClassType.LED,
        title="Led Primary",
        online=True,
        city="berlin",
        teacher_id=cast.teacher.id,
        start=time(7, 30),
        minutes=90,
        weekdays=frozenset({5}),
        every=2,
        starts_on=NOV[13],
        ends_on=date(2027, 3, 26),
    )
    world.schedule.reads.clear()

    new = await world.update().execute(
        world.me(cast.office), cast.shala, old.id, ClassPatch(minutes=105)
    )

    assert new == replace(old, minutes=105)
    assert world.schedule.reads == ["classes_of", "update"]  # with the account: 3 statements


async def test_a_patch_may_change_every_field(world: World, cast: Cast) -> None:
    old = world.schedule.add_class(cast.shala, starts_on=NOV[9])
    patch = ClassPatch(
        type=ClassType.PRANAYAMA,
        title="  Sunday  breath ",
        online=True,
        city="berlin",
        teacher_id=cast.teacher.id,
        start=time(18, 0),
        minutes=60,
        weekdays=frozenset({7}),
        every=3,
        starts_on=NOV[15],
        ends_on=date(2027, 1, 31),
    )

    new = await world.update().execute(world.me(cast.owner), cast.shala, old.id, patch)

    assert new == replace(
        old,
        type=ClassType.PRANAYAMA,
        title="Sunday breath",
        online=True,
        city="berlin",
        teacher_id=cast.teacher.id,
        start=time(18, 0),
        minutes=60,
        weekdays=frozenset({7}),
        every=3,
        starts_on=NOV[15],
        ends_on=date(2027, 1, 31),
    )


async def test_null_clears_the_four_fields_that_may_be_empty(world: World, cast: Cast) -> None:
    old = world.schedule.add_class(
        cast.shala,
        title="Early",
        online=True,
        city="berlin",
        teacher_id=cast.teacher.id,
        ends_on=date(2027, 1, 31),
    )

    new = await world.update().execute(
        world.me(cast.owner),
        cast.shala,
        old.id,
        ClassPatch(title=None, city=None, teacher_id=None, ends_on=None),
    )

    assert (new.title, new.city, new.teacher_id, new.ends_on) == (None, None, None, None)
    assert (new.id, new.online, new.start, new.weekdays) == (old.id, True, old.start, MON_FRI)


async def test_the_merged_class_is_checked_as_a_whole(world: World, cast: Cast) -> None:
    """A field that is fine by itself can break the stored rest: 22:00 plus the stored 210
    minutes runs past midnight; a city on a class that is not online has no meaning."""
    old = world.schedule.add_class(cast.shala)

    for patch in (ClassPatch(start=time(22, 0)), ClassPatch(city="berlin"), ClassPatch(every=5)):
        with pytest.raises(InvalidClass):
            await world.update().execute(world.me(cast.owner), cast.shala, old.id, patch)
    with pytest.raises(UnknownLocation):
        await world.update().execute(
            world.me(cast.owner), cast.shala, old.id, ClassPatch(online=True, city="atlantis")
        )

    assert world.schedule.writes == []
    assert world.schedule.of(cast.shala) == [old]


async def test_who_may_edit_a_class(world: World, cast: Cast) -> None:
    """Q118, unchanged: the owner, a manager, a teacher and the front desk; an assistant and
    a student are refused before anything is read back, a stranger sees no shala."""
    old = world.schedule.add_class(cast.shala)
    patch = ClassPatch(minutes=180)

    for who in (cast.owner, cast.admin, cast.teacher, cast.office):
        await world.update().execute(world.me(who), cast.shala, old.id, patch)
    for who in (cast.assistant, cast.student):
        with pytest.raises(NotAllowed):
            await world.update().execute(world.me(who), cast.shala, old.id, patch)
    with pytest.raises(NotFound):
        await world.update().execute(world.me(cast.stranger), cast.shala, old.id, patch)

    assert world.schedule.writes == ["update"] * 4


async def test_a_class_of_another_shala_is_not_found(world: World, cast: Cast) -> None:
    other = world.shala(world.person("30", "Boris"))
    theirs = world.schedule.add_class(other)

    with pytest.raises(NotFound):
        await world.update().execute(
            world.me(cast.owner), cast.shala, theirs.id, ClassPatch(minutes=180)
        )

    assert world.schedule.of(other) == [theirs]


async def test_a_split_keeps_the_fields_that_were_not_sent(world: World, cast: Cast) -> None:
    old = world.schedule.add_class(
        cast.shala, title="Early", teacher_id=cast.teacher.id, starts_on=NOV[2]
    )

    new = await world.update().execute(
        world.me(cast.owner), cast.shala, old.id, ClassPatch(start=time(7, 0)), from_date=NOV[16]
    )

    assert new == replace(old, id=new.id, start=time(7, 0), starts_on=NOV[16])
    rows = {c.id: c for c in world.schedule.of(cast.shala)}
    assert rows[old.id] == replace(old, ends_on=NOV[15])  # the past is not rewritten


async def test_a_sent_start_date_does_not_move_a_split(world: World, cast: Cast) -> None:
    """With `from` on a running class the successor starts on `from`, whatever was sent."""
    old = world.schedule.add_class(cast.shala, starts_on=NOV[2])

    new = await world.update().execute(
        world.me(cast.owner),
        cast.shala,
        old.id,
        ClassPatch(starts_on=NOV[23], minutes=180),
        from_date=NOV[16],
    )

    assert (new.id != old.id, new.starts_on) == (True, NOV[16])


async def test_a_series_ended_before_the_date_is_gone_for_this_edit(
    world: World, cast: Cast
) -> None:
    """D3: another staff member split it a moment ago. No second successor, no misleading
    422: the class is gone for this edit (404), whether a last date was sent or not."""
    ended = world.schedule.add_class(cast.shala, starts_on=NOV[2], ends_on=NOV[8])
    world.schedule.add_class(cast.shala, starts_on=NOV[9], start=time(7, 0))  # its successor
    before = world.schedule.of(cast.shala)

    for patch in (ClassPatch(minutes=180), ClassPatch(minutes=180, ends_on=date(2027, 1, 31))):
        with pytest.raises(NotFound):
            await world.update().execute(
                world.me(cast.owner), cast.shala, ended.id, patch, from_date=NOV[9]
            )

    assert world.schedule.of(cast.shala) == before
    assert world.schedule.writes == []


async def test_a_series_ending_on_the_date_itself_still_splits(world: World, cast: Cast) -> None:
    old = world.schedule.add_class(cast.shala, starts_on=NOV[2], ends_on=NOV[9])

    new = await world.update().execute(
        world.me(cast.owner), cast.shala, old.id, ClassPatch(minutes=180), from_date=NOV[9]
    )

    assert (new.starts_on, new.ends_on, new.minutes) == (NOV[9], NOV[9], 180)
    rows = {c.id: c for c in world.schedule.of(cast.shala)}
    assert rows[old.id].ends_on == NOV[8]


async def test_a_last_date_before_the_split_is_refused(world: World, cast: Cast) -> None:
    old = world.schedule.add_class(cast.shala, starts_on=NOV[2])

    with pytest.raises(InvalidClass):
        await world.update().execute(
            world.me(cast.owner), cast.shala, old.id, ClassPatch(ends_on=NOV[10]), NOV[16]
        )

    assert world.schedule.writes == []


@pytest.mark.parametrize("from_date", [NOV[5], date(2027, 11, 8)])
async def test_the_date_is_bounded_by_the_callers_today(
    world: World, cast: Cast, from_date: date
) -> None:
    """[yesterday, today + 365] by the caller's date (Sat 7 Nov): the past is not rewritten
    from further back either."""
    old = world.schedule.add_class(cast.shala, starts_on=date(2026, 10, 5))

    with pytest.raises(InvalidClass):
        await world.update().execute(
            world.me(cast.owner), cast.shala, old.id, ClassPatch(minutes=180), from_date
        )

    assert world.schedule.writes == []


@pytest.mark.parametrize("from_date", [NOV[6], NOV[9]])
async def test_a_class_that_has_not_started_changes_whole(
    world: World, cast: Cast, from_date: date
) -> None:
    """`from` on or before the start: nothing to keep, so the id and the start stay."""
    old = world.schedule.add_class(cast.shala, starts_on=NOV[9])

    new = await world.update().execute(
        world.me(cast.owner), cast.shala, old.id, ClassPatch(start=time(7, 0)), from_date
    )

    assert new == replace(old, start=time(7, 0))
    assert world.schedule.of(cast.shala) == [new]


async def test_a_one_off_changes_whole(world: World, cast: Cast) -> None:
    old = world.schedule.add_class(
        cast.shala, type=ClassType.WORKSHOP, weekdays=frozenset[int](), starts_on=NOV[6]
    )

    new = await world.update().execute(
        world.me(cast.owner), cast.shala, old.id, ClassPatch(minutes=120), from_date=NOV[7]
    )

    assert new == replace(old, minutes=120)
    assert world.schedule.of(cast.shala) == [new]


@pytest.mark.parametrize(
    ("asked", "written"),
    [(NOV[9], NOV[16]), (NOV[13], NOV[16]), (NOV[16], NOV[16]), (NOV[18], NOV[18])],
)
async def test_every_two_weeks_keeps_its_rhythm_through_a_split(
    world: World, cast: Cast, asked: date, written: date
) -> None:
    """D2: Mondays every 2 weeks from 2 Nov run on 2, 16 and 30 Nov. Asked from the off week
    of 9 Nov, the successor starts in the next week of the rule, so 16 and 30 Nov stay."""
    old = world.schedule.add_class(cast.shala, weekdays=frozenset({1}), every=2, starts_on=NOV[2])
    before = await world.get().execute(world.me(cast.owner), cast.shala, NOV[2], 31)

    new = await world.update().execute(
        world.me(cast.owner), cast.shala, old.id, ClassPatch(start=time(7, 0)), from_date=asked
    )

    assert new.starts_on == written
    after = await world.get().execute(world.me(cast.owner), cast.shala, NOV[2], 31)
    assert [o.on for o in after.occurrences] == [o.on for o in before.occurrences]
    assert [(o.on, o.start) for o in after.occurrences] == [
        (day, time(7, 0) if day >= asked else time(6, 0)) for day in (NOV[2], NOV[16], NOV[30])
    ]


async def test_a_new_interval_counts_from_the_date_asked(world: World, cast: Cast) -> None:
    old = world.schedule.add_class(cast.shala, weekdays=frozenset({1}), every=2, starts_on=NOV[2])

    new = await world.update().execute(
        world.me(cast.owner), cast.shala, old.id, ClassPatch(every=1), from_date=NOV[9]
    )

    assert (new.starts_on, new.every) == (NOV[9], 1)


async def test_a_series_that_ends_in_its_off_week_has_nothing_left_to_change(
    world: World, cast: Cast
) -> None:
    """Every 2 weeks, last date Wed 11 Nov, asked from Mon 9 Nov: the rule has no date left
    from there on, and its next week (16 Nov) is past the end. Gone for this edit."""
    old = world.schedule.add_class(
        cast.shala, weekdays=frozenset({1}), every=2, starts_on=NOV[2], ends_on=NOV[11]
    )

    with pytest.raises(NotFound):
        await world.update().execute(
            world.me(cast.owner), cast.shala, old.id, ClassPatch(minutes=180), from_date=NOV[9]
        )

    assert world.schedule.of(cast.shala) == [old]


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


@pytest.mark.parametrize(
    ("starts_on", "ends_on"), [(NOV[2], NOV[8]), (NOV[16], None)], ids=["ended", "not-started"]
)
async def test_a_date_outside_the_series_is_not_found_and_writes_nothing(
    world: World, cast: Cast, starts_on: date, ends_on: date | None
) -> None:
    """Review fix (ADR-0048): an old id after "change from a date" names a series that ended
    the day before. Its later dates belong to the successor: no orphan override on the old
    id, and a restore says the same, so every adapter can show "this class has changed"."""
    row = world.schedule.add_class(cast.shala, starts_on=starts_on, ends_on=ends_on)
    me = world.me(cast.teacher)

    with pytest.raises(NotFound):
        await world.override().execute(
            me, cast.shala, row.id, NOV[9], _ov(NOV[9], OverrideStatus.CANCELLED)
        )
    with pytest.raises(NotFound):
        await ClearOverride(world.schedule).execute(me, cast.shala, row.id, NOV[9])

    assert world.schedule.overrides == {}
    assert world.schedule.writes == []


async def test_a_restore_with_nothing_to_restore_is_quiet(world: World, cast: Cast) -> None:
    row = world.schedule.add_class(cast.shala)

    await ClearOverride(world.schedule).execute(world.me(cast.office), cast.shala, row.id, NOV[9])

    assert world.schedule.writes == []


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


# A substitute on a held moon day (SC-02; SC-03 moves "My classes" to test_my_schedule.py)


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
