"""day status log (PR-01, PR-04)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-18

Expand/contract: the previous revision keeps serving while this runs (ADR-0014).
"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None

SCHEMA = "tristhana"


def _timestamp(name: str) -> sa.Column[datetime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def upgrade() -> None:
    # The app role gets DML through the default privileges set in 0001.
    op.create_table(
        "day_log",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("sealed_status", sa.LargeBinary()),
        sa.Column("timezone", sa.Text()),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint(
            "status IN ('practiced', 'rest', 'moon', 'sick', 'travel', 'skipped')",
            name="day_log_status_check",
        ),
        sa.CheckConstraint(
            "(status = 'rest') = (sealed_status IS NOT NULL)", name="day_log_sealed_rest_check"
        ),
        sa.CheckConstraint("local_date >= '2000-01-01'", name="day_log_local_date_min_check"),
        sa.CheckConstraint("octet_length(sealed_status) = 42", name="day_log_sealed_length_check"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["tristhana.account.id"],
            name="day_log_account_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("account_id", "local_date", name="day_log_pkey"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("day_log", schema=SCHEMA)
