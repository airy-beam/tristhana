"""Rest periods on real Postgres (WH-01 part 2, ADR-0023): the sealed kind, the CHECKs, the
overlap / cut CTEs in the same statement as the write (parity with the domain table), the
upsert snapshot, insert-if-absent for rest, reads with periods, the tick's paused dates,
`account.hide_ladies`, and migration 0010."""

import asyncio
import base64
import itertools
import logging
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests import rest_period_cases as cases
from tristhana.domain.accounts import IdentityKey, IdentityProvider, NewAccount, ProfileChange
from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.notifications import DEFAULTS
from tristhana.domain.rest_periods import RestPeriod
from tristhana.infrastructure.crypto import FieldCipher
from tristhana.infrastructure.db import migrate
from tristhana.infrastructure.db.accounts import SqlAccountRepository
from tristhana.infrastructure.db.days import SqlDayLogRepository
from tristhana.infrastructure.db.notifications import SqlNotificationRepository

pytestmark = pytest.mark.db

KEYS = "1:" + base64.b64encode(b"\x07" * 32).decode()
OTHER_KEYS = "2:" + base64.b64encode(b"\x08" * 32).decode()
ZONE = "Asia/Almaty"
L, K, T = DayStatus.LADIES, DayStatus.SICK, DayStatus.TRAVEL
d, p = cases.d, cases.p
WINDOW = (d(-30), d(30))


def _periods_repo(engine: AsyncEngine, keys: str = KEYS) -> Any:
    from tristhana.infrastructure.db.rest_periods import SqlRestPeriodRepository

    return SqlRestPeriodRepository(engine, FieldCipher(keys))


def _days(engine: AsyncEngine, keys: str = KEYS) -> SqlDayLogRepository:
    return SqlDayLogRepository(engine, FieldCipher(keys))


async def _account(engine: AsyncEngine, user: str = "42") -> UUID:
    repo = SqlAccountRepository(engine)
    a = await repo.create_with_identity(
        IdentityKey(IdentityProvider.TELEGRAM, user), NewAccount(display_name="A", locale="ru")
    )
    await repo.set_timezone_if_unset(a.id, ZONE)
    return a.id


async def _all(engine: AsyncEngine, me: UUID, keys: str = KEYS) -> list[RestPeriod]:
    view = await _days(engine, keys).range_with_moon(me, *WINDOW, "mysuru")
    return sorted(view.periods, key=lambda q: q.start)


@contextmanager
def _statements(engine: AsyncEngine) -> Generator[list[str]]:
    """The application statements sent while inside (pool pings and the like ignored)."""
    seen: list[str] = []

    def record(_conn: object, _cursor: object, statement: str, *_: object) -> None:
        if "tristhana." in statement:
            seen.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)


async def _raw(engine: AsyncEngine) -> list[tuple[date, date, int]]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT start_date, end_date, octet_length(sealed_kind)"
                " FROM tristhana.rest_period ORDER BY start_date"
            )
        )
        return [(r[0], r[1], r[2]) for r in rows]


# Seals and CHECKs


async def test_every_kind_is_sealed_with_the_same_length_and_no_plain_kind(
    engine: AsyncEngine,
) -> None:
    me = await _account(engine)
    repo = _periods_repo(engine)
    for period in (p(-20, -18, L), p(-10, -8, K), p(-5, -3, T)):
        await repo.place(me, period)

    assert [length for _, _, length in await _raw(engine)] == [42, 42, 42]
    async with engine.connect() as conn:
        columns = (
            await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns"
                    " WHERE table_schema = 'tristhana' AND table_name = 'rest_period'"
                )
            )
        ).scalars()
        assert set(columns) == {
            "account_id",
            "start_date",
            "end_date",
            "sealed_kind",
            "created_at",
            "updated_at",
        }
    assert await _all(engine, me) == [p(-20, -18, L), p(-10, -8, K), p(-5, -3, T)]


async def test_a_seal_moved_to_another_period_reads_as_plain_rest(
    engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    me = await _account(engine)
    repo = _periods_repo(engine)
    await repo.place(me, p(-10, -8, L))
    await repo.place(me, p(-5, -3, K))
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "UPDATE tristhana.rest_period SET sealed_kind = (SELECT sealed_kind FROM"
                " tristhana.rest_period WHERE start_date = :a) WHERE start_date = :b"
            ),
            {"a": d(-10), "b": d(-5)},
        )

    with caplog.at_level(logging.WARNING):
        found = await _all(engine, me)

    assert found == [p(-10, -8, L), p(-5, -3, DayStatus.REST)]
    assert caplog.records  # a warning, never the kind or the dates
    assert all("ladies" not in r.getMessage() for r in caplog.records)


async def test_an_unknown_key_reads_as_plain_rest(engine: AsyncEngine) -> None:
    me = await _account(engine)
    await _periods_repo(engine).place(me, p(-3, 1, L))

    assert await _all(engine, me, OTHER_KEYS) == [p(-3, 1, DayStatus.REST)]


@pytest.mark.parametrize(
    ("start", "end", "seal"),
    [
        (d(0), d(14), 42),  # 15 days
        (d(0), d(0), 42),  # end = start
        (d(0), d(-1), 42),  # end before start
        (d(0), d(3), 41),  # not a seal
        (date(1999, 12, 30), date(1999, 12, 31), 42),
    ],
)
async def test_checks_refuse_broken_periods(
    engine: AsyncEngine, start: date, end: date, seal: int
) -> None:
    me = await _account(engine)
    with pytest.raises(IntegrityError):
        async with engine.connect() as conn:
            await conn.execute(
                text(
                    "INSERT INTO tristhana.rest_period (account_id, start_date, end_date,"
                    " sealed_kind) VALUES (:a, :s, :e, :k)"
                ),
                {"a": me, "s": start, "e": end, "k": b"x" * seal},
            )


async def test_fourteen_days_fit_the_cap(engine: AsyncEngine) -> None:
    me = await _account(engine)
    await _periods_repo(engine).place(me, p(0, 13, K))
    assert await _raw(engine) == [(d(0), d(13), 42)]


async def test_periods_go_with_the_account(engine: AsyncEngine) -> None:
    me = await _account(engine)
    await _periods_repo(engine).place(me, p(0, 3, T))
    async with engine.connect() as conn:
        await conn.execute(text("DELETE FROM tristhana.account WHERE id = :a"), {"a": me})
    assert await _raw(engine) == []


# The overlap rule and the cut, one statement each, parity with the domain


@pytest.mark.parametrize("case", cases.PLACE_CASES, ids=lambda c: c.id)
async def test_place_parity_table(engine: AsyncEngine, case: cases.PlaceCase) -> None:
    me = await _account(engine)
    repo = _periods_repo(engine)
    for existing in case.existing:
        await repo.place(me, existing)

    with _statements(engine) as seen:
        placed = await repo.place(me, case.new)

    assert placed.period == case.new
    assert len(seen) == 1  # the write (the advisory lock touches no table)
    assert await _all(engine, me) == list(case.expected)


@pytest.mark.parametrize("case", cases.CUT_CASES, ids=lambda c: c.id)
async def test_cut_parity_table(engine: AsyncEngine, case: cases.CutCase) -> None:
    me = await _account(engine)
    await _periods_repo(engine).place(me, case.period)
    days = _days(engine)
    day = cases.d(case.day)

    with _statements(engine) as seen:
        if case.status is None:
            await days.delete(me, day)
        else:
            await days.upsert(me, DayLog(day, case.status), ZONE)

    assert len(seen) == 1
    assert await _all(engine, me) == list(case.expected)


async def test_end_from_in_one_statement_and_idempotent(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = _periods_repo(engine)
    await repo.place(me, p(-3, 2, T))
    await repo.place(me, p(5, 8, K))

    with _statements(engine) as seen:
        ended = await repo.end(me, d(-3), cases.BASE)
    again = await repo.end(me, d(-3), cases.BASE)
    removed = await repo.end(me, d(5), d(5))

    assert len(seen) == 1
    assert ended.period == again.period == p(-3, -1, T)
    assert (ended.kind, removed.period, removed.kind) == (T, None, K)  # removed: still named
    gone = await repo.end(me, d(5), d(5))
    assert (gone.period, gone.kind) == (None, None)
    assert await _all(engine, me) == [p(-3, -1, T)]


# The upsert snapshot (one statement: CTEs + RETURNING)


async def test_upsert_returns_the_day_before_and_the_periods_from_one_snapshot(
    engine: AsyncEngine,
) -> None:
    me = await _account(engine)
    days = _days(engine)
    await days.upsert(me, DayLog(d(-1), L), ZONE)  # sealed as rest
    await _periods_repo(engine).place(me, p(-1, 0, L))

    with _statements(engine) as seen:
        saved = await days.upsert(me, DayLog(d(0), L), ZONE)

    assert len(seen) == 1
    assert saved.day == DayLog(d(0), L)
    assert saved.prev is L  # unsealed, never "rest"
    assert list(saved.periods) == [p(-1, 0, L)]
    assert saved.cut is None
    assert saved.practice_on is False


async def test_upsert_practiced_returns_the_period_as_it_was_before_the_cut(
    engine: AsyncEngine,
) -> None:
    me = await _account(engine)
    await _periods_repo(engine).place(me, p(-2, 3, K))

    saved = await _days(engine).upsert(me, DayLog(d(0), DayStatus.PRACTICED), ZONE)

    assert saved.cut == p(-2, 3, K)
    assert await _all(engine, me) == [p(-2, -1, K)]


async def test_upsert_reads_practice_on_in_the_same_statement(engine: AsyncEngine) -> None:
    from tristhana.application.ports.notifications import ReminderPatch

    me = await _account(engine)
    await SqlNotificationRepository(engine).patch_practice(me, ReminderPatch(on=True), DEFAULTS)

    saved = await _days(engine).upsert(me, DayLog(d(0), K), ZONE)

    assert saved.practice_on is True


# insert-if-absent: ✅ and the reminder's 🧘 / 😌 (Q26)


async def test_insert_if_absent_seals_rest_and_never_overwrites(engine: AsyncEngine) -> None:
    me = await _account(engine)
    days = _days(engine)

    first = await days.insert_if_absent(me, DayLog(d(0), DayStatus.REST), ZONE)
    second = await days.insert_if_absent(me, DayLog(d(0), DayStatus.PRACTICED), ZONE)

    assert (first.inserted, second.inserted) == (True, False)
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT status, octet_length(sealed_status) FROM tristhana.day_log")
            )
        ).one()
    assert tuple(row) == ("rest", 42)  # the CHECK sealed_rest holds
    assert await days.list_range(me, d(0), d(0)) == [DayLog(d(0), DayStatus.REST)]


async def test_insert_if_absent_keeps_a_ladies_holiday(engine: AsyncEngine) -> None:
    me = await _account(engine)
    days = _days(engine)
    await days.upsert(me, DayLog(d(0), L), ZONE)

    tapped = await days.insert_if_absent(me, DayLog(d(0), DayStatus.REST), ZONE)

    assert not tapped.inserted
    assert await days.list_range(me, d(0), d(0)) == [DayLog(d(0), L)]


async def test_insert_if_absent_practiced_cuts_a_period_in_the_same_statement(
    engine: AsyncEngine,
) -> None:
    me = await _account(engine)
    await _periods_repo(engine).place(me, p(-2, 2, K))

    with _statements(engine) as seen:
        tapped = await _days(engine).insert_if_absent(me, DayLog(d(0), DayStatus.PRACTICED), ZONE)

    assert len(seen) == 1
    assert tapped.inserted
    assert tapped.cut == p(-2, 2, K)
    assert await _all(engine, me) == [p(-2, -1, K)]


async def test_insert_if_absent_on_a_logged_day_cuts_nothing(engine: AsyncEngine) -> None:
    me = await _account(engine)
    days = _days(engine)
    await days.upsert(me, DayLog(d(0), K), ZONE)
    await _periods_repo(engine).place(me, p(0, 3, K))

    tapped = await days.insert_if_absent(me, DayLog(d(0), DayStatus.PRACTICED), ZONE)

    assert (tapped.inserted, tapped.cut) == (False, None)
    assert await _all(engine, me) == [p(0, 3, K)]


# Reads: periods in the same statement


async def test_reads_return_overlapping_periods_unclipped_in_one_statement(
    engine: AsyncEngine,
) -> None:
    me = await _account(engine)
    repo = _periods_repo(engine)
    for period in (p(-20, -15, K), p(-13, 0, K), p(2, 4, L), p(9, 11, T)):
        await repo.place(me, period)
    days = _days(engine)

    with _statements(engine) as seen:
        view = await days.range_with_moon(me, d(0), d(7), "mysuru")
    history = await days.history(me, d(0), d(7))

    assert len(seen) == 1
    assert list(view.periods) == [p(-13, 0, K), p(2, 4, L)]  # starts 13 days before: found
    assert list(history.periods) == [p(-13, 0, K), p(2, 4, L)]


async def test_periods_are_keyed_by_account_and_start(engine: AsyncEngine) -> None:
    """The 14-day cap makes the overlap read a range scan of the primary key."""
    async with engine.connect() as conn:
        index = (
            await conn.execute(
                text(
                    "SELECT indexdef FROM pg_indexes WHERE schemaname = 'tristhana'"
                    " AND tablename = 'rest_period' AND indexname LIKE '%pkey'"
                )
            )
        ).scalar_one()
    assert "(account_id, start_date)" in index


# The tick: paused dates come with the logged days (no new statement)


async def test_candidates_carry_paused_dates_without_a_new_statement(
    engine: AsyncEngine,
) -> None:
    from tristhana.application.ports.notifications import ReminderPatch

    me = await _account(engine)
    notifications = SqlNotificationRepository(engine)
    await notifications.patch_practice(me, ReminderPatch(on=True), DEFAULTS)
    now = datetime(2026, 10, 26, 5, tzinfo=UTC)
    with _statements(engine) as before:
        await notifications.candidates(now, d(-7), DEFAULTS)
    await _periods_repo(engine).place(me, p(-9, 1, T))
    await _days(engine).upsert(me, DayLog(d(-1), DayStatus.PRACTICED), ZONE)  # cuts at d(-2)
    await _periods_repo(engine).place(me, p(0, 2, K))

    with _statements(engine) as after:
        [candidate] = await notifications.candidates(now, d(-7), DEFAULTS)

    assert len(after) == len(before)
    assert candidate.paused == {d(i) for i in (-7, -6, -5, -4, -3, -2, 0, 1, 2)}
    assert d(-1) in candidate.logged


async def test_candidates_without_practice_reminders_have_no_paused_dates(
    engine: AsyncEngine,
) -> None:
    me = await _account(engine)
    await _periods_repo(engine).place(me, p(0, 2, K))

    found = await SqlNotificationRepository(engine).candidates(
        datetime(2026, 10, 26, 5, tzinfo=UTC), d(-7), DEFAULTS
    )

    assert all(c.paused == frozenset() for c in found)


# account.hide_ladies


async def test_hide_ladies_defaults_to_shown_and_is_its_own_field_group(
    engine: AsyncEngine,
) -> None:
    me = await _account(engine)
    repo = SqlAccountRepository(engine)
    account = await repo.set_timezone_if_unset(me, "UTC")
    assert account.hide_ladies is False

    hidden = await repo.update_settings(
        me,
        ProfileChange(
            "X",
            True,
            "en",
            True,
            None,
            hide_ladies=True,  # type: ignore[call-arg]
            fields=frozenset({"hide_ladies"}),
        ),
    )

    assert hidden.hide_ladies is True
    assert hidden.display_name == "A"  # only the sent group is written


# Migration 0010 (expand-only)


async def _exists(engine: AsyncEngine, sql: str) -> bool:
    async with engine.connect() as conn:
        return (await conn.execute(text(sql))).scalar_one() > 0


_HAS_TABLE = (
    "SELECT count(*) FROM information_schema.tables"
    " WHERE table_schema = 'tristhana' AND table_name = 'rest_period'"
)
_HAS_COLUMN = (
    "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'tristhana'"
    " AND table_name = 'account' AND column_name = 'hide_ladies'"
)


async def test_0010_adds_rest_period_and_hide_ladies_and_downgrade_drops_them(
    migrated_url: str, engine: AsyncEngine
) -> None:
    me = await _account(engine)
    assert await _exists(engine, _HAS_TABLE)
    assert await _exists(engine, _HAS_COLUMN)
    await asyncio.to_thread(migrate.downgrade, migrated_url, "0009")
    try:
        assert not await _exists(engine, _HAS_TABLE)
        assert not await _exists(engine, _HAS_COLUMN)
    finally:
        await asyncio.to_thread(migrate.upgrade, migrated_url)
    assert await _exists(engine, _HAS_TABLE)
    account = await SqlAccountRepository(engine).set_timezone_if_unset(me, "UTC")
    assert account.hide_ladies is False  # existing rows get the default


def test_0010_tables_match_the_metadata(migrated_url: str) -> None:
    migrate.check(migrated_url)


# Review fixes: the restore gate, the per-account lock, the pause read, the reminder flag


async def test_restore_needs_a_practiced_day_inside_and_is_one_statement(
    engine: AsyncEngine,
) -> None:
    me = await _account(engine)
    repo = _periods_repo(engine)
    await repo.place(me, p(-20, -18, K))  # an older period a forged keep must not touch
    days = _days(engine)
    await days.upsert(me, DayLog(d(-14), DayStatus.PRACTICED), ZONE)  # before the range

    with _statements(engine) as seen:
        forged = await repo.restore(me, p(-13, 0, K), cases.BASE)

    assert forged is None
    assert len(seen) == 1
    assert await _all(engine, me) == [p(-20, -18, K)]  # nothing written, nothing cut
    await days.upsert(me, DayLog(d(-2), DayStatus.PRACTICED), ZONE)

    kept = await repo.restore(me, p(-4, 2, K), cases.BASE)

    assert kept == p(-4, 2, K)
    assert p(-4, 2, K) in await _all(engine, me)


async def test_restore_ignores_practice_after_today(engine: AsyncEngine) -> None:
    """Only [start, min(end, today)] counts (a later day can't be logged anyway)."""
    me = await _account(engine)
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "INSERT INTO tristhana.day_log (account_id, local_date, status)"
                " VALUES (:a, :d, 'practiced')"
            ),
            {"a": me, "d": d(1)},
        )

    assert await _periods_repo(engine).restore(me, p(-1, 3, K), cases.BASE) is None


async def test_concurrent_places_never_overlap(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = _periods_repo(engine)

    for _ in range(5):
        await asyncio.gather(repo.place(me, p(0, 4, L)), repo.place(me, p(2, 6, K)))
        found = await _all(engine, me)
        assert found  # one of them, or both adjacent
        for a, b in itertools.pairwise(found):
            assert a.end < b.start  # coverage never overlaps, whichever ran first


async def test_place_says_whether_practice_reminders_are_on(engine: AsyncEngine) -> None:
    from tristhana.application.ports.notifications import ReminderPatch

    me = await _account(engine)
    repo = _periods_repo(engine)
    assert (await repo.place(me, p(0, 2, K))).practice_on is False
    await SqlNotificationRepository(engine).patch_practice(me, ReminderPatch(on=True), DEFAULTS)

    with _statements(engine) as seen:
        placed = await repo.place(me, p(0, 3, K))

    assert placed.practice_on is True
    assert len(seen) == 1


async def test_the_pause_read_survives_two_covering_periods(engine: AsyncEngine) -> None:
    """Should two ever overlap (raw rows here), the latest start wins, never an error."""
    me = await _account(engine)
    repo = _periods_repo(engine)
    await repo.place(me, p(-3, 3, K))
    async with engine.connect() as conn:  # a second row covering today, bypassing `place`
        await conn.execute(
            text(
                "INSERT INTO tristhana.rest_period (account_id, start_date, end_date,"
                " sealed_kind) SELECT account_id, :s, :e, sealed_kind FROM"
                " tristhana.rest_period WHERE account_id = :a"
            ),
            {"a": me, "s": d(-1), "e": d(2)},
        )
    notifications = SqlNotificationRepository(engine)

    _, pause = await notifications.settings_with_pause(me, DEFAULTS, cases.BASE)
    _, patched = await notifications.patch_with_pause(me, {"daily_cap": 2}, DEFAULTS, cases.BASE)

    assert pause is not None
    assert (pause.start, pause.until) == (d(-1), d(2))
    assert patched == pause


async def test_patch_returns_the_pause_in_the_same_statement(engine: AsyncEngine) -> None:
    me = await _account(engine)
    await _periods_repo(engine).place(me, p(-1, 3, T))
    notifications = SqlNotificationRepository(engine)

    with _statements(engine) as seen:
        settings, pause = await notifications.patch_with_pause(
            me, {"practice_on": True}, DEFAULTS, cases.BASE
        )
    _, none = await notifications.patch_with_pause(me, {"daily_cap": 2}, DEFAULTS, d(5))

    assert len(seen) == 1
    assert settings.practice.on is True
    assert pause is not None
    assert (pause.start, pause.until) == (d(-1), d(3))
    assert none is None
