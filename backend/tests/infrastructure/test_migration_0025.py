"""Migration 0025 `class_attendance` (SC-05 spec §6; ADR-0039), without a database: the head,
the columns, the keys, the export coverage and `is_account_gone`. CHECKs, up/down and
`alembic check` run on Postgres in `test_db_attendance.py`."""

from typing import Any

from alembic.script import ScriptDirectory

from tristhana.infrastructure.db import tables
from tristhana.infrastructure.db.export import EXCLUDED_TABLES, EXPORTED_TABLES
from tristhana.infrastructure.db.migrate import alembic_config


def _table(name: str) -> Any:
    table = tables.metadata.tables.get(f"tristhana.{name}")
    assert table is not None
    return table


def test_0025_follows_0024() -> None:
    script = ScriptDirectory.from_config(alembic_config("postgresql://unused"))
    revision = script.get_revision("0025")
    assert revision is not None
    assert revision.down_revision == "0024"


def test_the_columns() -> None:
    a = _table("class_attendance")
    assert set(a.c.keys()) == {
        "id", "shala_id", "class_id", "occurrence_key", "account_id", "state", "class_type",
        "on_date", "starts_at", "zone", "created_at", "updated_at",
    }  # fmt: skip
    assert {c.name for c in a.columns if c.nullable} == {"class_id"}
    assert "marked_by" not in a.c  # who marked a row isn't kept (less personal data)


def test_the_keys() -> None:
    a = _table("class_attendance")
    keys = {fk.name: (fk.referred_table.name, fk.ondelete) for fk in a.foreign_key_constraints}
    assert keys == {
        "class_attendance_shala_id_fkey": ("shala", "CASCADE"),
        "class_attendance_class_id_fkey": ("shala_class", "SET NULL"),
        "class_attendance_account_id_fkey": ("account", "CASCADE"),
    }


def test_exported_as_my_own() -> None:
    assert "class_attendance" in EXPORTED_TABLES
    assert "class_attendance" not in EXCLUDED_TABLES
