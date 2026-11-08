"""calendar_feed: one personal calendar subscription link per account

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-08

Expand-only (ADR-0014, SC-06, ADR-0036): one new table, which the previous revision ignores.
The token is stored as its SHA-256 (the lookup key, unique) and a sealed copy (ADR-0016);
the row goes with its account. Table grants come from the default privileges (0001, 0015).
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | None = None
depends_on: str | None = None
SCHEMA = "tristhana"


def upgrade() -> None:
    op.create_table(
        "calendar_feed",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("sealed_token", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("fetched_on", sa.Date(), nullable=True),
        sa.CheckConstraint(
            "octet_length(token_hash) = 32", name=op.f("calendar_feed_token_hash_length_check")
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["tristhana.account.id"],
            name=op.f("calendar_feed_account_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("account_id", name=op.f("calendar_feed_pkey")),
        sa.UniqueConstraint("token_hash", name=op.f("calendar_feed_token_hash_key")),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("calendar_feed", schema=SCHEMA)
