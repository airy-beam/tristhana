"""Table definitions (SQLAlchemy Core, no ORM). Migrations must match: `alembic check`."""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    LargeBinary,
    MetaData,
    PrimaryKeyConstraint,
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

# PR-01. `status` is the public value: a ladies' holiday is stored as 'rest', and every
# 'rest' row carries `sealed_status` (the true value, encrypted), so the two are
# indistinguishable here (ADR-0016). 'ladies' is not a valid plain value.
day_log = Table(
    "day_log",
    metadata,
    Column("account_id", Uuid(), ForeignKey(account.c.id, ondelete="CASCADE"), nullable=False),
    Column("local_date", Date(), nullable=False),
    Column("status", Text(), nullable=False),
    Column("sealed_status", LargeBinary()),
    Column("timezone", Text()),  # zone "today" was computed in; NULL = provisional guess
    _timestamp("created_at"),
    _timestamp("updated_at"),
    PrimaryKeyConstraint("account_id", "local_date"),
    CheckConstraint(
        "status IN ('practiced', 'rest', 'moon', 'sick', 'travel', 'skipped')", name="status"
    ),
    CheckConstraint("(status = 'rest') = (sealed_status IS NOT NULL)", name="sealed_rest"),
    # key id (1) + nonce (24) + 1-byte payload + tag (16): every seal has the same length.
    CheckConstraint("octet_length(sealed_status) = 42", name="sealed_length"),
    CheckConstraint("local_date >= '2000-01-01'", name="local_date_min"),
)
