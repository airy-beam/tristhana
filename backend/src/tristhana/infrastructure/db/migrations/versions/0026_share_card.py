"""share_card: share card PNGs kept 24 h behind a capability URL

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-09

Expand-only (ADR-0014, ST-07, ADR-0040): one new table, which the previous revision ignores.
The token is stored only as its SHA-256; the row goes with its account and the tick deletes
it after `expires_at`. Table grants come from the default privileges (0001, 0015).
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | None = None
depends_on: str | None = None
SCHEMA = "tristhana"


def upgrade() -> None:
    op.create_table(
        "share_card",
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("format", sa.Text(), nullable=False),
        sa.Column("png", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "octet_length(token_hash) = 32", name=op.f("share_card_token_hash_length_check")
        ),
        sa.CheckConstraint(
            "kind IN ('month', 'year', 'asana', 'count')", name=op.f("share_card_kind_check")
        ),
        sa.CheckConstraint("format IN ('story', 'square')", name=op.f("share_card_format_check")),
        sa.CheckConstraint("octet_length(png) <= 2000000", name=op.f("share_card_png_size_check")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["tristhana.account.id"],
            name=op.f("share_card_account_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("token_hash", name=op.f("share_card_pkey")),
        schema=SCHEMA,
    )
    op.create_index(
        "share_card_account_id_created_at_idx",
        "share_card",
        ["account_id", "created_at"],
        schema=SCHEMA,
    )
    op.create_index("share_card_expires_at_idx", "share_card", ["expires_at"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("share_card", schema=SCHEMA)
