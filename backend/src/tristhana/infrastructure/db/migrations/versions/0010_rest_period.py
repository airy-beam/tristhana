"""rest period: multi-day 🌸 / sick / travel with a sealed kind, and account.hide_ladies

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-26

Expand-only (ADR-0014, WH-01 part 2, ADR-0023): a new table and a column with a default;
no data change, and the previous revision ignores both. The kind is sealed on every row
(no plain kind column), so a 🌸 period looks like a sick or travel one. The 14-day cap is
the only length CHECK: the 🌸 limit of 7 is a domain rule (the kind is sealed).
"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | None = None
depends_on: str | None = None

SCHEMA = "tristhana"


def _timestamp(name: str) -> sa.Column[datetime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def upgrade() -> None:
    # The app role gets DML through the default privileges set in 0001.
    op.create_table(
        "rest_period",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("sealed_kind", sa.LargeBinary(), nullable=False),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint("end_date > start_date", name="rest_period_period_order_check"),
        sa.CheckConstraint("end_date - start_date <= 13", name="rest_period_period_length_check"),
        sa.CheckConstraint(
            "octet_length(sealed_kind) = 42", name="rest_period_sealed_length_check"
        ),
        sa.CheckConstraint("start_date >= '2000-01-01'", name="rest_period_start_date_min_check"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["tristhana.account.id"],
            name="rest_period_account_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("account_id", "start_date", name="rest_period_pkey"),
        schema=SCHEMA,
    )
    op.add_column(
        "account",
        sa.Column("hide_ladies", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("account", "hide_ladies", schema=SCHEMA)
    op.drop_table("rest_period", schema=SCHEMA)
