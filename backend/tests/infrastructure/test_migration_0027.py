"""Migration 0027 `directory_listing` (ID-05 spec §9; ADR-0042), without a database: the head,
the columns, the two foreign keys and the export coverage. CHECKs, up/down and `alembic check`
run on Postgres in `test_db_directory_listing.py`."""

from alembic.script import ScriptDirectory

from tristhana.infrastructure.db import tables
from tristhana.infrastructure.db.export import EXCLUDED_TABLES, EXPORTED_TABLES
from tristhana.infrastructure.db.migrate import alembic_config


def test_0027_follows_0026_and_is_the_head() -> None:
    script = ScriptDirectory.from_config(alembic_config("postgresql://unused"))
    revision = script.get_revision("0027")
    assert revision is not None
    assert revision.down_revision == "0026"
    assert script.get_current_head() == "0027"


def test_the_table() -> None:
    t = tables.metadata.tables["tristhana.directory_listing"]
    assert set(t.c.keys()) == {
        "account_id", "status", "name_as_listed", "region", "declared_level", "note",
        "revision", "requested_at", "checked_on", "checked_by", "decided_at",
    }  # fmt: skip
    assert [c.name for c in t.primary_key.columns] == ["account_id"]
    assert {c.name for c in t.columns if not c.nullable} == {
        "account_id",
        "status",
        "revision",
        "requested_at",
    }
    rules = {fk.column_keys[0]: fk.ondelete for fk in t.foreign_key_constraints}
    assert rules == {"account_id": "CASCADE", "checked_by": "SET NULL"}


def test_exported_as_the_persons_own_request() -> None:
    assert "directory_listing" in EXPORTED_TABLES
    assert "directory_listing" not in EXCLUDED_TABLES
