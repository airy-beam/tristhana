"""`GetMySchedule` on fakes (SC-03 spec §3, §7, §8; ADR-0035): one `member_windows` read over
[start - 2, end + 2] in the viewer's dates; rows bucketed by the viewer's local date of the
instant; filters all / teachers / mine; 1:1 only from the shalas where I am staff; a followed
teacher seen only through shalas I joined (Q135); the unknown-zone fallback (Q141); my own
moon day from `moon_follow_of` (MD-02 inheritance included), independent of each shala's moon
rows; the ⚠ shifts of the shown class zones (Q140). A frozen clock.

Also the SC-02 "My classes" cases, now `only=Only.MINE` (Q137: `GetMyClasses` and
`staff_windows` go away).

Shapes from the spec (`application/classes.py`): `Only(StrEnum)` ALL/TEACHERS/MINE;
`MyRow(shala_id, occurrence, zone, city, role, my_teacher)`; `MyDay(date, my_moon)`;
`ShalaRef(id, name, city, zone, staff)`; `MySchedule(zone, zone_known, today, days, shalas,
has_teachers, is_staff, rows, shifts, staff)`; `GetMySchedule(schedule, clock, cities)` (as
`GetMyClasses`), `execute(principal, start, days=7, skip=0, only=Only.ALL)`.
"""

import ast
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from tests.fakes import FixedClock, InMemoryMoon, cities
from tests.moon_follow_fakes import person
from tests.schedule_fakes import InMemorySchedule
from tests.shala_fakes import InMemoryShalas, ShalaAccounts, ShalaLinks
from tristhana.application.classes import (
    BadWindow,
    GetMySchedule,
    MySchedule,
    Only,
    Teaching,
)
from tristhana.application.policies import Principal
from tristhana.domain.accounts import Account, moon_follow_of
from tristhana.domain.classes import ClassType, Override, OverrideStatus, Reason, Shift, Swap
from tristhana.domain.moon import FOLLOW_TEACHER, MoonDay, MoonDayKind
from tristhana.domain.shalas import ShalaRole

NOW = datetime(2026, 11, 9, 3, 0, tzinfo=UTC)  # Mon 9 Nov, 08:00 in Almaty
NOV = {d: date(2026, 11, d) for d in range(1, 31)}
EVERY_DAY = frozenset(range(1, 8))
ALMATY, BERLIN = "Asia/Almaty", "Europe/Berlin"


def _ov(on: date, status: OverrideStatus | None = None, **kw: Any) -> Override:
    values: dict[str, Any] = {"moved_to": None, "start": None, "minutes": None, "teacher_id": None}
    values.update(kw)
    return Override(on_date=on, status=status, **values)


@dataclass
class World:
    instant: datetime = NOW
    clock: FixedClock = field(init=False)
    accounts: ShalaAccounts = field(init=False)
    links: ShalaLinks = field(init=False)
    shalas: InMemoryShalas = field(init=False)
    moon: InMemoryMoon = field(init=False)
    schedule: InMemorySchedule = field(init=False)

    def __post_init__(self) -> None:
        self.clock = FixedClock(self.instant)
        self.accounts = ShalaAccounts(clock=self.clock)
        self.links = ShalaLinks(self.accounts)
        self.shalas = InMemoryShalas(self.accounts, self.links)
        self.links.shalas = self.shalas
        self.accounts.links = self.links
        self.accounts.shalas = self.shalas
        self.moon = InMemoryMoon()
        self.schedule = InMemorySchedule(self.shalas, self.moon)

    def person(
        self, telegram_id: str, name: str = "Person", zone: str | None = ALMATY, **kw: Any
    ) -> Account:
        return person(self.accounts, telegram_id, name, zone=zone, **kw)

    def me(self, account: Account) -> Principal:
        return Principal(self.accounts.inputs(self.accounts.accounts[account.id]))

    def shala(self, owner: Account, city: str = "almaty", **kw: Any) -> UUID:
        return self.shalas.add_shala(owner.id, city=city, **kw).id

    def moon_days(self, city: str, *days: date) -> None:
        self.moon.days_by_location[city] = [MoonDay(d, MoonDayKind.PURNIMA) for d in days]

    def link(self, student: Account, teacher: Account, primary: bool = True) -> None:
        self.links.add(student.id, teacher.id, primary=primary)

    def mine(self) -> GetMySchedule:
        return GetMySchedule(self.schedule, self.clock, cities())

    async def read(self, who: Account, start: date | None = None, **kw: Any) -> MySchedule:
        return await self.mine().execute(self.me(who), start, **kw)


@pytest.fixture
def world() -> World:
    return World()


@dataclass
class Cast:
    """Ashtanga Almaty (Anna owns it): Sam a student, Tara on the staff; Boris teaches there
    too. Sam follows Anna (linked teacher)."""

    anna: Account
    boris: Account
    tara: Account
    sam: Account
    shala: UUID


@pytest.fixture
def cast(world: World) -> Cast:
    anna = world.person("1", "Anna")
    boris = world.person("2", "Boris")
    tara = world.person("3", "Tara")
    sam = world.person("4", "Sam")
    shala = world.shala(anna, name="Ashtanga Almaty")
    world.shalas.add_staff(shala, boris.id, ShalaRole.TEACHER)
    world.shalas.add_staff(shala, tara.id, ShalaRole.TEACHER)
    world.shalas.add_student(shala, sam.id)
    world.link(sam, anna)
    return Cast(anna, boris, tara, sam, shala)


def _on(s: MySchedule, zone: str | None = None) -> list[date]:
    here = ZoneInfo(zone or s.zone)
    return [r.occurrence.starts_at.astimezone(here).date() for r in s.rows]


# The read and the window


async def test_a_week_is_one_read_in_my_zone(world: World, cast: Cast) -> None:
    world.schedule.add_class(cast.shala, teacher_id=cast.anna.id)
    world.schedule.reads.clear()

    out = await world.read(cast.sam)

    assert world.schedule.reads == ["member_windows"]
    assert (out.zone, out.zone_known, out.today) == (ALMATY, True, NOV[9])
    assert [d.date for d in out.days] == [NOV[d] for d in range(9, 16)]
    assert _on(out) == [NOV[d] for d in (9, 10, 11, 12, 13)]
    first = out.rows[0]
    assert (first.shala_id, first.zone, first.city) == (cast.shala, ALMATY, "almaty")
    assert first.occurrence.starts_at == datetime(2026, 11, 9, 1, 0, tzinfo=UTC)
    [ref] = out.shalas
    assert (ref.id, ref.name, ref.city, ref.zone, ref.staff) == (
        cast.shala,
        "Ashtanga Almaty",
        "almaty",
        ALMATY,
        False,
    )
    assert out.staff[cast.shala][cast.anna.id] == "Anna"


async def test_the_read_spans_two_days_either_side(world: World, cast: Cast) -> None:
    await world.read(cast.sam, NOV[16], days=3)

    [(me, start, end, staff_only, _)] = world.schedule.member_calls
    assert (me, start, end, staff_only) == (cast.sam.id, NOV[14], NOV[20], False)


async def test_the_default_start_is_my_today_plus_skip(world: World, cast: Cast) -> None:
    """03:00 UTC on Mon 9 Nov is still Sun 8 Nov, 19:00 in Los Angeles."""
    viewer = world.person("9", "Lee", zone="America/Los_Angeles")
    world.shalas.add_student(cast.shala, viewer.id)

    now = await world.read(viewer)
    later = await world.read(viewer, skip=14)

    assert now.today == NOV[8]
    assert now.days[0].date == NOV[8]
    assert later.days[0].date == NOV[22]


@pytest.mark.parametrize("start", [NOV[2], date(2027, 11, 9)], ids=["today-7", "today+365"])
async def test_the_start_bounds_are_inclusive_in_my_dates(
    world: World, cast: Cast, start: date
) -> None:
    out = await world.read(cast.sam, start, days=1)

    assert [d.date for d in out.days] == [start]


@pytest.mark.parametrize(
    ("start", "days"),
    [(NOV[1], 7), (date(2027, 11, 10), 1), (NOV[9], 0), (NOV[9], 8)],
    ids=["today-8", "today+366", "0-days", "8-days"],
)
async def test_a_bad_window(world: World, cast: Cast, start: date, days: int) -> None:
    with pytest.raises(BadWindow):
        await world.read(cast.sam, start, days=days)


async def test_no_membership_reads_as_nothing(world: World) -> None:
    lone = world.person("50", "Lone")

    out = await world.read(lone)

    assert (out.rows, out.shalas, out.shifts) == ((), (), ())
    assert (out.is_staff, out.zone_known) == (False, True)


# Bucketing by my local date


async def test_rows_sit_under_my_date_of_the_instant(world: World, cast: Cast) -> None:
    """A Berlin online class at 22:00 is 02:00 the next day in Almaty: Sunday's falls into a
    Monday-only window, Monday's does not."""
    world.schedule.add_class(
        cast.shala, type=ClassType.LED, online=True, city="berlin", start=time(22, 0),
        minutes=60, weekdays=frozenset({1, 7}), starts_on=NOV[1],
    )  # fmt: skip

    out = await world.read(cast.sam, NOV[9], days=1)

    [row] = out.rows
    assert (row.occurrence.on, row.zone, row.city) == (NOV[8], BERLIN, "berlin")
    assert row.occurrence.starts_at == datetime(2026, 11, 8, 21, 0, tzinfo=UTC)


async def test_a_viewer_behind_the_shala_sees_the_class_on_the_day_before(
    world: World, cast: Cast
) -> None:
    """06:00 Tue 10 Nov in Almaty is 17:00 Mon 9 Nov in Los Angeles."""
    viewer = world.person("9", "Lee", zone="America/Los_Angeles")
    world.shalas.add_student(cast.shala, viewer.id)
    world.schedule.add_class(cast.shala, weekdays=frozenset({2}))

    out = await world.read(viewer, NOV[9], days=1)

    [row] = out.rows
    assert row.occurrence.on == NOV[10]
    assert out.zone == "America/Los_Angeles"


async def test_rows_of_all_shalas_are_sorted_by_instant(world: World, cast: Cast) -> None:
    berlin = world.shala(cast.boris, city="berlin", name="Yoga Berlin")
    world.shalas.add_student(berlin, cast.sam.id)
    world.schedule.add_class(cast.shala, start=time(6, 0))  # 01:00 UTC
    world.schedule.add_class(berlin, type=ClassType.LED, start=time(7, 0), minutes=90)  # 06:00
    world.schedule.add_class(cast.shala, type=ClassType.PRANAYAMA, start=time(9, 0), minutes=60)

    out = await world.read(cast.sam, NOV[9], days=1)

    instants = [r.occurrence.starts_at for r in out.rows]
    assert instants == sorted(instants)
    assert [r.shala_id for r in out.rows] == [cast.shala, cast.shala, berlin]
    assert {r.shala_id: r.city for r in out.rows} == {cast.shala: "almaty", berlin: "berlin"}


# Filters and marks


async def test_the_filters(world: World, cast: Cast) -> None:
    """Sam teaches at a second shala of his own; Anna is his teacher, Boris is not."""
    world.shalas.add_staff(cast.shala, cast.sam.id, ShalaRole.ASSISTANT)
    own = world.shala(cast.sam, name="Sam's Room")
    world.schedule.add_class(cast.shala, teacher_id=cast.anna.id)
    world.schedule.add_class(
        cast.shala, type=ClassType.LED, teacher_id=cast.boris.id, start=time(18, 0), minutes=90
    )
    world.schedule.add_class(
        own, type=ClassType.PRANAYAMA, teacher_id=cast.sam.id, start=time(12, 0), minutes=60
    )

    found = {
        only: await world.read(cast.sam, NOV[9], days=1, only=only)
        for only in (Only.ALL, Only.TEACHERS, Only.MINE)
    }

    assert {r.occurrence.type for r in found[Only.ALL].rows} == {
        ClassType.MYSORE,
        ClassType.LED,
        ClassType.PRANAYAMA,
    }
    assert [r.occurrence.type for r in found[Only.TEACHERS].rows] == [ClassType.MYSORE]
    assert [(r.occurrence.type, r.role) for r in found[Only.MINE].rows] == [
        (ClassType.PRANAYAMA, Teaching.TEACHING)
    ]
    for out in found.values():  # the flags and shalas do not depend on the filter
        assert (out.has_teachers, out.is_staff) == (True, True)
        assert {s.id for s in out.shalas} == {cast.shala, own}


def test_the_filter_wire_names() -> None:
    assert [o.value for o in Only] == ["all", "teachers", "mine"]


async def test_my_teacher_marks_the_dates_my_teacher_teaches(world: World, cast: Cast) -> None:
    """Anna substitutes on Boris's Tuesday: that date's row is my teacher's."""
    led = world.schedule.add_class(
        cast.shala, type=ClassType.LED, teacher_id=cast.boris.id, start=time(18, 0), minutes=90
    )
    world.schedule.add_override(led.id, _ov(NOV[10], teacher_id=cast.anna.id))

    out = await world.read(cast.sam, NOV[9], days=2)

    by_day = {r.occurrence.on: r for r in out.rows}
    assert by_day[NOV[9]].my_teacher is False
    assert by_day[NOV[10]].my_teacher is True
    assert by_day[NOV[10]].occurrence.substitute is True
    teachers = await world.read(cast.sam, NOV[9], days=2, only=Only.TEACHERS)
    assert [r.occurrence.on for r in teachers.rows] == [NOV[10]]


async def test_a_substitute_for_my_teacher_keeps_who_was_planned(world: World, cast: Cast) -> None:
    """Tara covers Anna's Tuesday: the row names Tara, with Anna as the planned teacher (the
    adapters render "Tara (for Anna) 👤")."""
    mysore = world.schedule.add_class(cast.shala, teacher_id=cast.anna.id)
    world.schedule.add_override(mysore.id, _ov(NOV[10], teacher_id=cast.tara.id))

    out = await world.read(cast.sam, NOV[10], days=1)

    [row] = out.rows
    o = row.occurrence
    assert (o.teacher_id, o.planned_teacher, o.substitute) == (cast.tara.id, cast.anna.id, True)
    assert out.staff[cast.shala][cast.tara.id] == "Tara"


async def test_roles_on_staff_rows(world: World, cast: Cast) -> None:
    mysore = world.schedule.add_class(cast.shala, teacher_id=cast.tara.id)
    led = world.schedule.add_class(
        cast.shala, type=ClassType.LED, teacher_id=cast.anna.id, weekdays=frozenset({2}),
        start=time(18, 0), minutes=90,
    )  # fmt: skip
    world.schedule.add_override(mysore.id, _ov(NOV[9], teacher_id=cast.anna.id))
    world.schedule.add_override(led.id, _ov(NOV[10], teacher_id=cast.tara.id))

    out = await world.read(cast.tara, NOV[9], days=2, only=Only.MINE)

    roles = {(r.occurrence.on, r.occurrence.type): r.role for r in out.rows}
    assert roles == {
        (NOV[9], ClassType.MYSORE): Teaching.COVERED,
        (NOV[10], ClassType.MYSORE): Teaching.TEACHING,
        (NOV[10], ClassType.LED): Teaching.COVERING,
    }
    boris = await world.read(cast.boris, NOV[9], days=2)
    assert {r.role for r in boris.rows} == {None}  # staff, but none of these is his


async def test_private_classes_only_from_the_shala_where_i_am_staff(
    world: World, cast: Cast
) -> None:
    other = world.shala(cast.boris, name="B Shala")
    world.shalas.add_staff(other, cast.sam.id, ShalaRole.ASSISTANT)
    for shala in (cast.shala, other):
        world.schedule.add_class(shala, type=ClassType.PRIVATE, start=time(12, 0), minutes=60)
        world.schedule.add_class(shala)

    out = await world.read(cast.sam, NOV[9], days=1)

    private = [r.shala_id for r in out.rows if r.occurrence.type is ClassType.PRIVATE]
    assert private == [other]
    assert {r.shala_id for r in out.rows if r.occurrence.type is ClassType.MYSORE} == {
        cast.shala,
        other,
    }


async def test_staff_shalas_come_first(world: World, cast: Cast) -> None:
    other = world.shala(cast.boris, name="Z Shala")
    world.shalas.add_staff(other, cast.sam.id, ShalaRole.TEACHER)

    out = await world.read(cast.sam)

    assert [(s.id, s.staff) for s in out.shalas] == [(other, True), (cast.shala, False)]


# Privacy (Q135)


async def test_a_followed_teachers_other_shala_stays_invisible(world: World, cast: Cast) -> None:
    hidden = world.shala(cast.anna, city="berlin", name="Anna's Berlin Room")
    world.schedule.add_class(hidden, teacher_id=cast.anna.id, title="Secret")
    world.schedule.add_class(cast.shala, teacher_id=cast.anna.id)

    out = await world.read(cast.sam)

    assert {s.id for s in out.shalas} == {cast.shala}
    assert {r.shala_id for r in out.rows} == {cast.shala}
    assert all(r.occurrence.title != "Secret" for r in out.rows)
    assert hidden not in out.staff
    assert {r.zone for r in out.rows} == {ALMATY}
    assert out.shifts == ()


async def test_a_followed_teacher_with_no_shared_shala_gives_nothing(world: World) -> None:
    anna = world.person("1", "Anna")
    sam = world.person("4", "Sam")
    world.link(sam, anna)
    shala = world.shala(anna)
    world.schedule.add_class(shala, teacher_id=anna.id)

    out = await world.read(sam)

    assert (out.rows, out.shalas) == ((), ())


# The unknown zone (Q141)


async def test_an_unknown_zone_falls_back_to_my_first_shala(world: World, cast: Cast) -> None:
    """Staff first: Sam teaches at a Berlin shala and studies in Almaty."""
    nomad = world.person("60", "Nomad", zone=None)
    berlin = world.shala(cast.boris, city="berlin", name="Yoga Berlin")
    world.shalas.add_staff(berlin, nomad.id, ShalaRole.TEACHER)
    world.shalas.add_student(cast.shala, nomad.id)
    world.schedule.add_class(cast.shala)

    out = await world.read(nomad, NOV[9], days=1)

    assert (out.zone, out.zone_known) == (BERLIN, False)
    [row] = out.rows
    assert row.occurrence.starts_at.astimezone(ZoneInfo(BERLIN)).date() == NOV[9]


async def test_an_unknown_zone_with_only_a_student_seat(world: World, cast: Cast) -> None:
    nomad = world.person("60", "Nomad", zone=None)
    world.shalas.add_student(cast.shala, nomad.id)

    out = await world.read(nomad)

    assert (out.zone, out.zone_known, out.today) == (ALMATY, False, NOV[9])


# Moon days: each shala's own rows, and my own day (MD-02)


async def test_each_shala_cancels_on_its_own_moon_date(world: World, cast: Cast) -> None:
    """A Los Angeles shala following Mysuru (13 Nov) and the Almaty shala (12 Nov) in one week,
    seen from Almaty."""
    west = world.shala(cast.boris, city="los-angeles", name="LA Mysore", moon_city="mysuru")
    world.shalas.add_student(west, cast.sam.id)
    world.moon_days("almaty", NOV[12])
    world.moon_days("mysuru", NOV[13])
    world.schedule.add_class(cast.shala)
    world.schedule.add_class(west)

    out = await world.read(cast.sam)

    found = {(r.shala_id, r.occurrence.on): r.occurrence.cancelled for r in out.rows}
    assert found[(cast.shala, NOV[12])] is Reason.MOON
    assert found[(cast.shala, NOV[13])] is None
    assert found[(west, NOV[12])] is None
    assert found[(west, NOV[13])] is Reason.MOON
    moon_rows = {(r.shala_id, r.occurrence.on) for r in out.rows if r.occurrence.moon}
    assert moon_rows == {(cast.shala, NOV[12]), (west, NOV[13])}


async def test_a_cancelled_moon_row_names_its_swap_target(world: World, cast: Cast) -> None:
    """Expert item 3: the original on Friday stays, with `swapped_to`; Saturday's names Friday."""
    world.moon_days("almaty", NOV[13])
    world.schedule.add_class(cast.shala)
    world.schedule.swaps[(cast.shala, NOV[13])] = Swap(NOV[13], NOV[14])

    out = await world.read(cast.sam, NOV[13], days=2)

    assert [
        (
            r.occurrence.on,
            r.occurrence.cancelled,
            r.occurrence.swapped_to,
            r.occurrence.swapped_from,
        )
        for r in out.rows
    ] == [(NOV[13], Reason.MOON, NOV[14], None), (NOV[14], None, None, NOV[13])]


async def test_my_moon_day_from_my_own_city(world: World, cast: Cast) -> None:
    world.accounts.accounts[cast.sam.id] = replace(cast.sam, moon_location="mysuru")
    world.moon_days("mysuru", NOV[13], date(2026, 11, 27))

    out = await world.read(cast.sam)

    assert [d.date for d in out.days if d.my_moon] == [NOV[13]]
    [call] = world.schedule.member_calls
    assert call[4] == "mysuru"


async def test_my_moon_day_inherited_from_my_main_teacher(world: World, cast: Cast) -> None:
    """MD-02: "Follow my teacher", whose own city is Mysuru, though my shala is in Almaty."""
    world.accounts.accounts[cast.anna.id] = replace(cast.anna, moon_location="mysuru")
    world.accounts.accounts[cast.sam.id] = replace(cast.sam, moon_location=FOLLOW_TEACHER)
    world.moon_days("almaty", NOV[12])
    world.moon_days("mysuru", NOV[13])

    out = await world.read(cast.sam)

    assert [d.date for d in out.days if d.my_moon] == [NOV[13]]
    assert world.schedule.member_calls[0][4] == "mysuru"


async def test_a_never_chose_member_follows_the_md02_fallback(world: World) -> None:
    """Never chose, no teacher: a student follows the main shala's city (Berlin here)."""
    owner = world.person("1", "Anna", zone=BERLIN)
    me = world.person("5", "Mo", zone=ALMATY)
    shala = world.shala(owner, city="berlin")
    world.shalas.add_student(shala, me.id)
    world.moon_days("almaty", NOV[12])
    world.moon_days("berlin", NOV[14])

    out = await world.read(me)

    assert [d.date for d in out.days if d.my_moon] == [NOV[14]]
    assert world.schedule.member_calls[0][4] == "berlin"


async def test_the_moon_city_passed_is_moon_follow_of_the_loaded_account(
    world: World, cast: Cast
) -> None:
    principal = world.me(cast.sam)

    await world.mine().execute(principal, None)

    expected = moon_follow_of(principal.account, cities()).city.slug
    assert world.schedule.member_calls[0][4] == expected


async def test_my_moon_day_and_the_shalas_may_differ_by_a_day(world: World, cast: Cast) -> None:
    """Both show: my 🌙 on Friday (Mysuru), the shala's moon row on Thursday (Almaty)."""
    world.accounts.accounts[cast.sam.id] = replace(cast.sam, moon_location="mysuru")
    world.moon_days("almaty", NOV[12])
    world.moon_days("mysuru", NOV[13])
    world.schedule.add_class(cast.shala)

    out = await world.read(cast.sam)

    assert {d.date: d.my_moon for d in out.days if d.date in (NOV[12], NOV[13])} == {
        NOV[12]: False,
        NOV[13]: True,
    }
    cancelled = {r.occurrence.on: r.occurrence.cancelled for r in out.rows}
    assert (cancelled[NOV[12]], cancelled[NOV[13]]) == (Reason.MOON, None)


async def test_my_moon_day_shows_with_an_unknown_zone(world: World, cast: Cast) -> None:
    nomad = world.person("60", "Nomad", zone=None, moon="mysuru")
    world.shalas.add_student(cast.shala, nomad.id)
    world.moon_days("mysuru", NOV[13])

    out = await world.read(nomad)

    assert out.zone_known is False
    assert [d.date for d in out.days if d.my_moon] == [NOV[13]]


# The ⚠ shift lines (Q140)


async def test_a_dst_week_reports_the_shift_of_a_shown_class_zone() -> None:
    world = World(instant=datetime(2026, 10, 19, 3, 0, tzinfo=UTC))  # Mon 19 Oct, Almaty
    anna = world.person("1", "Anna", zone=BERLIN)
    sam = world.person("4", "Sam")
    berlin = world.shala(anna, city="berlin", name="Yoga Berlin")
    world.shalas.add_student(berlin, sam.id)
    world.schedule.add_class(
        berlin, type=ClassType.LED, start=time(17, 30), minutes=90, weekdays=frozenset({1, 7}),
        starts_on=date(2026, 10, 1),
    )  # fmt: skip

    out = await world.read(sam)

    assert out.shifts == (Shift(BERLIN, date(2026, 10, 25), -60),)
    times = [r.occurrence.starts_at.astimezone(ZoneInfo(ALMATY)).time() for r in out.rows]
    assert times == [time(20, 30), time(21, 30)]  # Mon 19, Sun 25: the rows stay exact


async def test_no_shift_when_both_sides_move_together() -> None:
    world = World(instant=datetime(2026, 10, 19, 6, 0, tzinfo=UTC))
    anna = world.person("1", "Anna", zone="Europe/London")
    sam = world.person("4", "Sam", zone=BERLIN)
    london = world.shala(anna, city="london", name="London Shala")
    world.shalas.add_student(london, sam.id)
    world.schedule.add_class(london, weekdays=EVERY_DAY, starts_on=date(2026, 10, 1))

    out = await world.read(sam)

    assert out.shifts == ()
    assert len(out.rows) == 7


async def test_only_class_zones_with_rows_this_week_shift() -> None:
    """A Berlin shala with no class this week gives no ⚠ line."""
    world = World(instant=datetime(2026, 10, 19, 3, 0, tzinfo=UTC))
    anna = world.person("1", "Anna", zone=BERLIN)
    sam = world.person("4", "Sam")
    world.shalas.add_student(world.shala(anna, city="berlin"), sam.id)

    out = await world.read(sam)

    assert out.shifts == ()


async def test_the_my_classes_week_crosses_shalas_in_my_time(world: World, cast: Cast) -> None:
    """SC-02's "My classes" case, now in my zone: a 20:00 Los Angeles online class is 09:00 the
    next morning in Almaty, every day."""
    world.schedule.add_class(
        cast.shala, teacher_id=cast.tara.id, online=True, city="los-angeles",
        start=time(20, 0), minutes=60, weekdays=EVERY_DAY, starts_on=NOV[1],
    )  # fmt: skip

    out = await world.read(cast.tara, only=Only.MINE)

    local = [r.occurrence.starts_at.astimezone(ZoneInfo(ALMATY)) for r in out.rows]
    assert [d.date() for d in local] == [NOV[d] for d in range(9, 16)]
    assert {d.hour for d in local} == {9}
    assert {r.role for r in out.rows} == {Teaching.TEACHING}


async def test_cancelled_rows_stay_with_their_reason_under_mine(world: World, cast: Cast) -> None:
    world.moon_days("almaty", NOV[11])
    world.schedule.add_class(cast.shala, teacher_id=cast.tara.id)

    out = await world.read(cast.tara, only=Only.MINE)

    cancelled = {r.occurrence.on: r.occurrence.cancelled for r in out.rows}
    assert (cancelled[NOV[11]], cancelled[NOV[10]]) == (Reason.MOON, None)


async def test_a_held_moon_row_is_moon_and_not_cancelled(world: World, cast: Cast) -> None:
    world.moon_days("almaty", NOV[13])
    world.shalas.shalas[cast.shala].moon_policy = "open"
    world.schedule.add_class(cast.shala)

    out = await world.read(cast.sam, NOV[13], days=1)

    [row] = out.rows
    assert (row.occurrence.cancelled, row.occurrence.moon) == (None, True)


# No new reads of private data (spec §3, §7)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
    return found


def test_the_use_case_needs_no_extra_port_and_no_account_reload() -> None:
    from typing import get_type_hints

    hints = get_type_hints(GetMySchedule.__init__)
    hints.pop("return", None)

    assert len(hints) == 3  # the schedule port, the clock, the cities


def _module() -> str:
    import tristhana.application.classes as module

    return module.__file__ or ""


def test_the_classes_module_imports_no_log_rest_or_moon_use_case() -> None:
    imported = _imports(Path(_module()))
    banned = {
        "tristhana.application.ports.practice",
        "tristhana.application.ports.diary",
        "tristhana.application.ports.check_in",
        "tristhana.application.ports.rest_periods",
        "tristhana.application.ports.progression",
        "tristhana.application.ports.days",
        "tristhana.application.ports.moon",
        "tristhana.application.moon",
    }

    assert imported & banned == set()
