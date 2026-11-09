"""SC-05 attendance use cases on fakes (spec §3, §8; ADR-0039). A frozen clock: Mon 9 Nov
2026, 08:00 in Almaty."""

from dataclasses import dataclass, field, fields
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from tests.attendance_fakes import InMemoryAttendance
from tests.fakes import FixedClock, InMemoryMoon, cities
from tests.moon_follow_fakes import person
from tests.schedule_fakes import InMemorySchedule
from tests.shala_fakes import InMemoryShalas, ShalaAccounts, ShalaLinks
from tristhana.application.attendance import (
    ClaimAttendance,
    GetRoster,
    ListAttendable,
    MarkAttendance,
    RemoveMyAttendance,
)
from tristhana.application.classes import GetMySchedule, GetSchedule
from tristhana.application.policies import NotAllowed, NotFound, Principal
from tristhana.application.ports.attendance import RosterPerson
from tristhana.domain.accounts import Account
from tristhana.domain.attendance import (
    AttendanceState,
    Counts,
    InvalidAttendance,
    NotAttendable,
)
from tristhana.domain.classes import ClassType, Override, OverrideStatus
from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.domain.shalas import ShalaRole

NOW = datetime(2026, 11, 9, 3, 0, tzinfo=UTC)  # Mon 9 Nov, 08:00 in Almaty
MON, SUN = date(2026, 11, 9), date(2026, 11, 8)
EVERY_DAY = frozenset(range(1, 8))
C, K = AttendanceState.CONFIRMED, AttendanceState.CLAIMED


@dataclass
class World:
    clock: FixedClock = field(init=False)
    accounts: ShalaAccounts = field(init=False)
    shalas: InMemoryShalas = field(init=False)
    moon: InMemoryMoon = field(init=False)
    schedule: InMemorySchedule = field(init=False)
    attendance: InMemoryAttendance = field(init=False)

    def __post_init__(self) -> None:
        self.clock = FixedClock(NOW)
        self.accounts = ShalaAccounts(clock=self.clock)
        links = ShalaLinks(self.accounts)
        self.shalas = InMemoryShalas(self.accounts, links)
        links.shalas = self.shalas
        self.accounts.links = links
        self.accounts.shalas = self.shalas
        self.moon = InMemoryMoon()
        self.schedule = InMemorySchedule(self.shalas, self.moon)
        self.attendance = InMemoryAttendance(self.schedule)

    def person(self, tg: str, name: str, zone: str | None = "Asia/Almaty") -> Account:
        return person(self.accounts, tg, name, zone=zone)

    def me(self, a: Account) -> Principal:
        return Principal(self.accounts.inputs(self.accounts.accounts[a.id]))

    def claim(self) -> ClaimAttendance:
        return ClaimAttendance(self.attendance, self.clock, cities())

    def mark(self) -> MarkAttendance:
        return MarkAttendance(self.attendance, self.clock, cities())

    def roster(self) -> GetRoster:
        return GetRoster(self.attendance, self.clock, cities())

    def listing(self) -> ListAttendable:
        return ListAttendable(self.schedule, self.clock, cities())


@dataclass
class Cast:
    w: World
    anna: Account  # owner, teacher
    tara: Account  # assistant
    olga: Account  # front desk
    sam: Account  # student
    vera: Account  # student
    out: Account  # not a member
    shala: UUID
    mysore: UUID  # every day 06:00-09:30

    @property
    def everyone(self) -> list[Account]:
        return [self.anna, self.tara, self.olga, self.sam, self.vera]


@pytest.fixture
def cast() -> Cast:
    w = World()
    anna, tara, olga = w.person("1", "Anna"), w.person("2", "Tara"), w.person("3", "Olga")
    sam, vera, out = w.person("4", "Sam"), w.person("5", "Vera"), w.person("6", "Out")
    shala = w.shalas.add_shala(anna.id).id
    w.shalas.add_staff(shala, tara.id, ShalaRole.ASSISTANT)
    w.shalas.add_staff(shala, olga.id, ShalaRole.OFFICE)
    w.shalas.add_student(shala, sam.id)
    w.shalas.add_student(shala, vera.id)
    mysore = w.schedule.add_class(
        shala, weekdays=EVERY_DAY, starts_on=date(2026, 10, 1), teacher_id=anna.id
    ).id
    return Cast(w, anna, tara, olga, sam, vera, out, shala, mysore)


class TestClaim:
    async def test_a_student_claim_is_claimed(self, cast: Cast) -> None:
        w = cast.w
        mark = await w.claim().execute(w.me(cast.sam), cast.mysore, MON)
        assert mark.state is K
        assert mark.day == MON
        assert mark.log_day
        assert mark.shala_name == "Ashtanga Almaty"
        assert w.attendance.state_of(cast.mysore, MON, cast.sam.id) is K

    @pytest.mark.parametrize("who", ["anna", "tara", "olga"])
    async def test_a_staff_self_claim_is_confirmed(self, cast: Cast, who: str) -> None:
        w = cast.w
        mark = await w.claim().execute(w.me(getattr(cast, who)), cast.mysore, MON)
        assert mark.state is C

    async def test_a_confirmed_row_stays_confirmed_on_a_re_claim(self, cast: Cast) -> None:
        w = cast.w
        await w.mark().execute(w.me(cast.tara), cast.mysore, MON, present=[cast.sam.id])
        mark = await w.claim().execute(w.me(cast.sam), cast.mysore, MON)
        assert mark.state is C

    async def test_not_before_the_start(self, cast: Cast) -> None:
        w = cast.w
        w.clock.instant = datetime(2026, 11, 9, 0, 59, tzinfo=UTC)  # 05:59 Almaty
        with pytest.raises(NotAttendable):
            await w.claim().execute(w.me(cast.sam), cast.mysore, MON)

    async def test_today_minus_6_is_in_and_minus_7_is_out(self, cast: Cast) -> None:
        w = cast.w
        await w.claim().execute(w.me(cast.sam), cast.mysore, MON - timedelta(days=6))
        with pytest.raises(NotAttendable):
            await w.claim().execute(w.me(cast.sam), cast.mysore, MON - timedelta(days=7))

    async def test_not_when_cancelled(self, cast: Cast) -> None:
        w = cast.w
        w.schedule.add_override(cast.mysore, Override(SUN, OverrideStatus.CANCELLED))
        with pytest.raises(NotAttendable):
            await w.claim().execute(w.me(cast.sam), cast.mysore, SUN)

    async def test_a_forged_key_is_not_attendable(self, cast: Cast) -> None:
        w = cast.w
        weekly = w.schedule.add_class(cast.shala, weekdays=frozenset({1}), type=ClassType.LED)
        with pytest.raises(NotAttendable):
            await w.claim().execute(w.me(cast.sam), weekly.id, SUN)  # a Sunday: no Monday rule

    async def test_a_non_member_or_unknown_class_is_not_found(self, cast: Cast) -> None:
        w = cast.w
        with pytest.raises(NotFound):
            await w.claim().execute(w.me(cast.out), cast.mysore, MON)
        with pytest.raises(NotFound):
            await w.claim().execute(w.me(cast.sam), uuid4(), MON)

    async def test_a_student_cannot_claim_a_1_to_1(self, cast: Cast) -> None:
        w = cast.w
        private = w.schedule.add_class(cast.shala, weekdays=EVERY_DAY, type=ClassType.PRIVATE)
        with pytest.raises(NotAttendable):
            await w.claim().execute(w.me(cast.sam), private.id, MON)
        assert (await w.claim().execute(w.me(cast.tara), private.id, MON)).state is C

    @pytest.mark.parametrize(
        ("type", "offered"),
        [(ClassType.CONFERENCE, False), (ClassType.CHANTING, False), (ClassType.LED, True)],
    )
    async def test_log_this_day_by_type(self, cast: Cast, type: ClassType, offered: bool) -> None:
        w = cast.w
        c = w.schedule.add_class(cast.shala, weekdays=EVERY_DAY, type=type, minutes=60)
        assert (await w.claim().execute(w.me(cast.sam), c.id, MON)).log_day is offered

    async def test_log_this_day_targets_my_local_date(self, cast: Cast) -> None:
        """A Berlin 21:30 online class on Sun 8 Nov is Mon 9 Nov 01:30 in Almaty."""
        w = cast.w
        c = w.schedule.add_class(
            cast.shala, weekdays=EVERY_DAY, online=True, city="berlin",
            start=time(21, 30), minutes=60,
        )  # fmt: skip
        mark = await w.claim().execute(w.me(cast.sam), c.id, SUN)
        assert mark.occurrence.on == SUN
        assert mark.day == MON
        assert mark.zone == "Europe/Berlin"

    async def test_a_class_held_on_a_moon_day_can_be_marked(self, cast: Cast) -> None:
        """Held on a moon day (pranayama policy): it can be marked. That the day card, streak,
        GM-01 count and 🌙 rest day stay the same is checked on real Postgres
        (`test_db_attendance.py`)."""
        w = cast.w
        w.shalas.shalas[cast.shala].moon_policy = "pranayama"
        w.moon.days_by_location["almaty"] = [MoonDay(MON, MoonDayKind.PURNIMA)]
        p = w.schedule.add_class(cast.shala, weekdays=EVERY_DAY, type=ClassType.PRANAYAMA,
                                 start=time(7, 0), minutes=60)  # fmt: skip
        mark = await w.claim().execute(w.me(cast.sam), p.id, MON)
        assert mark.state is K
        assert mark.occurrence.moon
        with pytest.raises(NotAttendable):  # Mysore is cancelled on the moon day
            await w.claim().execute(w.me(cast.sam), cast.mysore, MON)


class TestRemove:
    async def test_removing_my_own_row_is_idempotent(self, cast: Cast) -> None:
        w = cast.w
        await w.mark().execute(w.me(cast.anna), cast.mysore, MON, present=[cast.sam.id])
        uc = RemoveMyAttendance(w.attendance)
        await uc.execute(w.me(cast.sam), cast.mysore, MON)
        await uc.execute(w.me(cast.sam), cast.mysore, MON)
        assert w.attendance.state_of(cast.mysore, MON, cast.sam.id) is None

    async def test_after_leaving_it_needs_no_seat(self, cast: Cast) -> None:
        w = cast.w
        await w.claim().execute(w.me(cast.sam), cast.mysore, MON)
        await w.shalas.remove_student(cast.shala, cast.sam.id, cast.sam.id)
        assert w.attendance.rows == {}  # Q186: leaving deletes the rows
        await RemoveMyAttendance(w.attendance).execute(w.me(cast.sam), cast.mysore, MON)


class TestRoster:
    async def test_order_claims_regulars_then_names(self, cast: Cast) -> None:
        w = cast.w
        zed = w.person("7", "Zed")
        w.shalas.add_student(cast.shala, zed.id)
        await w.claim().execute(w.me(zed), cast.mysore, SUN)  # a regular now
        await w.mark().execute(w.me(cast.anna), cast.mysore, SUN, confirm_claims=True)
        await w.claim().execute(w.me(cast.vera), cast.mysore, MON)
        r = await w.roster().execute(w.me(cast.olga), cast.mysore, MON)
        names = [p.name for p in r.people]
        assert names == ["Vera", "Zed", "Sam"]  # claim, regular, the rest by name
        assert r.counts == Counts(0, 1)
        assert r.attendable
        assert not r.more

    async def test_staff_who_practise_here_appear(self, cast: Cast) -> None:
        w = cast.w
        r = await w.roster().execute(w.me(cast.anna), cast.mysore, MON)
        assert {p.name for p in r.people} == {"Sam", "Vera"}
        await w.claim().execute(w.me(cast.tara), cast.mysore, SUN)
        r = await w.roster().execute(w.me(cast.anna), cast.mysore, MON)
        tara = next(p for p in r.people if p.name == "Tara")
        assert tara.staff
        assert tara.state is None

    async def test_search_and_paging(self, cast: Cast) -> None:
        w = cast.w
        r = await w.roster().execute(w.me(cast.anna), cast.mysore, MON, q="ver")
        assert [p.name for p in r.people] == ["Vera"]
        r = await w.roster().execute(w.me(cast.anna), cast.mysore, MON, limit=1)
        assert len(r.people) == 1
        assert r.more

    async def test_a_student_is_not_allowed_and_a_stranger_not_found(self, cast: Cast) -> None:
        w = cast.w
        with pytest.raises(NotAllowed):
            await w.roster().execute(w.me(cast.sam), cast.mysore, MON)
        with pytest.raises(NotFound):
            await w.roster().execute(w.me(cast.out), cast.mysore, MON)

    async def test_the_shape_holds_no_log_field(self) -> None:
        """Privacy: a student who logged 🌸 that day looks the same as anyone else."""
        assert {f.name for f in fields(RosterPerson)} == {
            "account_id", "name", "state", "staff", "regular",
        }  # fmt: skip


class TestMark:
    async def test_present_removed_and_confirm_all(self, cast: Cast) -> None:
        w = cast.w
        await w.claim().execute(w.me(cast.sam), cast.mysore, MON)
        counts = await w.mark().execute(w.me(cast.tara), cast.mysore, MON, present=[cast.vera.id])
        assert counts == Counts(1, 1)
        counts = await w.mark().execute(w.me(cast.olga), cast.mysore, MON, confirm_claims=True)
        assert counts == Counts(2, 0)
        counts = await w.mark().execute(w.me(cast.anna), cast.mysore, MON, removed=[cast.sam.id])
        assert counts == Counts(1, 0)
        assert w.attendance.state_of(cast.mysore, MON, cast.sam.id) is None

    async def test_confirm_claims_confirms_only_claims(self, cast: Cast) -> None:
        w = cast.w
        await w.claim().execute(w.me(cast.sam), cast.mysore, MON)
        await w.mark().execute(w.me(cast.anna), cast.mysore, MON, confirm_claims=True)
        assert w.attendance.state_of(cast.mysore, MON, cast.vera.id) is None
        assert w.attendance.state_of(cast.mysore, MON, cast.sam.id) is C

    @pytest.mark.parametrize("bad", ["overlap", "too_many", "stranger"])
    async def test_invalid(self, cast: Cast, bad: str) -> None:
        w = cast.w
        kw: dict[str, Any]
        if bad == "overlap":
            kw = {"present": [cast.sam.id], "removed": [cast.sam.id]}
        elif bad == "too_many":
            kw = {"present": [uuid4() for _ in range(101)]}
        else:
            kw = {"present": [cast.out.id]}
        with pytest.raises(InvalidAttendance):
            await w.mark().execute(w.me(cast.anna), cast.mysore, MON, **kw)
        assert w.attendance.rows == {}

    async def test_a_student_is_not_allowed(self, cast: Cast) -> None:
        w = cast.w
        with pytest.raises(NotAllowed):
            await w.mark().execute(w.me(cast.sam), cast.mysore, MON, present=[cast.vera.id])

    async def test_not_attendable_and_a_wrong_shala(self, cast: Cast) -> None:
        w = cast.w
        with pytest.raises(NotAttendable):
            await w.mark().execute(w.me(cast.anna), cast.mysore, MON + timedelta(days=1))
        with pytest.raises(NotFound):
            await w.mark().execute(w.me(cast.anna), cast.mysore, MON, shala=uuid4())

    async def test_a_staff_delta_keeps_a_concurrent_claim(self, cast: Cast) -> None:
        w = cast.w
        await w.claim().execute(w.me(cast.sam), cast.mysore, MON)
        await w.mark().execute(w.me(cast.anna), cast.mysore, MON, present=[cast.vera.id])
        assert w.attendance.state_of(cast.mysore, MON, cast.sam.id) is K

    async def test_two_statements(self, cast: Cast) -> None:
        w = cast.w
        await w.mark().execute(w.me(cast.anna), cast.mysore, MON, present=[cast.vera.id])
        assert w.attendance.calls == ["occurrence", "mark"]


class TestLists:
    async def test_my_list_newest_first_with_my_marks(self, cast: Cast) -> None:
        w = cast.w
        await w.claim().execute(w.me(cast.sam), cast.mysore, SUN)
        found = await w.listing().execute(w.me(cast.sam))
        days = [r.row.occurrence.on for r in found.rows]
        assert days == [MON - timedelta(days=i) for i in range(7)]
        assert found.rows[1].row.attendance is K
        assert found.rows[0].row.attendance is None
        assert all(r.shala_name == "Ashtanga Almaty" for r in found.rows)

    async def test_the_staff_picker_puts_mine_first_with_counts(self, cast: Cast) -> None:
        w = cast.w
        led = w.schedule.add_class(cast.shala, weekdays=EVERY_DAY, type=ClassType.LED,
                                   start=time(7, 0), minutes=90)  # fmt: skip
        await w.claim().execute(w.me(cast.sam), led.id, MON)
        found = await w.listing().execute(w.me(cast.anna), staff=True)
        assert len(found.rows) == 10
        assert all(r.row.occurrence.class_id == cast.mysore for r in found.rows[:7])
        led_mon = next(r for r in found.rows if r.row.occurrence.class_id == led.id)
        assert led_mon.row.counts == Counts(0, 1)
        assert (await w.listing().execute(w.me(cast.sam), staff=True)).rows == ()


class TestSchedules:
    async def test_my_schedule_rows_carry_my_mark_and_can_claim(self, cast: Cast) -> None:
        w = cast.w
        await w.claim().execute(w.me(cast.sam), cast.mysore, SUN)
        mine = await GetMySchedule(w.schedule, w.clock, cities()).execute(
            w.me(cast.sam), SUN, days=3
        )
        by_day = {r.occurrence.on: r for r in mine.rows}
        assert by_day[SUN].attendance is K
        assert by_day[SUN].can_claim
        assert by_day[MON].attendance is None
        assert by_day[MON].can_claim
        assert not by_day[MON + timedelta(days=1)].can_claim
        assert by_day[SUN].counts is None  # a student sees no counts

    async def test_the_shala_schedule_has_counts_for_staff_only(self, cast: Cast) -> None:
        w = cast.w
        await w.claim().execute(w.me(cast.sam), cast.mysore, SUN)
        uc = GetSchedule(w.schedule, w.clock, cities())
        staff = await uc.execute(w.me(cast.olga), cast.shala, SUN, 2)
        assert staff.counts == {(cast.mysore, SUN): Counts(0, 1)}
        student = await uc.execute(w.me(cast.vera), cast.shala, SUN, 2)
        assert student.counts == {}
