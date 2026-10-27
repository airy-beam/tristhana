"""Migration 0012 and the table metadata (PR-06, spec §7), without a database."""

from alembic.script import ScriptDirectory

from tristhana.infrastructure.db import tables
from tristhana.infrastructure.db.migrate import alembic_config


def test_0012_follows_0011() -> None:
    script = ScriptDirectory.from_config(alembic_config("postgresql://unused"))
    revision = script.get_revision("0012")

    assert revision is not None  # the head is checked by the newest migration's test
    assert revision.down_revision == "0011"


def test_check_in_is_keyed_by_account_date_and_slot() -> None:
    table = tables.metadata.tables.get("tristhana.check_in")
    assert table is not None

    assert [c.name for c in table.primary_key.columns] == ["account_id", "local_date", "slot"]
    assert {c.name for c in table.columns} == {
        "account_id",
        "local_date",
        "slot",
        "mood",
        "energy",
        "effort",
        "tags",
        "created_at",
        "updated_at",
    }
    nullable = {c.name for c in table.columns if c.nullable}
    assert nullable == {"mood", "energy", "effort"}
    assert table.c.slot.server_default is not None
    assert table.c.tags.server_default is not None


def test_check_in_cascades_from_its_day() -> None:
    table = tables.metadata.tables.get("tristhana.check_in")
    assert table is not None

    [fk] = [c for c in table.foreign_key_constraints if c.referred_table.name == "day_log"]
    assert [c.name for c in fk.columns] == ["account_id", "local_date"]
    assert fk.ondelete is not None
    assert fk.ondelete.upper() == "CASCADE"


def test_check_in_has_range_checks_and_no_tag_value_check() -> None:
    table = tables.metadata.tables.get("tristhana.check_in")
    assert table is not None

    checks = [c for c in table.constraints if c.__class__.__name__ == "CheckConstraint"]
    sql = " ".join(str(getattr(c, "sqltext", "")) for c in checks)
    for column in ("slot", "mood", "energy", "effort"):
        assert column in sql
    assert "cardinality" in sql
    assert "'calm'" not in sql  # tag values are validated in the domain (ADR-0024)


def test_account_has_offer_check_in_defaulting_to_true() -> None:
    account = tables.metadata.tables["tristhana.account"]
    assert "offer_check_in" in account.c

    column = account.c.offer_check_in
    assert not column.nullable
    assert column.server_default is not None
    assert "true" in str(getattr(column.server_default, "arg", "")).lower()
