"""Migration 0013 and the `diary_note` metadata (PR-07, spec §7), plus the storage wiring,
without a database."""

from datetime import date
from uuid import uuid4

import pytest
from alembic.script import ScriptDirectory

from tristhana.application.ports.storage import StorageUnavailable
from tristhana.infrastructure.db import tables
from tristhana.infrastructure.db.migrate import alembic_config


def test_0013_follows_0012() -> None:
    script = ScriptDirectory.from_config(alembic_config("postgresql://unused"))
    revision = script.get_revision("0013")

    assert revision is not None  # the head is checked by the newest migration's test
    assert revision.down_revision == "0012"


def test_diary_note_is_keyed_by_account_and_date() -> None:
    table = tables.metadata.tables.get("tristhana.diary_note")
    assert table is not None

    assert [c.name for c in table.primary_key.columns] == ["account_id", "local_date"]
    assert {c.name for c in table.columns} == {
        "account_id",
        "local_date",
        "sealed_text",
        "created_at",
        "updated_at",
    }
    assert {c.name for c in table.columns if c.nullable} == set()
    assert table.c.created_at.server_default is not None
    assert table.c.updated_at.server_default is not None
    assert table.c.created_at.type.timezone is True  # type: ignore[attr-defined]


def test_diary_note_hangs_off_the_account_not_the_day() -> None:
    table = tables.metadata.tables.get("tristhana.diary_note")
    assert table is not None

    [fk] = list(table.foreign_key_constraints)  # no FK to day_log (ADR-0025)
    assert fk.referred_table.name == "account"
    assert [c.name for c in fk.columns] == ["account_id"]
    assert fk.ondelete is not None
    assert fk.ondelete.upper() == "CASCADE"


def test_diary_note_checks_the_sealed_length_and_the_date() -> None:
    table = tables.metadata.tables.get("tristhana.diary_note")
    assert table is not None

    checks = [c for c in table.constraints if c.__class__.__name__ == "CheckConstraint"]
    sql = " ".join(str(getattr(c, "sqltext", "")) for c in checks)
    assert "octet_length(sealed_text)" in sql
    assert "42" in sql
    assert "8041" in sql
    assert "2000-01-01" in sql


async def test_unconfigured_storage_has_an_unavailable_diary() -> None:
    from tristhana.infrastructure.db.storage import UnconfiguredStorage

    diary = UnconfiguredStorage().diary  # type: ignore[attr-defined]

    with pytest.raises(StorageUnavailable):
        await diary.save(uuid4(), date(2026, 10, 27), "hi")
    with pytest.raises(StorageUnavailable):
        await diary.get(uuid4(), date(2026, 10, 27))
    with pytest.raises(StorageUnavailable):
        await diary.delete(uuid4(), date(2026, 10, 27))
