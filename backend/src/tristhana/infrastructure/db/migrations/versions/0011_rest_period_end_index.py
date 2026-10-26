"""rest period end index: the tick reads covered dates by end_date (WH-01 second review)

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-27

Expand-only (ADR-0014): one index; the previous revision is unaffected. The tick's
paused-days read (`end_date >= :from` for all accounts with practice reminders on) would
otherwise scan the whole table; the primary key (account_id, start_date) can't serve it.
"""

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | None = None
depends_on: str | None = None

SCHEMA = "tristhana"


def upgrade() -> None:
    op.create_index("rest_period_end_date_idx", "rest_period", ["end_date"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("rest_period_end_date_idx", table_name="rest_period", schema=SCHEMA)
