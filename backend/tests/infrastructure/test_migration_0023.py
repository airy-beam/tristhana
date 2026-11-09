"""Migration 0023 `calendar_feed` and the storage wiring (SC-06 spec §6; ADR-0036), without a
database: one row per account (PK `account_id`, cascade on delete), `token_hash` unique, the
sealed copy, `fetched_on` nullable; excluded from the export as a secret; an unconfigured
storage answers "unavailable". The CHECK, the cascade, up/down and `alembic check` run on
Postgres in `test_db_calendar_feed.py`."""

from datetime import date
from typing import Any
from uuid import uuid4

import pytest
from alembic.script import ScriptDirectory

from tristhana.application.ports.storage import StorageUnavailable
from tristhana.infrastructure.db import tables
from tristhana.infrastructure.db.export import EXCLUDED_TABLES, EXPORTED_TABLES
from tristhana.infrastructure.db.migrate import alembic_config
from tristhana.infrastructure.db.storage import UnconfiguredStorage


def _table() -> Any:
    table = tables.metadata.tables.get("tristhana.calendar_feed")
    assert table is not None
    return table


def test_0023_follows_0022() -> None:
    script = ScriptDirectory.from_config(alembic_config("postgresql://unused"))
    revision = script.get_revision("0023")

    assert revision is not None
    assert revision.down_revision == "0022"


def test_the_columns() -> None:
    feed = _table()

    assert set(feed.c.keys()) == {
        "account_id",
        "token_hash",
        "sealed_token",
        "created_at",
        "fetched_on",
    }
    for name in ("account_id", "token_hash", "sealed_token", "created_at"):
        assert feed.c[name].nullable is False, name
    assert feed.c.fetched_on.nullable is True
    assert feed.c.created_at.server_default is not None
    assert "now()" in str(feed.c.created_at.server_default.arg).lower()


def test_one_row_per_account_and_cascade() -> None:
    feed = _table()

    assert [c.name for c in feed.primary_key.columns] == ["account_id"]
    [fk] = list(feed.c.account_id.foreign_keys)
    assert (fk.column.table.name, fk.ondelete) == ("account", "CASCADE")


def test_the_hash_is_unique() -> None:
    feed = _table()

    unique = {
        tuple(c.name for c in constraint.columns)
        for constraint in feed.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    } | {tuple(c.name for c in index.columns) for index in feed.indexes if index.unique}
    assert ("token_hash",) in unique or feed.c.token_hash.unique is True


def test_the_hash_length_is_checked() -> None:
    checks = [
        str(c.sqltext) for c in _table().constraints if c.__class__.__name__ == "CheckConstraint"
    ]

    assert any("token_hash" in c and "32" in c for c in checks), checks


def test_the_link_is_a_secret_never_exported() -> None:
    assert "calendar_feed" not in EXPORTED_TABLES
    assert "secret" in EXCLUDED_TABLES["calendar_feed"]


async def test_unconfigured_storage_has_an_unavailable_feed() -> None:
    feed = UnconfiguredStorage().calendar_feed  # pyright: ignore[reportAttributeAccessIssue]

    with pytest.raises(StorageUnavailable):
        await feed.get(uuid4())
    with pytest.raises(StorageUnavailable):
        await feed.account_by_token(b"\x00" * 32, date(2026, 11, 9))
