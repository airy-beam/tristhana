"""Progression on real Postgres (PR-08, ADR-0026): one statement per method, the
compare-and-set (a stale or racing write appends nothing), latest-only undo restoring the
position, items and previous event id (undoing the START unsets), the "Not new" answer
lapsing after any change, the practice save and presets joins (still one statement, with
`length_changed`), the CHECKs, cascades, and migration 0014."""

import asyncio
import base64
import itertools
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date
from uuid import UUID

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.application.practice_patch import PracticePatch
from tristhana.domain.accounts import IdentityKey, IdentityProvider, NewAccount
from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.practice import PracticeContext, PracticeLength
from tristhana.domain.progression import (
    STANDING_ONLY,
    Change,
    EventKind,
    Position,
    Progression,
)
from tristhana.infrastructure.crypto import FieldCipher
from tristhana.infrastructure.db import migrate
from tristhana.infrastructure.db.accounts import SqlAccountRepository
from tristhana.infrastructure.db.days import SqlDayLogRepository
from tristhana.infrastructure.db.practice import SqlPracticeRepository
from tristhana.infrastructure.db.progression import SqlProgressionRepository

pytestmark = pytest.mark.db

KEYS = "1:" + base64.b64encode(b"\x07" * 32).decode()
ON, MON = date(2026, 10, 27), date(2026, 10, 26)
NAVASANA = Position("primary", "navasana")
KURMASANA = Position("primary", "kurmasana")
SETU = Position("primary", "setu-bandhasana")
_users = itertools.count(9_000)


async def _account(engine: AsyncEngine) -> UUID:
    account = await SqlAccountRepository(engine).create_with_identity(
        IdentityKey(IdentityProvider.TELEGRAM, str(next(_users))),
        NewAccount(display_name="A", locale="en"),
    )
    return account.id


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


def _start(target: Position) -> Change:
    return Change(EventKind.START, ON, Progression(target), after=target)


def _given(before: Position, after: Position, items: frozenset[str] = frozenset()) -> Change:
    return Change(EventKind.GIVEN, ON, Progression(after, items), before, after)


def _item(at: Position, item: str, given: bool, items: frozenset[str]) -> Change:
    kind = EventKind.ITEM_GIVEN if given else EventKind.ITEM_REMOVED
    return Change(kind, ON, Progression(at, items), item=item)


async def test_unset_reads_empty_in_one_statement(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = SqlProgressionRepository(engine)
    with _statements(engine) as seen:
        view = await repo.get(me)
    assert len(seen) == 1
    assert view.progression is None
    assert view.events == ()
    assert not view.earlier.targets


async def test_apply_and_get_round_trip(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = SqlProgressionRepository(engine)
    with _statements(engine) as writing:
        start = await repo.apply(me, _start(NAVASANA), None, me)
    assert start is not None
    assert len(writing) == 1
    given = await repo.apply(me, _given(NAVASANA, KURMASANA), start.id, me)
    assert given is not None
    items = frozenset({"drop-backs"})
    item = await repo.apply(me, _item(KURMASANA, "drop-backs", True, items), given.id, me)
    assert item is not None

    with _statements(engine) as reading:
        view = await repo.get(me)
    assert len(reading) == 1
    assert view.progression == Progression(KURMASANA, items, item.id)
    assert view.earlier.targets == {NAVASANA, KURMASANA}
    assert view.earlier.items == {"drop-backs"}
    assert [e.kind for e in view.events] == [
        EventKind.ITEM_GIVEN,
        EventKind.GIVEN,
        EventKind.START,
    ]
    newest, middle, oldest = view.events
    assert newest.item == "drop-backs"
    assert newest.before is None
    assert newest.after is None
    assert middle.before == NAVASANA
    assert middle.after == KURMASANA
    assert oldest.before is None
    assert oldest.after == NAVASANA
    assert all(e.marked_by_self and e.occurred_on == ON for e in view.events)


async def test_standing_only_round_trips(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = SqlProgressionRepository(engine)
    start = await repo.apply(me, _start(STANDING_ONLY), None, me)
    assert start is not None
    await repo.apply(me, _given(STANDING_ONLY, NAVASANA), start.id, me)
    view = await repo.get(me)
    assert view.progression is not None
    assert view.progression.position == NAVASANA
    assert view.events[0].before == STANDING_ONLY
    assert view.events[1].after == STANDING_ONLY


async def test_a_stale_expected_id_appends_nothing(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = SqlProgressionRepository(engine)
    start = await repo.apply(me, _start(NAVASANA), None, me)
    assert start is not None
    assert await repo.apply(me, _start(SETU), None, me) is None  # set already exists
    assert await repo.apply(me, _given(NAVASANA, SETU), start.id + 100, me) is None
    view = await repo.get(me)
    assert len(view.events) == 1
    assert view.progression is not None
    assert view.progression.position == NAVASANA


async def test_expected_id_on_a_missing_row_appends_nothing(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = SqlProgressionRepository(engine)
    assert await repo.apply(me, _given(NAVASANA, SETU), 1, me) is None
    assert (await repo.get(me)).events == ()


async def test_two_racing_gives_leave_one_event(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = SqlProgressionRepository(engine)
    start = await repo.apply(me, _start(NAVASANA), None, me)
    assert start is not None
    results = await asyncio.gather(
        *(repo.apply(me, _given(NAVASANA, KURMASANA), start.id, me) for _ in range(3))
    )
    assert sum(r is not None for r in results) == 1
    view = await repo.get(me)
    assert len(view.events) == 2
    winner = next(r for r in results if r is not None)
    assert view.progression is not None
    assert view.progression.last_event_id == winner.id


async def test_undo_latest_restores_position_items_and_previous_id(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = SqlProgressionRepository(engine)
    start = await repo.apply(me, _start(NAVASANA), None, me)
    assert start is not None
    given = await repo.apply(me, _given(NAVASANA, KURMASANA), start.id, me)
    assert given is not None
    items = frozenset({"standing-up"})
    item = await repo.apply(me, _item(KURMASANA, "standing-up", True, items), given.id, me)
    assert item is not None

    assert not await repo.undo(me, given.id)  # not the latest
    with _statements(engine) as seen:
        assert await repo.undo(me, item.id)
    assert len(seen) == 1
    view = await repo.get(me)
    assert view.progression == Progression(KURMASANA, frozenset(), given.id)

    assert await repo.undo(me, given.id)
    view = await repo.get(me)
    assert view.progression == Progression(NAVASANA, frozenset(), start.id)
    assert view.earlier.targets == {NAVASANA}

    assert await repo.undo(me, start.id)
    view = await repo.get(me)
    assert view.progression is None
    assert view.events == ()
    assert not await repo.undo(me, start.id)


async def test_undo_of_a_removal_puts_the_item_back(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = SqlProgressionRepository(engine)
    start = await repo.apply(me, _start(SETU), None, me)
    assert start is not None
    added = await repo.apply(
        me, _item(SETU, "drop-backs", True, frozenset({"drop-backs"})), start.id, me
    )
    assert added is not None
    removed = await repo.apply(me, _item(SETU, "drop-backs", False, frozenset()), added.id, me)
    assert removed is not None
    assert await repo.undo(me, removed.id)
    view = await repo.get(me)
    assert view.progression is not None
    assert view.progression.items == {"drop-backs"}


async def test_not_new_lapses_after_any_change(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = SqlProgressionRepository(engine)
    await repo.dismiss_hint(me, KURMASANA)  # no row: nothing
    start = await repo.apply(me, _start(NAVASANA), None, me)
    assert start is not None
    with _statements(engine) as seen:
        await repo.dismiss_hint(me, KURMASANA)
    assert len(seen) == 1
    view = await repo.get(me)
    assert view.progression is not None
    assert view.progression.dismissed == KURMASANA
    item = await repo.apply(
        me, _item(NAVASANA, "drop-backs", True, frozenset({"drop-backs"})), start.id, me
    )
    assert item is not None
    view = await repo.get(me)
    assert view.progression is not None
    assert view.progression.dismissed is None


async def test_practice_save_joins_progression_and_reports_length_changes(
    engine: AsyncEngine,
) -> None:
    me = await _account(engine)
    days = SqlDayLogRepository(engine, FieldCipher(KEYS))
    await days.upsert(me, DayLog(ON, DayStatus.PRACTICED), "Asia/Almaty")
    practices, repo = SqlPracticeRepository(engine), SqlProgressionRepository(engine)
    start = await repo.apply(me, _start(NAVASANA), None, me)
    assert start is not None
    kurmasana = PracticeLength(("primary",), "kurmasana")

    with _statements(engine) as seen:
        saved = await practices.save(me, ON, PracticePatch.of(length=kurmasana))
    assert len(seen) == 1
    assert saved is not None
    assert saved.length_changed
    assert saved.progression == Progression(NAVASANA, frozenset(), start.id)

    same = await practices.save(me, ON, PracticePatch.of(length=kurmasana))
    assert same is not None
    assert not same.length_changed
    other = await practices.save(me, ON, PracticePatch.of(context=PracticeContext.MYSORE))
    assert other is not None
    assert not other.length_changed


async def test_presets_read_progression_in_one_statement(engine: AsyncEngine) -> None:
    me = await _account(engine)
    days = SqlDayLogRepository(engine, FieldCipher(KEYS))
    practices, repo = SqlPracticeRepository(engine), SqlProgressionRepository(engine)
    with _statements(engine) as seen:
        none, unset = await practices.recent_with_progression(me, ON, 60)
    assert (none, unset, len(seen)) == ([], None, 1)

    start = await repo.apply(me, _start(NAVASANA), None, me)
    assert start is not None
    _, set_only = await practices.recent_with_progression(me, ON, 60)
    assert set_only is not None
    assert set_only.position == NAVASANA

    await days.upsert(me, DayLog(MON, DayStatus.PRACTICED), "Asia/Almaty")
    length = PracticeLength(("primary",), "kurmasana")
    await practices.save(me, MON, PracticePatch.of(length=length))
    recent, found = await practices.recent_with_progression(me, ON, 60)
    assert [p.length for p in recent] == [length]
    assert found is not None
    assert found.position == NAVASANA
    assert recent == await practices.recent(me, ON, 60)


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO tristhana.progression (account_id, series, last_event_id)"
        " VALUES (:a, 'primary', 1)",
        "INSERT INTO tristhana.progression (account_id, last_event_id, hint_series, hint_key)"
        " VALUES (:a, 1, 'primary', 'navasana')",
        "INSERT INTO tristhana.progression_event (account_id, kind, occurred_on)"
        " VALUES (:a, 'unknown', '2026-10-27')",
        "INSERT INTO tristhana.progression_event (account_id, kind, item, occurred_on)"
        " VALUES (:a, 'given', 'drop-backs', '2026-10-27')",
        "INSERT INTO tristhana.progression_event (account_id, kind, occurred_on)"
        " VALUES (:a, 'item_given', '2026-10-27')",
        "INSERT INTO tristhana.progression_event (account_id, kind, to_series, occurred_on)"
        " VALUES (:a, 'start', 'primary', '2026-10-27')",
        "INSERT INTO tristhana.progression_event (account_id, kind, occurred_on)"
        " VALUES (:a, 'start', '1999-12-31')",
    ],
)
async def test_checks_reject_bad_rows(engine: AsyncEngine, sql: str) -> None:
    me = await _account(engine)
    with pytest.raises(IntegrityError):
        async with engine.connect() as conn:
            await conn.execute(text(sql), {"a": me})


async def test_account_delete_cascades_and_marked_by_is_set_null(engine: AsyncEngine) -> None:
    me, teacher = await _account(engine), await _account(engine)
    repo = SqlProgressionRepository(engine)
    await repo.apply(me, _start(NAVASANA), None, teacher)  # Phase 3: a teacher marks it
    view = await repo.get(me)
    assert not view.events[0].marked_by_self
    async with engine.connect() as conn:
        await conn.execute(text("DELETE FROM tristhana.account WHERE id = :a"), {"a": teacher})
    assert len((await repo.get(me)).events) == 1
    async with engine.connect() as conn:
        await conn.execute(text("DELETE FROM tristhana.account WHERE id = :a"), {"a": me})
        left = await conn.execute(text("SELECT count(*) FROM tristhana.progression_event"))
        assert left.scalar_one() == 0


_HAS_TABLES = (
    "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'tristhana'"
    " AND table_name IN ('progression', 'progression_event')"
)


async def test_0014_adds_the_tables_and_downgrade_drops_them(
    migrated_url: str, engine: AsyncEngine
) -> None:
    me = await _account(engine)
    await asyncio.to_thread(migrate.downgrade, migrated_url, "0013")  # via 0015
    try:
        async with engine.connect() as conn:
            assert (await conn.execute(text(_HAS_TABLES))).scalar_one() == 0
    finally:
        await asyncio.to_thread(migrate.upgrade, migrated_url)
    async with engine.connect() as conn:
        assert (await conn.execute(text(_HAS_TABLES))).scalar_one() == 2
    assert await SqlProgressionRepository(engine).apply(me, _start(NAVASANA), None, me)


def test_0015_follows_0014_and_is_the_head() -> None:
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(migrate.alembic_config("postgresql://unused"))
    revision = script.get_revision("0015")
    assert revision is not None
    assert revision.down_revision == "0014"
    assert script.get_current_head() == "0015"


def test_0014_tables_match_the_metadata(migrated_url: str) -> None:
    migrate.check(migrated_url)
