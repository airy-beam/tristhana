"""Migration 0011: an index for the tick's paused-days read (WH-01 second review)."""

from alembic.script import ScriptDirectory

from tristhana.infrastructure.db import tables
from tristhana.infrastructure.db.migrate import alembic_config


def test_0011_is_the_head_after_0010() -> None:
    script = ScriptDirectory.from_config(alembic_config("postgresql://unused"))
    revision = script.get_revision("0011")

    assert script.get_current_head() == "0011"
    assert revision is not None
    assert revision.down_revision == "0010"


def test_rest_period_has_an_end_date_index() -> None:
    table = tables.metadata.tables["tristhana.rest_period"]

    assert {i.name: [c.name for c in i.columns] for i in table.indexes} == {
        "rest_period_end_date_idx": ["end_date"]
    }
