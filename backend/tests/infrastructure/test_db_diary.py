"""Diary notes on real Postgres (PR-07, ADR-0025): sealed at rest (no plaintext bytes, a
valid seal), the AAD binding (a seal moved to another date or account reads as unreadable),
a retired key (unreadable, row kept), one statement per method, the notes in
`range_with_moon` (still one statement; `list_range` and `history` never touch the table),
independence from the day log (status changes and clearing keep it, 🌸 and 😌 rows look the
same), the CHECKs, the account cascade, and migration 0013.

`SqlDiaryRepository` and the domain types are imported inside the tests (test-first)."""

import asyncio
import base64
import itertools
import logging
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.application.ports.storage import StorageUnavailable
from tristhana.domain.accounts import IdentityKey, IdentityProvider, NewAccount
from tristhana.domain.days import DayLog, DayStatus
from tristhana.infrastructure.crypto import FieldCipher, MissingCipher
from tristhana.infrastructure.db import migrate
from tristhana.infrastructure.db.accounts import SqlAccountRepository
from tristhana.infrastructure.db.days import SqlDayLogRepository

pytestmark = pytest.mark.db

KEYS = "1:" + base64.b64encode(b"\x07" * 32).decode()
OTHER_KEYS = "2:" + base64.b64encode(b"\x08" * 32).decode()
ROTATED = f"{OTHER_KEYS},{KEYS}"  # a new key first; the old one still opens
ZONE = "Asia/Almaty"
SAT, SUN, MON = date(2026, 10, 24), date(2026, 10, 25), date(2026, 10, 26)
ASCII = "Felt light today, teacher gave Pasasana"
UTF8 = "Сегодня было легко 🧘 дыхание ровное"
_users = itertools.count(7_000)


def _repo(engine: AsyncEngine, keys: str = KEYS) -> Any:
    from tristhana.infrastructure.db.diary import SqlDiaryRepository

    return SqlDiaryRepository(engine, FieldCipher(keys))


def _note(value: str | None) -> Any:
    from tristhana.domain.diary import DiaryNote

    return DiaryNote(value)


def _days(engine: AsyncEngine, keys: str = KEYS) -> SqlDayLogRepository:
    return SqlDayLogRepository(engine, FieldCipher(keys))


def _aad(account_id: UUID, day: date) -> bytes:
    return b"diary_note.sealed_text|" + account_id.bytes + day.isoformat().encode()


async def _account(engine: AsyncEngine) -> UUID:
    account = await SqlAccountRepository(engine).create_with_identity(
        IdentityKey(IdentityProvider.TELEGRAM, str(next(_users))),
        NewAccount(display_name="A", locale="en"),
    )
    return account.id


async def _raw(engine: AsyncEngine) -> list[tuple[UUID, date, bytes]]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT account_id, local_date, sealed_text FROM tristhana.diary_note"
                " ORDER BY local_date"
            )
        )
        return [(r[0], r[1], bytes(r[2])) for r in rows]


async def _count(engine: AsyncEngine) -> int:
    async with engine.connect() as conn:
        return (await conn.execute(text("SELECT count(*) FROM tristhana.diary_note"))).scalar_one()


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


# Round trip, one statement each


async def test_save_get_delete_round_trip_one_statement_each(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = _repo(engine)

    with _statements(engine) as saving:
        await repo.save(me, MON, ASCII)
    with _statements(engine) as reading:
        found = await repo.get(me, MON)
    with _statements(engine) as deleting:
        await repo.delete(me, MON)

    assert found == _note(ASCII)
    assert (len(saving), len(reading), len(deleting)) == (1, 1, 1)
    assert await repo.get(me, MON) is None


async def test_save_replaces_the_note_in_place(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = _repo(engine)
    await repo.save(me, MON, "first")

    await repo.save(me, MON, "second")

    assert await repo.get(me, MON) == _note("second")
    assert await _count(engine) == 1


async def test_delete_is_idempotent(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = _repo(engine)
    await repo.save(me, MON, ASCII)

    await repo.delete(me, MON)
    await repo.delete(me, MON)
    await repo.delete(me, SUN)  # never had one

    assert await _count(engine) == 0


async def test_the_longest_note_fits(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = _repo(engine)
    longest = "🧘" * 2000  # 8000 UTF-8 bytes: the CHECK's upper bound

    await repo.save(me, MON, longest)

    assert await repo.get(me, MON) == _note(longest)
    [(_, _, sealed)] = await _raw(engine)
    assert len(sealed) == 8041


async def test_notes_are_per_account(engine: AsyncEngine) -> None:
    me, other = await _account(engine), await _account(engine)
    await _repo(engine).save(me, MON, ASCII)

    assert await _repo(engine).get(other, MON) is None
    view = await _days(engine).range_with_moon(other, SAT, MON, "mysuru")
    assert view.notes == {}  # type: ignore[attr-defined]


# Sealed at rest (ADR-0016)


@pytest.mark.parametrize("plain", [ASCII, UTF8])
async def test_the_stored_bytes_never_contain_the_plaintext(
    engine: AsyncEngine, plain: str
) -> None:
    me = await _account(engine)

    await _repo(engine).save(me, MON, plain)

    [(account_id, day, sealed)] = await _raw(engine)
    encoded = plain.encode()
    assert (account_id, day) == (me, MON)
    assert encoded not in sealed
    for word in plain.split():
        assert word.encode() not in sealed
    assert sealed[0] == 1  # the active key's id
    assert len(sealed) == 1 + 24 + 16 + len(encoded)
    assert FieldCipher(KEYS).open(sealed, _aad(me, MON)) == encoded  # a valid seal


async def test_the_table_has_no_plain_text_or_status_column(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        columns = (
            await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns"
                    " WHERE table_schema = 'tristhana' AND table_name = 'diary_note'"
                )
            )
        ).scalars()
        assert set(columns) == {
            "account_id",
            "local_date",
            "sealed_text",
            "created_at",
            "updated_at",
        }


async def test_a_seal_copied_to_another_date_reads_as_unreadable(
    engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    me = await _account(engine)
    repo = _repo(engine)
    await repo.save(me, MON, ASCII)
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "INSERT INTO tristhana.diary_note (account_id, local_date, sealed_text)"
                " SELECT account_id, :d, sealed_text FROM tristhana.diary_note"
                " WHERE local_date = :src"
            ),
            {"d": SUN, "src": MON},
        )

    with caplog.at_level(logging.WARNING):
        moved = await repo.get(me, SUN)
        view = await _days(engine).range_with_moon(me, SAT, MON, "mysuru")

    assert moved == _note(None)
    assert view.notes == {SUN: _note(None), MON: _note(ASCII)}  # type: ignore[attr-defined]
    assert caplog.records  # a warning: the account uuid only
    assert any(str(me) in r.getMessage() for r in caplog.records)
    assert all("Pasasana" not in r.getMessage() for r in caplog.records)
    assert all(SUN.isoformat() not in r.getMessage() for r in caplog.records)
    assert await _count(engine) == 2  # kept: a restored key or an overwrite fixes it


async def test_a_seal_copied_to_another_account_reads_as_unreadable(engine: AsyncEngine) -> None:
    me, other = await _account(engine), await _account(engine)
    await _repo(engine).save(me, MON, ASCII)
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "INSERT INTO tristhana.diary_note (account_id, local_date, sealed_text)"
                " SELECT :other, local_date, sealed_text FROM tristhana.diary_note"
                " WHERE account_id = :me"
            ),
            {"other": other, "me": me},
        )

    assert await _repo(engine).get(other, MON) == _note(None)
    assert await _repo(engine).get(me, MON) == _note(ASCII)


async def test_tampered_bytes_read_as_unreadable(engine: AsyncEngine) -> None:
    me = await _account(engine)
    await _repo(engine).save(me, MON, ASCII)
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "UPDATE tristhana.diary_note SET sealed_text ="
                " set_byte(sealed_text, 30, get_byte(sealed_text, 30) # 1)"
            )
        )

    assert await _repo(engine).get(me, MON) == _note(None)


async def test_a_retired_key_reads_as_unreadable_and_keeps_the_row(engine: AsyncEngine) -> None:
    me = await _account(engine)
    await _repo(engine, KEYS).save(me, MON, ASCII)

    found = await _repo(engine, OTHER_KEYS).get(me, MON)
    view = await _days(engine, OTHER_KEYS).range_with_moon(me, SAT, MON, "mysuru")

    assert found == _note(None)
    assert view.notes == {MON: _note(None)}  # type: ignore[attr-defined]
    assert await _count(engine) == 1
    assert await _repo(engine, KEYS).get(me, MON) == _note(ASCII)  # the key restored


async def test_an_unreadable_note_can_be_overwritten_or_removed(engine: AsyncEngine) -> None:
    me = await _account(engine)
    await _repo(engine, KEYS).save(me, MON, "old")
    await _repo(engine, KEYS).save(me, SUN, "old too")
    repo = _repo(engine, OTHER_KEYS)

    await repo.save(me, MON, "new")
    await repo.delete(me, SUN)

    assert await repo.get(me, MON) == _note("new")
    assert await repo.get(me, SUN) is None


async def test_rotation_seals_with_the_new_key_and_opens_the_old(engine: AsyncEngine) -> None:
    me = await _account(engine)
    await _repo(engine, KEYS).save(me, SUN, "sealed with key 1")
    repo = _repo(engine, ROTATED)

    await repo.save(me, MON, "sealed with key 2")

    assert await repo.get(me, SUN) == _note("sealed with key 1")
    assert await repo.get(me, MON) == _note("sealed with key 2")
    assert [sealed[0] for _, _, sealed in await _raw(engine)] == [1, 2]


async def test_no_key_configured_is_storage_unavailable(engine: AsyncEngine) -> None:
    from tristhana.infrastructure.db.diary import SqlDiaryRepository

    me = await _account(engine)
    await _repo(engine).save(me, MON, ASCII)
    repo = SqlDiaryRepository(engine, MissingCipher())

    with pytest.raises(StorageUnavailable):
        await repo.save(me, SUN, ASCII)
    with pytest.raises(StorageUnavailable):
        await repo.get(me, MON)
    with pytest.raises(StorageUnavailable):
        await SqlDayLogRepository(engine, MissingCipher()).range_with_moon(me, SAT, MON, "mysuru")


# Reads for screens: in `range_with_moon`, one statement


async def test_range_with_moon_carries_notes_in_one_statement(engine: AsyncEngine) -> None:
    me = await _account(engine)
    days = _days(engine)
    await days.upsert(me, DayLog(MON, DayStatus.PRACTICED), ZONE)
    repo = _repo(engine)
    await repo.save(me, MON, ASCII)
    await repo.save(me, SUN, UTF8)  # a day never logged
    await repo.save(me, date(2026, 10, 1), "outside the range")

    with _statements(engine) as seen:
        view = await days.range_with_moon(me, SAT, MON, "mysuru")

    assert len(seen) == 1
    assert "diary_note" in seen[0]
    assert view.notes == {SUN: _note(UTF8), MON: _note(ASCII)}  # type: ignore[attr-defined]
    assert [d.local_date for d in view.days] == [MON]


async def test_only_the_first_row_carries_the_note_seals(engine: AsyncEngine) -> None:
    # Review S1: up to 8 KB per note must not repeat on every (day, slot) row.
    me = await _account(engine)
    days = _days(engine)
    for day in (SAT, SUN, MON):
        await days.upsert(me, DayLog(day, DayStatus.PRACTICED), ZONE)
    await _repo(engine).save(me, SUN, UTF8)
    rows: list[Any] = []
    original = days._days  # pyright: ignore[reportPrivateUsage]

    def spy(account_id: UUID, got: Any) -> Any:
        rows.extend(got)
        return original(account_id, got)

    days._days = spy  # type: ignore[method-assign]
    view = await days.range_with_moon(me, SAT, MON, "mysuru")

    assert view.notes == {SUN: _note(UTF8)}  # type: ignore[attr-defined]
    assert len(rows) == 3
    assert rows[0].note_seals is not None
    assert all(r.note_seals is None and r.note_dates is None for r in rows[1:])


async def test_range_with_moon_without_notes_is_an_empty_dict(engine: AsyncEngine) -> None:
    me = await _account(engine)

    view = await _days(engine).range_with_moon(me, SAT, MON, "mysuru")

    assert view.notes == {}  # type: ignore[attr-defined]


async def test_list_range_and_history_never_touch_diary_note(engine: AsyncEngine) -> None:
    me = await _account(engine)
    days = _days(engine)
    await days.upsert(me, DayLog(MON, DayStatus.PRACTICED), ZONE)
    await _repo(engine).save(me, MON, ASCII)

    with _statements(engine) as seen:
        await days.list_range(me, SAT, MON)
        await days.history(me, SAT, MON)
        await days.upsert(me, DayLog(MON, DayStatus.REST), ZONE)
        await days.delete(me, MON)

    assert len(seen) == 4
    assert all("diary_note" not in s for s in seen)


# Independent of the day log


@pytest.mark.parametrize("status", [s for s in DayStatus if s is not DayStatus.PRACTICED])
async def test_a_status_change_keeps_the_note(engine: AsyncEngine, status: DayStatus) -> None:
    me = await _account(engine)
    days = _days(engine)
    await days.upsert(me, DayLog(MON, DayStatus.PRACTICED), ZONE)
    await _repo(engine).save(me, MON, ASCII)

    await days.upsert(me, DayLog(MON, status), ZONE)

    assert await _repo(engine).get(me, MON) == _note(ASCII)


async def test_clearing_the_day_keeps_the_note(engine: AsyncEngine) -> None:
    me = await _account(engine)
    days = _days(engine)
    await days.upsert(me, DayLog(MON, DayStatus.SICK), ZONE)
    await _repo(engine).save(me, MON, ASCII)

    await days.delete(me, MON)

    assert await _repo(engine).get(me, MON) == _note(ASCII)


async def test_a_ladies_and_a_rest_days_note_rows_look_the_same(engine: AsyncEngine) -> None:
    me = await _account(engine)
    days = _days(engine)
    await days.upsert(me, DayLog(SUN, DayStatus.LADIES), ZONE)
    await days.upsert(me, DayLog(MON, DayStatus.REST), ZONE)
    repo = _repo(engine)
    await repo.save(me, SUN, ASCII)
    await repo.save(me, MON, ASCII)

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT account_id, octet_length(sealed_text), get_byte(sealed_text, 0)"
                    " FROM tristhana.diary_note ORDER BY local_date"
                )
            )
        ).all()

    assert [tuple(r) for r in rows] == [(me, 41 + len(ASCII), 1)] * 2


async def test_deleting_the_account_cascades(engine: AsyncEngine) -> None:
    me = await _account(engine)
    await _repo(engine).save(me, MON, ASCII)

    async with engine.connect() as conn:
        await conn.execute(text("DELETE FROM tristhana.account WHERE id = :id"), {"id": me})

    assert await _count(engine) == 0


# CHECKs


@pytest.mark.parametrize(
    ("day", "length"),
    [
        (MON, 41),  # shorter than an empty seal
        (MON, 8042),  # longer than 2000 code points x 4 bytes, sealed
        (date(1999, 12, 31), 42),
    ],
)
async def test_checks_refuse_broken_rows(engine: AsyncEngine, day: date, length: int) -> None:
    me = await _account(engine)

    with pytest.raises(IntegrityError):
        async with engine.connect() as conn:
            await conn.execute(
                text(
                    "INSERT INTO tristhana.diary_note (account_id, local_date, sealed_text)"
                    " VALUES (:a, :d, :s)"
                ),
                {"a": me, "d": day, "s": b"x" * length},
            )


@pytest.mark.parametrize("length", [42, 8041])
async def test_checks_allow_the_bounds(engine: AsyncEngine, length: int) -> None:
    me = await _account(engine)

    async with engine.connect() as conn:
        await conn.execute(
            text(
                "INSERT INTO tristhana.diary_note (account_id, local_date, sealed_text)"
                " VALUES (:a, :d, :s)"
            ),
            {"a": me, "d": date(2000, 1, 1), "s": b"x" * length},
        )

    assert await _count(engine) == 1


async def test_a_note_needs_an_account(engine: AsyncEngine) -> None:
    with pytest.raises(IntegrityError):
        await _repo(engine).save(uuid4(), MON, ASCII)


async def test_created_and_updated_at_are_set(engine: AsyncEngine) -> None:
    me = await _account(engine)
    await _repo(engine).save(me, MON, ASCII)

    async with engine.connect() as conn:
        row = (
            await conn.execute(text("SELECT created_at, updated_at FROM tristhana.diary_note"))
        ).one()

    assert row[0] is not None
    assert row[1] is not None
    assert row[0].tzinfo is not None


# Migration 0013 (expand-only)


_HAS_TABLE = (
    "SELECT count(*) FROM information_schema.tables"
    " WHERE table_schema = 'tristhana' AND table_name = 'diary_note'"
)


async def _exists(engine: AsyncEngine, sql: str) -> bool:
    async with engine.connect() as conn:
        return (await conn.execute(text(sql))).scalar_one() > 0


async def test_0013_adds_diary_note_and_downgrade_drops_it(
    migrated_url: str, engine: AsyncEngine
) -> None:
    me = await _account(engine)
    assert await _exists(engine, _HAS_TABLE)
    await asyncio.to_thread(migrate.downgrade, migrated_url, "0012")
    try:
        assert not await _exists(engine, _HAS_TABLE)
        # The previous revision works without the table.
        await _days(engine).upsert(me, DayLog(MON, DayStatus.REST), ZONE)
    finally:
        await asyncio.to_thread(migrate.upgrade, migrated_url)
    assert await _exists(engine, _HAS_TABLE)
    await _repo(engine).save(me, MON, ASCII)
    assert await _repo(engine).get(me, MON) == _note(ASCII)


def test_0013_tables_match_the_metadata(migrated_url: str) -> None:
    migrate.check(migrated_url)
