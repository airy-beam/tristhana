"""Migration 0026 `share_card` (ST-07 spec §6; ADR-0040), without a database: its place, the
columns, the key, the cascade and the export exclusion. CHECKs, up/down and `alembic check`
run on Postgres in `test_db_share_cards.py`."""

from alembic.script import ScriptDirectory

from tristhana.infrastructure.db import tables
from tristhana.infrastructure.db.export import EXCLUDED_TABLES, EXPORTED_TABLES
from tristhana.infrastructure.db.migrate import alembic_config


def test_0026_follows_0025() -> None:
    script = ScriptDirectory.from_config(alembic_config("postgresql://unused"))
    revision = script.get_revision("0026")
    assert revision is not None
    assert revision.down_revision == "0025"


def test_the_table() -> None:
    t = tables.metadata.tables["tristhana.share_card"]
    assert set(t.c.keys()) == {
        "token_hash", "account_id", "kind", "format", "png", "created_at", "expires_at",
        "sent_at",
    }  # fmt: skip
    assert [c.name for c in t.primary_key.columns] == ["token_hash"]
    assert {c.name for c in t.columns if c.nullable} == {"sent_at"}
    (fk,) = t.foreign_key_constraints
    assert (fk.referred_table.name, fk.ondelete) == ("account", "CASCADE")


def test_never_exported() -> None:
    assert "share_card" in EXCLUDED_TABLES
    assert "share_card" not in EXPORTED_TABLES
