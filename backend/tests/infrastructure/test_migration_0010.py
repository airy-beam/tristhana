"""Migration 0010 and the table metadata (WH-01 part 2, spec §8), without a database."""

from alembic.script import ScriptDirectory

from tristhana.infrastructure.db import tables
from tristhana.infrastructure.db.migrate import alembic_config


def test_0010_rest_period_is_the_head_after_0009() -> None:
    script = ScriptDirectory.from_config(alembic_config("postgresql://unused"))
    revision = script.get_revision("0010")

    assert script.get_current_head() == "0010"
    assert revision is not None
    assert revision.down_revision == "0009"


def test_rest_period_table_is_keyed_by_account_and_start_with_a_sealed_kind() -> None:
    table = tables.metadata.tables["tristhana.rest_period"]

    assert [c.name for c in table.primary_key.columns] == ["account_id", "start_date"]
    assert {c.name for c in table.columns} == {
        "account_id",
        "start_date",
        "end_date",
        "sealed_kind",
        "created_at",
        "updated_at",
    }
    assert not any(c.nullable for c in table.columns)
    [fk] = table.c.account_id.foreign_keys
    assert fk.ondelete is not None
    assert fk.ondelete.upper() == "CASCADE"
    checks = {c.name for c in table.constraints if c.__class__.__name__ == "CheckConstraint"}
    assert {
        "rest_period_period_order_check",
        "rest_period_period_length_check",
        "rest_period_sealed_length_check",
    } <= {str(n) for n in checks}


def test_account_has_hide_ladies_defaulting_to_false() -> None:
    column = tables.metadata.tables["tristhana.account"].c.hide_ladies

    assert not column.nullable
    assert column.server_default is not None
    assert "false" in str(getattr(column.server_default, "arg", "")).lower()
