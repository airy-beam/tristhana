"""SC-05 on real Postgres (spec §3, §6, §8; ADR-0039): `class_attendance` and its CHECKs and
unique key; the guarded claim and staff deltas; the roster's people and order; leaving deletes
the rows (Q186); a class delete keeps them; statement counts per tap; 0025 up/down/up; the app
role."""

import asyncio
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.fakes import FixedClock, cities
from tests.infrastructure.test_db_app_role import app_engine  # noqa: F401  # pyright: ignore[reportUnusedImport]
from tests.infrastructure.test_db_shalas import (  # pyright: ignore[reportPrivateUsage]
    _person,  # pyright: ignore[reportPrivateUsage]
    _shala,  # pyright: ignore[reportPrivateUsage]
    _staff,  # pyright: ignore[reportPrivateUsage]
    _student,  # pyright: ignore[reportPrivateUsage]
)
from tristhana.application.attendance import (
    ClaimAttendance,
    GetRoster,
    ListAttendable,
    MarkAttendance,
    RemoveMyAttendance,
)
from tristhana.application.classes import GetMySchedule, GetSchedule
from tristhana.application.policies import NotAllowed, NotFound, Principal
from tristhana.domain.accounts import Account
from tristhana.domain.attendance import AttendanceState, Counts, InvalidAttendance
from tristhana.domain.classes import ClassType
from tristhana.domain.shalas import ShalaRole
from tristhana.infrastructure.db import migrate
from tristhana.infrastructure.db.accounts import SqlAccountRepository
from tristhana.infrastructure.db.attendance import SqlAttendanceRepository
from tristhana.infrastructure.db.classes import SqlScheduleRepository
from tristhana.infrastructure.db.shalas import SqlShalaRepository

pytestmark = pytest.mark.db

NOW = datetime(2026, 11, 9, 3, 0, tzinfo=UTC)  # Mon 9 Nov, 08:00 Almaty
MON, SUN = date(2026, 11, 9), date(2026, 11, 8)
EVERY_DAY = frozenset(range(1, 8))
C, K = AttendanceState.CONFIRMED, AttendanceState.CLAIMED


@contextmanager
def _statements(engine: AsyncEngine) -> Generator[list[str]]:
    seen: list[str] = []

    def record(_conn: object, _cursor: object, statement: str, *_: object) -> None:
        if "tristhana." in statement:
            seen.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)


@dataclass
class W:
    engine: AsyncEngine
    clock: FixedClock
    owner: Account
    tara: Account  # assistant
    sam: Account
    vera: Account
    out: Account
    shala: UUID
    mysore: UUID
    keys: dict[UUID, Any]

    async def person(self, name: str) -> Account:
        a, key = await _person(self.engine, name)
        self.keys[a.id] = key
        return a

    @property
    def repo(self) -> SqlAttendanceRepository:
        return SqlAttendanceRepository(self.engine)

    @property
    def schedule(self) -> SqlScheduleRepository:
        return SqlScheduleRepository(self.engine)

    async def me(self, a: Account) -> Principal:
        found = await SqlAccountRepository(self.engine).find_by_identity(self.keys[a.id])
        assert found is not None
        return Principal(found)

    def claim(self) -> ClaimAttendance:
        return ClaimAttendance(self.repo, self.clock, cities())

    def mark(self) -> MarkAttendance:
        return MarkAttendance(self.repo, self.clock, cities())

    def roster(self) -> GetRoster:
        return GetRoster(self.repo, self.clock, cities())

    async def add_class(self, **kw: Any) -> UUID:
        from tests.infrastructure.test_db_classes import CAPS, _draft  # pyright: ignore[reportPrivateUsage]

        kw.setdefault("weekdays", EVERY_DAY)
        kw.setdefault("starts_on", date(2026, 10, 1))
        created = await self.schedule.create(self.shala, self.owner.id, _draft(**kw), CAPS, MON)
        assert created.value is not None
        return created.value.id

    async def rows(self) -> list[Any]:
        async with self.engine.connect() as conn:
            result = await conn.execute(
                text("SELECT * FROM tristhana.class_attendance ORDER BY created_at, id")
            )
            return list(result.all())


async def _world(engine: AsyncEngine) -> W:
    keys: dict[UUID, Any] = {}
    people: list[Account] = []
    for name in ("Anna", "Tara", "Sam", "Vera", "Out"):
        a, key = await _person(engine, name)
        keys[a.id] = key
        people.append(a)
    owner, tara, sam, vera, out = people
    shala = await _shala(engine, owner.id)
    await _staff(engine, shala, owner.id, tara.id, ShalaRole.ASSISTANT)
    await _student(engine, shala, owner.id, sam.id)
    await _student(engine, shala, owner.id, vera.id)
    w = W(engine, FixedClock(NOW), owner, tara, sam, vera, out, shala, uuid4(), keys)
    w.mysore = await w.add_class(teacher_id=owner.id)
    return w


@pytest.fixture
async def w(engine: AsyncEngine) -> W:
    return await _world(engine)


async def test_claim_keeps_a_snapshot_and_never_downgrades(w: W) -> None:
    mark = await w.claim().execute(await w.me(w.sam), w.mysore, MON)
    assert mark.state is K
    (row,) = await w.rows()
    assert (row.shala_id, row.class_id, row.occurrence_key) == (w.shala, w.mysore, MON)
    assert (row.on_date, row.zone, row.class_type) == (MON, "Asia/Almaty", "mysore")
    assert row.starts_at == datetime(2026, 11, 9, 1, 0, tzinfo=UTC)
    await w.mark().execute(await w.me(w.tara), w.mysore, MON, present=[w.vera.id])
    await w.mark().execute(await w.me(w.owner), w.mysore, MON, confirm_claims=True)
    again = await w.claim().execute(await w.me(w.sam), w.mysore, MON)
    assert again.state is C
    assert {r.state for r in await w.rows()} == {"confirmed"}


async def test_a_staff_self_claim_is_confirmed(w: W) -> None:
    assert (await w.claim().execute(await w.me(w.tara), w.mysore, MON)).state is C


async def test_a_non_member_is_not_found(w: W) -> None:
    with pytest.raises(NotFound):
        await w.claim().execute(await w.me(w.out), w.mysore, MON)
    with pytest.raises(NotFound):
        await w.claim().execute(await w.me(w.sam), uuid4(), MON)


async def test_staff_deltas_and_counts(w: W) -> None:
    await w.claim().execute(await w.me(w.sam), w.mysore, MON)
    tara = await w.me(w.tara)
    assert await w.mark().execute(tara, w.mysore, MON, present=[w.vera.id]) == Counts(1, 1)
    assert await w.mark().execute(tara, w.mysore, MON, confirm_claims=True) == Counts(2, 0)
    counts = await w.mark().execute(tara, w.mysore, MON, removed=[w.sam.id], present=[w.tara.id])
    assert counts == Counts(2, 0)
    assert {r.account_id for r in await w.rows()} == {w.vera.id, w.tara.id}


async def test_a_stranger_or_a_student_writes_nothing(w: W) -> None:
    with pytest.raises(InvalidAttendance):
        await w.mark().execute(await w.me(w.owner), w.mysore, MON, present=[w.out.id])
    with pytest.raises(NotAllowed):
        await w.mark().execute(await w.me(w.sam), w.mysore, MON, present=[w.vera.id])
    assert await w.rows() == []


async def test_a_demoted_staff_member_is_refused_by_the_guard(w: W) -> None:
    """The occurrence read said staff; the seat is gone before the write: the CTE refuses."""
    target = await w.repo.occurrence(w.tara.id, w.mysore, MON)
    assert target is not None
    shalas = SqlShalaRepository(w.engine)
    assert (await shalas.remove_staff(w.shala, w.owner.id, w.tara.id)).done
    from tristhana.domain.attendance import Snapshot

    snap = Snapshot(w.shala, w.mysore, MON, MON, NOW, "Asia/Almaty", ClassType.MYSORE)
    written = await w.repo.mark(w.tara.id, snap, [w.sam.id], [], False)
    assert written.me is None
    assert await w.rows() == []


async def test_roster_people_and_order(w: W) -> None:
    zed = await w.person("Zed")
    await _student(w.engine, w.shala, w.owner.id, zed.id)
    await w.claim().execute(await w.me(zed), w.mysore, SUN)
    await w.mark().execute(await w.me(w.owner), w.mysore, SUN, confirm_claims=True)
    await w.claim().execute(await w.me(w.vera), w.mysore, MON)
    r = await w.roster().execute(await w.me(w.tara), w.mysore, MON)
    assert [p.name for p in r.people] == ["Vera", "Zed", "Sam"]
    assert r.counts == Counts(0, 1)
    assert r.attendable
    assert not r.more
    assert r.people[0].state is K
    assert r.people[1].regular
    assert not r.people[2].regular
    # Staff who practise here: Tara after a mark in the last 90 days.
    await w.claim().execute(await w.me(w.tara), w.mysore, SUN)
    r = await w.roster().execute(await w.me(w.owner), w.mysore, MON)
    tara = next(p for p in r.people if p.name == "Tara")
    assert tara.staff
    assert tara.state is None
    # Search and paging.
    r = await w.roster().execute(await w.me(w.owner), w.mysore, MON, q="ve")
    assert [p.name for p in r.people] == ["Vera"]
    r = await w.roster().execute(await w.me(w.owner), w.mysore, MON, limit=2)
    assert len(r.people) == 2
    assert r.more
    r = await w.roster().execute(await w.me(w.owner), w.mysore, MON, q="%")
    assert r.people == ()
    with pytest.raises(NotAllowed):
        await w.roster().execute(await w.me(w.sam), w.mysore, MON)


async def test_leaving_and_removal_delete_the_rows(w: W) -> None:
    await w.claim().execute(await w.me(w.sam), w.mysore, MON)
    await w.claim().execute(await w.me(w.tara), w.mysore, MON)
    await w.claim().execute(await w.me(w.vera), w.mysore, MON)
    shalas = SqlShalaRepository(w.engine)
    assert (await shalas.remove_student(w.shala, w.sam.id, w.sam.id)).done  # leaves
    assert (await shalas.remove_staff(w.shala, w.owner.id, w.tara.id)).done  # removed
    assert [r.account_id for r in await w.rows()] == [w.vera.id]
    await RemoveMyAttendance(w.repo).execute(await w.me(w.sam), w.mysore, MON)  # no seat


async def test_class_delete_keeps_the_rows_and_account_delete_cascades(w: W) -> None:
    await w.claim().execute(await w.me(w.sam), w.mysore, MON)
    await w.claim().execute(await w.me(w.vera), w.mysore, MON)
    assert (await w.schedule.delete(w.shala, w.owner.id, w.mysore)).done
    rows = await w.rows()
    assert len(rows) == 2
    assert all(r.class_id is None for r in rows)
    async with w.engine.connect() as conn:
        await conn.execute(text("DELETE FROM tristhana.account WHERE id = :a"), {"a": w.sam.id})
        await conn.commit()
    assert [r.account_id for r in await w.rows()] == [w.vera.id]


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE tristhana.class_attendance SET state = 'absent'",
        "UPDATE tristhana.class_attendance SET class_type = 'yoga'",
        "UPDATE tristhana.class_attendance SET on_date = occurrence_key + 13",
    ],
)
async def test_the_checks(w: W, sql: str) -> None:
    await w.claim().execute(await w.me(w.sam), w.mysore, MON)
    with pytest.raises(IntegrityError):
        async with w.engine.connect() as conn:
            await conn.execute(text(sql))


async def test_the_unique_key(w: W) -> None:
    await w.claim().execute(await w.me(w.sam), w.mysore, MON)
    with pytest.raises(IntegrityError):
        async with w.engine.connect() as conn:
            await conn.execute(
                text(
                    "INSERT INTO tristhana.class_attendance (shala_id, class_id, occurrence_key,"
                    " account_id, state, class_type, on_date, starts_at, zone)"
                    " SELECT shala_id, class_id, occurrence_key, account_id, state, class_type,"
                    " on_date, starts_at, zone FROM tristhana.class_attendance"
                )
            )


async def test_schedules_carry_marks_and_counts(w: W) -> None:
    await w.claim().execute(await w.me(w.sam), w.mysore, SUN)
    mine = await GetMySchedule(w.schedule, w.clock, cities()).execute(
        await w.me(w.sam), SUN, days=2
    )
    by_day = {r.occurrence.on: r for r in mine.rows}
    assert by_day[SUN].attendance is K
    assert by_day[MON].attendance is None
    assert by_day[MON].can_claim
    assert by_day[SUN].counts is None
    uc = GetSchedule(w.schedule, w.clock, cities())
    staff = await uc.execute(await w.me(w.tara), w.shala, SUN, 2)
    assert staff.counts == {(w.mysore, SUN): Counts(0, 1)}
    student = await uc.execute(await w.me(w.vera), w.shala, SUN, 2)
    assert student.counts == {}
    picker = await ListAttendable(w.schedule, w.clock, cities()).execute(
        await w.me(w.owner), staff=True
    )
    assert picker.rows
    assert picker.rows[0].row.counts is not None


async def test_statements_per_tap(w: W) -> None:
    sam, tara = await w.me(w.sam), await w.me(w.tara)
    with _statements(w.engine) as seen:
        await w.claim().execute(sam, w.mysore, MON)
    assert len(seen) == 2  # occurrence read + guarded write (the account load is the third)
    with _statements(w.engine) as seen:
        await w.mark().execute(tara, w.mysore, MON, present=[w.vera.id], confirm_claims=True)
    assert len(seen) == 2
    with _statements(w.engine) as seen:
        await w.roster().execute(tara, w.mysore, MON)
    assert len(seen) == 1
    with _statements(w.engine) as seen:
        await RemoveMyAttendance(w.repo).execute(sam, w.mysore, MON)
    assert len(seen) == 1
    for statement in seen:
        for table in ("day_log", "practice", "rest_period", "check_in", "diary_note"):
            assert f"tristhana.{table}" not in statement


async def test_a_moved_occurrence_on_another_day(w: W) -> None:
    from tristhana.domain.classes import Override

    led = await w.add_class(type=ClassType.LED, weekdays=frozenset({7}), start=time(8, 0),
                            minutes=90)  # fmt: skip
    moved = Override(SUN, None, moved_to=MON)
    assert (await w.schedule.set_override(w.shala, w.owner.id, led, moved)).done
    mark = await w.claim().execute(await w.me(w.sam), led, SUN)
    assert mark.occurrence.on == MON
    (row,) = await w.rows()
    assert (row.occurrence_key, row.on_date) == (SUN, MON)


async def test_working_as_the_app_role(app_engine: AsyncEngine) -> None:  # noqa: F811
    w = await _world(app_engine)
    await w.claim().execute(await w.me(w.sam), w.mysore, MON)
    await w.mark().execute(await w.me(w.owner), w.mysore, MON, present=[w.vera.id])
    await w.roster().execute(await w.me(w.owner), w.mysore, MON)
    await RemoveMyAttendance(w.repo).execute(await w.me(w.sam), w.mysore, MON)


async def test_0025_up_down_up_and_no_drift(migrated_url: str, engine: AsyncEngine) -> None:
    exists = text(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'tristhana'"
        " AND table_name = 'class_attendance'"
    )
    await asyncio.to_thread(migrate.downgrade, migrated_url, "0024")
    try:
        async with engine.connect() as conn:
            assert (await conn.execute(exists)).scalar_one() == 0
    finally:
        await asyncio.to_thread(migrate.upgrade, migrated_url)
    async with engine.connect() as conn:
        assert (await conn.execute(exists)).scalar_one() == 1
    await asyncio.to_thread(migrate.check, migrated_url)


async def test_the_export_holds_my_own_marks_only(w: W) -> None:
    """Q193: my rows with the shala's name; a staff member's export holds none they marked."""
    from tests.infrastructure.test_db_export import DEFAULTS, _repo  # pyright: ignore[reportPrivateUsage]

    await w.claim().execute(await w.me(w.sam), w.mysore, MON)
    await w.mark().execute(await w.me(w.tara), w.mysore, MON, present=[w.vera.id])
    owned = await _repo(w.engine).snapshot(w.sam.id, DEFAULTS, date(2026, 9, 1))
    assert owned is not None
    (mine,) = owned.attendance
    assert (mine.shala, mine.class_type, mine.on, mine.zone, mine.state) == (
        "Ashtanga Almaty", "mysore", MON, "Asia/Almaty", "claimed",
    )  # fmt: skip
    staff = await _repo(w.engine).snapshot(w.tara.id, DEFAULTS, date(2026, 9, 1))
    assert staff is not None
    assert staff.attendance == ()


async def test_a_moon_day_claim_leaves_the_log_streaks_and_counts_unchanged(w: W) -> None:
    """Spec §8 (ashtanga-expert): a Pranayama class held on a Purnima under the `pranayama`
    policy can be marked, and the student's day card, year stats (streak, GM-01 practice
    count) and the 🌙 auto rest day read the same before and after the claim and its
    confirmation."""
    import base64

    from tests.domain.test_practice import catalog
    from tristhana.application.days import GetDays
    from tristhana.application.stats import GetYearStats
    from tristhana.domain.accounts import moon_follow_of
    from tristhana.domain.days import DayLog, DayStatus
    from tristhana.infrastructure.crypto import FieldCipher
    from tristhana.infrastructure.db.days import SqlDayLogRepository
    from tristhana.infrastructure.db.moon import SqlMoonCalendarRepository

    async with w.engine.begin() as conn:  # joined before the window, so auto days can fill it
        await conn.execute(
            text("UPDATE tristhana.account SET created_at = :at WHERE id = :id"),
            {"at": datetime(2026, 10, 1, tzinfo=UTC), "id": w.sam.id},
        )
    sam = await w.me(w.sam)
    follow = moon_follow_of(sam.account, cities()).city.slug
    async with w.engine.begin() as conn:
        await conn.execute(
            text("UPDATE tristhana.shala SET moon_policy = 'pranayama' WHERE id = :id"),
            {"id": w.shala},
        )
        await conn.execute(
            text(
                "INSERT INTO tristhana.moon_day (location, date, kind)"
                " VALUES (:loc, :d, 'purnima') ON CONFLICT DO NOTHING"
            ),
            [{"loc": loc, "d": MON} for loc in {"almaty", follow}],
        )
    keys = "1:" + base64.b64encode(b"\x07" * 32).decode()
    days = SqlDayLogRepository(w.engine, FieldCipher(keys))
    for day in (date(2026, 11, 6), date(2026, 11, 7), SUN):
        await days.upsert(w.sam.id, DayLog(day, DayStatus.PRACTICED), "Asia/Almaty")
    pranayama = await w.add_class(type=ClassType.PRANAYAMA, start=time(7, 0), minutes=60)
    get_days = GetDays(days, cities(), w.clock)
    stats = GetYearStats(days, SqlMoonCalendarRepository(w.engine), cities(), catalog(), w.clock)

    before = (await get_days.execute(sam), await stats.execute(sam))
    assert MON in before[0].auto  # really a 🌙 auto rest day for Sam
    mark = await w.claim().execute(sam, pranayama, MON)
    assert mark.state is K
    assert mark.occurrence.moon
    await w.mark().execute(await w.me(w.owner), pranayama, MON, confirm_claims=True)
    after = (await get_days.execute(sam), await stats.execute(sam))
    assert after == before


async def test_a_re_mark_after_a_move_refreshes_the_snapshot(w: W) -> None:
    """Review nit 5: the export shows the time the class really ran."""
    from tristhana.domain.classes import Override

    sam = await w.me(w.sam)
    await w.claim().execute(sam, w.mysore, MON)
    (row,) = await w.rows()
    assert row.starts_at == datetime(2026, 11, 9, 1, 0, tzinfo=UTC)  # 06:00 Almaty
    later = Override(MON, None, start=time(7, 0))
    assert (await w.schedule.set_override(w.shala, w.owner.id, w.mysore, later)).done
    await w.claim().execute(sam, w.mysore, MON)
    (row,) = await w.rows()
    assert row.starts_at == datetime(2026, 11, 9, 2, 0, tzinfo=UTC)  # 07:00 Almaty
    await w.mark().execute(await w.me(w.owner), w.mysore, MON, present=[w.vera.id])
    assert {r.starts_at for r in await w.rows()} == {datetime(2026, 11, 9, 2, 0, tzinfo=UTC)}


async def test_a_stray_row_of_a_non_member_is_never_counted_or_listed(w: W) -> None:
    """Review nit 6: a claim racing a leave can insert after the leave's delete. Reads count
    current members only, so such a row stays invisible."""
    async with w.engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO tristhana.class_attendance (shala_id, class_id, occurrence_key,"
                " account_id, state, class_type, on_date, starts_at, zone) VALUES (:s, :c, :k,"
                " :a, 'claimed', 'mysore', :k, :at, 'Asia/Almaty')"
            ),
            {"s": w.shala, "c": w.mysore, "k": MON, "a": w.out.id,
             "at": datetime(2026, 11, 9, 1, 0, tzinfo=UTC)},
        )  # fmt: skip
    await w.claim().execute(await w.me(w.sam), w.mysore, MON)
    roster = await w.roster().execute(await w.me(w.owner), w.mysore, MON)
    assert roster.counts == Counts(0, 1)
    assert w.out.id not in {p.account_id for p in roster.people}
    counts = await w.mark().execute(await w.me(w.owner), w.mysore, MON, present=[w.vera.id])
    assert counts == Counts(1, 1)
    staff = await GetSchedule(w.schedule, w.clock, cities()).execute(
        await w.me(w.owner), w.shala, MON, 1
    )
    assert staff.counts == {(w.mysore, MON): Counts(1, 1)}


async def test_the_calendar_feed_read_skips_attendance(w: W) -> None:
    """Review nit 11: the ICS window read carries no SC-05 subqueries."""
    with _statements(w.engine) as seen:
        found = await w.schedule.member_windows(w.sam.id, SUN, MON, attendance=False)
    assert found.windows
    assert all("class_attendance" not in s for s in seen)
    assert all(not x.mine and not x.counts for x in found.windows)


async def test_a_linked_teacher_off_the_staff_sees_nothing(w: W) -> None:
    """Review gap 7 (Q188): Sam's own teacher, linked by ID-04 but not on this shala's staff,
    gets NotFound for the roster and for marks, no picker rows, and no counts."""
    from tests.infrastructure.test_db_shalas import _link  # pyright: ignore[reportPrivateUsage]

    teacher = await w.person("Guru")
    await _link(w.engine, w.sam.id, teacher.id)
    await w.claim().execute(await w.me(w.sam), w.mysore, MON)
    me = await w.me(teacher)
    with pytest.raises(NotFound):
        await w.roster().execute(me, w.mysore, MON)
    with pytest.raises(NotFound):
        await w.mark().execute(me, w.mysore, MON, present=[w.sam.id])
    picker = await ListAttendable(w.schedule, w.clock, cities()).execute(me, staff=True)
    assert picker.rows == ()
    assert await w.schedule.window(w.shala, teacher.id, SUN, MON) is None
    assert {r.state for r in await w.rows()} == {"claimed"}  # nothing was written
