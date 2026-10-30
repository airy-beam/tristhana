"""practice milestone: the practice-count thresholds each account has passed

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-30

Expand-only (ADR-0014, GM-01 part 2, ADR-0028): a new table; no data change. The previous
revision ignores it (its day writes just don't record milestones). No backfill: accounts
already past a threshold are seeded silently on their next 🧘 write.
"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | None = None
depends_on: str | None = None

SCHEMA = "tristhana"


def _timestamp(name: str) -> sa.Column[datetime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def upgrade() -> None:
    # The app and backup roles get access through the default privileges (0001, backup_role).
    op.create_table(
        "practice_milestone",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("threshold", sa.Integer(), nullable=False),
        sa.Column("celebrated", sa.Boolean(), nullable=False),
        _timestamp("reached_at"),
        sa.CheckConstraint(
            "threshold BETWEEN 1 AND 100000", name="practice_milestone_threshold_check"
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["tristhana.account.id"],
            name="practice_milestone_account_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("account_id", "threshold", name="practice_milestone_pkey"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("practice_milestone", schema=SCHEMA)
