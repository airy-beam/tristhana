"""Table definitions (SQLAlchemy Core, no ORM). Migrations must match: `alembic check`."""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    MetaData,
    Table,
    Text,
    Uuid,
    func,
    text,
)

SCHEMA = "tristhana"

metadata = MetaData(
    schema=SCHEMA,
    naming_convention={
        "ix": "%(table_name)s_%(column_0_name)s_idx",
        "ck": "%(table_name)s_%(constraint_name)s_check",
        "fk": "%(table_name)s_%(column_0_name)s_fkey",
        "pk": "%(table_name)s_pkey",
    },
)


def _timestamp(name: str) -> Column[datetime]:
    return Column(name, DateTime(timezone=True), nullable=False, server_default=func.now())


account = Table(
    "account",
    metadata,
    Column("id", Uuid(), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("display_name", Text()),
    Column("locale", Text(), nullable=False),
    Column("timezone", Text()),  # IANA name (ADR-0005); NULL until the device reports it
    _timestamp("created_at"),
    _timestamp("updated_at"),
    _timestamp("last_seen_at"),
    CheckConstraint("char_length(display_name) <= 64", name="display_name_length"),
    CheckConstraint("locale IN ('en', 'ru')", name="locale"),
)

identity = Table(
    "identity",
    metadata,
    Column("provider", Text(), primary_key=True),
    Column("provider_user_id", Text(), primary_key=True),
    Column(
        "account_id",
        Uuid(),
        ForeignKey(account.c.id, ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    _timestamp("created_at"),
    CheckConstraint("provider IN ('telegram')", name="provider"),
)
