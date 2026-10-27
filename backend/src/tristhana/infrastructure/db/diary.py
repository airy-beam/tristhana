"""`DiaryRepository` on Postgres (PR-07, ADR-0025). The text is sealed with the field cipher
(ADR-0016); the AAD binds it to its account and date, so a ciphertext moved to another row
can't be read. This adapter (with `days.py` for the day-screen read) is the only place
that opens notes."""

import logging
from collections.abc import Sequence
from datetime import date
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import aggregate_order_by, insert
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql.elements import Label

from tristhana.domain.diary import DiaryNote
from tristhana.infrastructure.crypto import UnreadableSeal
from tristhana.infrastructure.db.engine import connection
from tristhana.infrastructure.db.tables import diary_note

log = logging.getLogger(__name__)


class Cipher(Protocol):
    def seal(self, plaintext: bytes, aad: bytes) -> bytes: ...
    def open(self, sealed: bytes, aad: bytes) -> bytes: ...


def _aad(account_id: UUID, local_date: date) -> bytes:
    return b"diary_note.sealed_text|" + account_id.bytes + local_date.isoformat().encode()


def open_note(cipher: Cipher, account_id: UUID, local_date: date, sealed: bytes) -> DiaryNote:
    """The note, or `DiaryNote(None)` when its seal can't be opened (the row is kept)."""
    try:
        return DiaryNote(cipher.open(bytes(sealed), _aad(account_id, local_date)).decode())
    except (UnreadableSeal, UnicodeDecodeError):
        log.warning("unreadable diary_note seal for account %s", account_id)  # never the text
        return DiaryNote(None)


def note_arrays(account_id: UUID, start: date, end: date) -> tuple[Label[Any], Label[Any]]:
    """Scalar subqueries over the PK range: the dates and seals of the notes in [start, end]
    (`note_dates`, `note_seals`), so a day read stays one statement."""
    window = (diary_note.c.account_id == account_id) & diary_note.c.local_date.between(start, end)

    def agg(column: Any, label: str) -> Label[Any]:
        ordered = aggregate_order_by(column, diary_note.c.local_date)
        return select(func.array_agg(ordered)).where(window).scalar_subquery().label(label)

    return agg(diary_note.c.local_date, "note_dates"), agg(diary_note.c.sealed_text, "note_seals")


def open_notes(
    cipher: Cipher,
    account_id: UUID,
    dates: Sequence[date] | None,
    seals: Sequence[bytes] | None,
) -> dict[date, DiaryNote]:
    return {
        d: open_note(cipher, account_id, d, s)
        for d, s in zip(dates or (), seals or (), strict=True)
    }


class SqlDiaryRepository:
    def __init__(self, engine: AsyncEngine, cipher: Cipher) -> None:
        self._engine = engine
        self._cipher = cipher

    async def save(self, account_id: UUID, local_date: date, text: str) -> None:
        sealed = self._cipher.seal(text.encode(), _aad(account_id, local_date))
        stmt = insert(diary_note).values(
            account_id=account_id, local_date=local_date, sealed_text=sealed
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[diary_note.c.account_id, diary_note.c.local_date],
            set_={"sealed_text": sealed, "updated_at": func.now()},
        )
        async with connection(self._engine) as conn:
            await conn.execute(stmt)

    async def get(self, account_id: UUID, local_date: date) -> DiaryNote | None:
        stmt = select(diary_note.c.sealed_text).where(
            diary_note.c.account_id == account_id, diary_note.c.local_date == local_date
        )
        async with connection(self._engine) as conn:
            sealed = (await conn.execute(stmt)).scalar_one_or_none()
        return None if sealed is None else open_note(self._cipher, account_id, local_date, sealed)

    async def delete(self, account_id: UUID, local_date: date) -> None:
        stmt = delete(diary_note).where(
            diary_note.c.account_id == account_id, diary_note.c.local_date == local_date
        )
        async with connection(self._engine) as conn:
            await conn.execute(stmt)
