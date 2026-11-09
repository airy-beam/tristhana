"""Migration 0024 `announcement` and the storage wiring (NT-03 spec §6; ADR-0038), without a
database: the head, the columns, the cascades, the mute columns, the NT-01 switch, the export
coverage and `is_account_gone`. CHECKs, up/down and `alembic check` run on Postgres in
`test_db_announcements.py`."""

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.exc import DBAPIError

from tristhana.application.ports.storage import StorageUnavailable
from tristhana.infrastructure.db import tables
from tristhana.infrastructure.db.engine import is_account_gone
from tristhana.infrastructure.db.export import EXCLUDED_TABLES, EXPORTED_TABLES
from tristhana.infrastructure.db.migrate import alembic_config
from tristhana.infrastructure.db.storage import UnconfiguredStorage


def _table(name: str) -> Any:
    table = tables.metadata.tables.get(f"tristhana.{name}")
    assert table is not None
    return table


def test_0024_follows_0023_and_is_the_head() -> None:
    script = ScriptDirectory.from_config(alembic_config("postgresql://unused"))
    revision = script.get_revision("0024")
    assert revision is not None
    assert revision.down_revision == "0023"
    assert script.get_current_head() == "0024"


def test_the_columns() -> None:
    a = _table("announcement")
    assert set(a.c.keys()) == {
        "id",
        "author_id",
        "shala_id",
        "text",
        "audience",
        "pinned_until",
        "created_at",
    }
    assert {c.name for c in a.columns if c.nullable} == {"shala_id", "pinned_until"}


def test_both_keys_cascade() -> None:
    a = _table("announcement")
    keys = {fk.name: (fk.referred_table.name, fk.ondelete) for fk in a.foreign_key_constraints}
    assert keys == {
        "announcement_author_id_fkey": ("account", "CASCADE"),
        "announcement_shala_id_fkey": ("shala", "CASCADE"),
    }


def test_mutes_and_the_switch() -> None:
    for name in ("teacher_link", "shala_staff", "shala_student"):
        column = _table(name).c.announcements_muted
        assert column.nullable is False, name
        assert column.server_default is not None, name
    assert _table("notification_settings").c.announcements_on.nullable is True


def test_the_ledger_category() -> None:
    checks = [
        str(c.sqltext)
        for c in _table("notification_delivery").constraints
        if c.__class__.__name__ == "CheckConstraint"
    ]
    assert any("'announcement'" in c for c in checks), checks


def test_exported_as_my_own() -> None:
    assert "announcement" in EXPORTED_TABLES
    assert "announcement" not in EXCLUDED_TABLES


def test_announcing_as_the_account_goes_is_account_gone() -> None:
    orig = SimpleNamespace(
        sqlstate="23503",
        constraint_name="announcement_author_id_fkey",
        __cause__=None,
    )
    error = DBAPIError("INSERT", {}, orig)  # pyright: ignore[reportArgumentType]
    assert is_account_gone(error)


async def test_unconfigured_storage_has_unavailable_announcements() -> None:
    repo = UnconfiguredStorage().announcements
    with pytest.raises(StorageUnavailable):
        await repo.set_mute(uuid4(), None, True)  # type: ignore[arg-type]
