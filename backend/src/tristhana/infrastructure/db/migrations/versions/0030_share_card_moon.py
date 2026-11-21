"""share cards: the moon day card (ST-10)

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-21

Expand-only (ADR-0014): the kind CHECK on `share_card` widens to 'moon', so the previous
revision keeps serving while this runs. The downgrade deletes moon cards (24 h lived,
derived) before it narrows the CHECK again.
"""

from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | None = None
depends_on: str | None = None
SCHEMA = "tristhana"
_KIND = "share_card_kind_check"


def upgrade() -> None:
    op.execute(f'ALTER TABLE {SCHEMA}.share_card DROP CONSTRAINT IF EXISTS "{_KIND}"')
    op.create_check_constraint(
        op.f(_KIND),
        "share_card",
        "kind IN ('month', 'year', 'asana', 'count', 'moon')",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.execute("DELETE FROM tristhana.share_card WHERE kind = 'moon'")
    op.drop_constraint(op.f(_KIND), "share_card", schema=SCHEMA)
    op.create_check_constraint(
        op.f(_KIND), "share_card", "kind IN ('month', 'year', 'asana', 'count')", schema=SCHEMA
    )
