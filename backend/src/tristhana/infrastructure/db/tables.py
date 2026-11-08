"""Table definitions (SQLAlchemy Core, no ORM). Migrations must match: `alembic check`."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    PrimaryKeyConstraint,
    SmallInteger,
    Table,
    Text,
    Time,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY

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
    Column("moon_location", Text()),  # city slug (MD-03); NULL = the default (Mysuru)
    # Chosen in settings (ID-06): Telegram's name/language no longer overwrite them.
    Column("name_custom", Boolean(), nullable=False, server_default=text("false")),
    Column("locale_custom", Boolean(), nullable=False, server_default=text("false")),
    # The weekly day off (PR-09, ADR-0022): ISO-weekday bitmask (bit d-1); 0 = none, NULL =
    # never chosen. `day_off_before` was in effect before `day_off_since`.
    Column("day_off", SmallInteger()),
    Column("day_off_since", Date()),
    Column("day_off_before", SmallInteger()),
    Column("day_off_dismissed_at", DateTime(timezone=True)),  # "Not now" on the question
    # WH-01: leave the 🌸 button out of the status grids (bot and Mini App).
    Column("hide_ladies", Boolean(), nullable=False, server_default=text("false")),
    # PR-06: offer the one-tap check-in mood row after logging a practice.
    Column("offer_check_in", Boolean(), nullable=False, server_default=text("true")),
    # ST-09: the export rate-limit slot (one per 10 min), released when sending fails.
    Column("export_claimed_at", DateTime(timezone=True)),
    # MD-04 (ADR-0029): NULL = never chosen, '-' = not listed / not now, else a city slug.
    Column("home_city", Text()),
    _timestamp("created_at"),
    _timestamp("updated_at"),
    _timestamp("last_seen_at"),
    CheckConstraint("char_length(display_name) <= 64", name="display_name_length"),
    CheckConstraint("locale IN ('en', 'ru')", name="locale"),
    CheckConstraint("moon_location ~ '^[a-z-]{1,24}$'", name="moon_location"),
    CheckConstraint("day_off BETWEEN 0 AND 127", name="day_off"),
    CheckConstraint("day_off_before BETWEEN 0 AND 127", name="day_off_before"),
    CheckConstraint("day_off_before IS NULL OR day_off_since IS NOT NULL", name="day_off_period"),
    CheckConstraint("day_off_since IS NULL OR day_off IS NOT NULL", name="day_off_since_set"),
    CheckConstraint("home_city ~ '^[a-z-]{1,24}$'", name="home_city"),
    CheckConstraint(
        "home_city IS NULL OR home_city = '-' OR timezone IS NOT NULL", name="home_city_zone"
    ),
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

# WH-01 part 2 (ADR-0023): a 🌸 / sick / travel statement over [start_date, end_date]
# (inclusive). The kind is sealed on every row (one byte, as `day_log.sealed_status`), so a
# 🌸 period is indistinguishable from sick/travel. The 14-day cap keeps the overlap read a
# PK range (`start_date BETWEEN from - 13 AND to`); the 🌸 limit of 7 is a domain rule.
rest_period = Table(
    "rest_period",
    metadata,
    Column("account_id", Uuid(), ForeignKey(account.c.id, ondelete="CASCADE"), nullable=False),
    Column("start_date", Date(), nullable=False),
    Column("end_date", Date(), nullable=False, index=True),  # the tick's paused days (0011)
    Column("sealed_kind", LargeBinary(), nullable=False),
    _timestamp("created_at"),
    _timestamp("updated_at"),
    PrimaryKeyConstraint("account_id", "start_date"),
    CheckConstraint("end_date > start_date", name="period_order"),
    CheckConstraint("end_date - start_date <= 13", name="period_length"),
    CheckConstraint("octet_length(sealed_kind) = 42", name="sealed_length"),
    CheckConstraint("start_date >= '2000-01-01'", name="start_date_min"),
)

# PR-02/03/05. One practice per practiced day for now (slot 1). Lengths reference the catalog
# by natural key, validated in the domain (ADR-0017: no catalog tables, no FKs).
practice = Table(
    "practice",
    metadata,
    Column("account_id", Uuid(), nullable=False),
    Column("local_date", Date(), nullable=False),
    Column("slot", SmallInteger(), nullable=False, server_default=text("1")),
    Column("context", Text()),
    Column("online", Boolean(), nullable=False, server_default=text("false")),
    Column("series", ARRAY(Text())),  # NULL: length not given; '{}': short practice
    Column("end_item", Text()),
    Column("first_part", Text()),
    Column("duration_min", SmallInteger()),
    Column("start_time", Time()),  # wall clock in `timezone` (ADR-0005)
    Column("timezone", Text()),
    _timestamp("created_at"),
    _timestamp("updated_at"),
    PrimaryKeyConstraint("account_id", "local_date", "slot"),
    ForeignKeyConstraint(
        ["account_id", "local_date"],
        [day_log.c.account_id, day_log.c.local_date],
        ondelete="CASCADE",
        name="practice_day_log_fkey",
    ),
    CheckConstraint("slot = 1", name="slot"),
    CheckConstraint("context IN ('mysore', 'led', 'private', 'self')", name="context"),
    CheckConstraint("NOT (context = 'self' AND online)", name="self_offline"),
    CheckConstraint("first_part IN ('first_half', 'second_half')", name="first_part"),
    CheckConstraint(
        "(end_item IS NULL AND first_part IS NULL) OR coalesce(cardinality(series), 0) > 0",
        name="series_given",
    ),
    CheckConstraint("cardinality(series) <= 6", name="series_max"),
    CheckConstraint("duration_min BETWEEN 1 AND 600", name="duration"),
    CheckConstraint("start_time IS NULL OR timezone IS NOT NULL", name="start_time_zone"),
)

# PR-06 (ADR-0024): an after-practice check-in per practice slot, plain and owner-only.
# Like `practice`, it exists only on a practiced day (the day upsert deletes it otherwise).
# Tag keys are validated in the domain (no value CHECK), so the vocabulary can grow.
check_in = Table(
    "check_in",
    metadata,
    Column("account_id", Uuid(), nullable=False),
    Column("local_date", Date(), nullable=False),
    Column("slot", SmallInteger(), nullable=False, server_default=text("1")),
    Column("mood", SmallInteger()),
    Column("energy", SmallInteger()),
    Column("effort", SmallInteger()),
    Column("tags", ARRAY(Text()), nullable=False, server_default=text("'{}'")),
    _timestamp("created_at"),
    _timestamp("updated_at"),
    PrimaryKeyConstraint("account_id", "local_date", "slot"),
    ForeignKeyConstraint(
        ["account_id", "local_date"],
        [day_log.c.account_id, day_log.c.local_date],
        ondelete="CASCADE",
        name="check_in_day_log_fkey",
    ),
    CheckConstraint("slot = 1", name="slot"),
    CheckConstraint("mood BETWEEN 1 AND 5", name="mood"),
    CheckConstraint("energy BETWEEN 1 AND 5", name="energy"),
    CheckConstraint("effort BETWEEN 1 AND 5", name="effort"),
    CheckConstraint("cardinality(tags) <= 16", name="tags_max"),
)

# PR-07 (ADR-0025): one diary note per local day, sealed (ADR-0016). Tied to the account,
# not to `day_log`: no status here, so a 🌸 day's note looks like any other day's. The
# length CHECK: key id (1) + nonce (24) + tag (16) + 1..8000 bytes (2000 code points x 4).
diary_note = Table(
    "diary_note",
    metadata,
    Column("account_id", Uuid(), ForeignKey(account.c.id, ondelete="CASCADE"), nullable=False),
    Column("local_date", Date(), nullable=False),
    Column("sealed_text", LargeBinary(), nullable=False),
    _timestamp("created_at"),
    _timestamp("updated_at"),
    PrimaryKeyConstraint("account_id", "local_date"),
    CheckConstraint("octet_length(sealed_text) BETWEEN 42 AND 8041", name="sealed_length"),
    CheckConstraint("local_date >= '2000-01-01'", name="local_date_min"),
)

# PR-08 (ADR-0026): where the practice ends now (series + last given stop; earlier series
# are full; NULL/NULL = standing only) and the milestone items given. Plain and owner-only.
# Keys are natural keys without FKs (ADR-0017). `last_event_id` is the compare-and-set
# guard; the "Not new" answer (`hint_*`) counts only while `hint_event_id = last_event_id`.
progression = Table(
    "progression",
    metadata,
    Column("account_id", Uuid(), ForeignKey(account.c.id, ondelete="CASCADE"), primary_key=True),
    Column("series", Text()),
    Column("last_key", Text()),
    Column("items", ARRAY(Text()), nullable=False, server_default=text("'{}'")),
    Column("last_event_id", BigInteger()),
    Column("hint_series", Text()),
    Column("hint_key", Text()),
    Column("hint_event_id", BigInteger()),
    _timestamp("updated_at"),
    CheckConstraint("(series IS NULL) = (last_key IS NULL)", name="position"),
    CheckConstraint("cardinality(items) <= 8", name="items_max"),
    CheckConstraint(
        "(hint_series IS NULL) = (hint_key IS NULL)"
        " AND (hint_series IS NULL) = (hint_event_id IS NULL)",
        name="hint_set",
    ),
)

# PR-08: the append-only history (undo deletes the latest). `marked_by` = who marked it
# (the student now; a linked teacher in Phase 3). `occurred_on` is a local date.
progression_event = Table(
    "progression_event",
    metadata,
    Column("id", BigInteger(), Identity(always=False), primary_key=True),
    Column("account_id", Uuid(), ForeignKey(account.c.id, ondelete="CASCADE"), nullable=False),
    Column("kind", Text(), nullable=False),
    Column("from_series", Text()),
    Column("from_key", Text()),
    Column("to_series", Text()),
    Column("to_key", Text()),
    Column("item", Text()),
    Column("occurred_on", Date(), nullable=False),
    Column("marked_by", Uuid(), ForeignKey(account.c.id, ondelete="SET NULL")),
    _timestamp("created_at"),
    CheckConstraint(
        "kind IN ('start', 'given', 'changed', 'item_given', 'item_removed')", name="kind"
    ),
    CheckConstraint(
        "CASE WHEN kind IN ('item_given', 'item_removed')"
        " THEN item IS NOT NULL AND from_key IS NULL AND to_key IS NULL"
        " AND from_series IS NULL AND to_series IS NULL"
        " ELSE item IS NULL END",
        name="item_kind",
    ),
    CheckConstraint("(from_series IS NULL) = (from_key IS NULL)", name="from_position"),
    CheckConstraint("(to_series IS NULL) = (to_key IS NULL)", name="to_position"),
    CheckConstraint("occurred_on >= '2000-01-01'", name="occurred_on_min"),
    Index("progression_event_account_id_idx", "account_id", "id"),
)

# GM-01 part 2 (ADR-0028): the practice-count thresholds a person has passed, each recorded
# once ever inside the day write. `celebrated` = it was shown (False: seeded silently).
practice_milestone = Table(
    "practice_milestone",
    metadata,
    Column("account_id", Uuid(), ForeignKey(account.c.id, ondelete="CASCADE"), nullable=False),
    Column("threshold", Integer(), nullable=False),
    Column("celebrated", Boolean(), nullable=False),
    _timestamp("reached_at"),
    PrimaryKeyConstraint("account_id", "threshold"),
    CheckConstraint("threshold BETWEEN 1 AND 100000", name="threshold"),
)

# MD-03 / ADR-0019: stored moon calendars per city (previous year … current + 2).
moon_calendar = Table(
    "moon_calendar",
    metadata,
    Column("location", Text(), nullable=False),
    Column("year", SmallInteger(), nullable=False),
    Column("algo_version", Text(), nullable=False),
    _timestamp("computed_at"),
    PrimaryKeyConstraint("location", "year"),
)

moon_day = Table(
    "moon_day",
    metadata,
    Column("location", Text(), nullable=False),
    Column("date", Date(), nullable=False),
    Column("kind", Text(), nullable=False),
    PrimaryKeyConstraint("location", "date"),
    CheckConstraint(
        "kind IN ('purnima', 'amavasya', 'kshaya_purnima', 'kshaya_amavasya')", name="kind"
    ),
)

# MD-03 / ADR-0018. A missing row or NULL column means the domain default.
notification_settings = Table(
    "notification_settings",
    metadata,
    Column("account_id", Uuid(), ForeignKey(account.c.id, ondelete="CASCADE"), primary_key=True),
    Column("moon_offsets", ARRAY(SmallInteger())),
    Column("moon_at", Time()),
    Column("quiet_start", Time()),
    Column("quiet_end", Time()),
    Column("daily_cap", SmallInteger()),
    Column("practice_on", Boolean()),  # NULL = never chosen (the one-time offer may show)
    Column("practice_at", Time()),
    Column("unreachable_at", DateTime(timezone=True)),
    Column("moon_intro_sent_at", DateTime(timezone=True)),  # Q24: the intro went out once
    _timestamp("updated_at"),
    CheckConstraint("moon_offsets <@ '{1,3,7}'::smallint[]", name="moon_offsets"),
    CheckConstraint("daily_cap BETWEEN 1 AND 10", name="daily_cap"),
    CheckConstraint("(quiet_start IS NULL) = (quiet_end IS NULL)", name="quiet_pair"),
)

notification_delivery = Table(
    "notification_delivery",
    metadata,
    Column("account_id", Uuid(), ForeignKey(account.c.id, ondelete="CASCADE"), nullable=False),
    Column("dedupe_key", Text(), nullable=False),
    Column("category", Text(), nullable=False),
    Column("local_date", Date(), nullable=False),
    Column("status", Text(), nullable=False),
    Column("attempts", SmallInteger(), nullable=False, server_default=text("1")),
    _timestamp("created_at"),
    _timestamp("updated_at"),
    PrimaryKeyConstraint("account_id", "dedupe_key"),
    CheckConstraint("category IN ('moon', 'practice')", name="category"),
    CheckConstraint("status IN ('claimed', 'sent', 'failed', 'blocked')", name="status"),
)


# ID-04, ADR-0030. `is_primary` = an explicit choice only (the default is read-time);
# `linked_on` = the student's local date at confirm, the boundary of "from today on".
teacher_link = Table(
    "teacher_link",
    metadata,
    Column("student_id", Uuid(), ForeignKey(account.c.id, ondelete="CASCADE"), nullable=False),
    Column("teacher_id", Uuid(), ForeignKey(account.c.id, ondelete="CASCADE"), nullable=False),
    Column("is_primary", Boolean(), nullable=False, server_default=text("false")),
    Column("linked_on", Date(), nullable=False),
    _timestamp("created_at"),
    Column("quiet_note_agreed", Boolean(), nullable=False, server_default=text("false")),
    PrimaryKeyConstraint("student_id", "teacher_id"),
    CheckConstraint("student_id <> teacher_id", name="not_self"),
    Index("teacher_link_teacher_id_student_id_idx", "teacher_id", "student_id"),
    Index(
        "teacher_link_one_primary", "student_id", unique=True, postgresql_where=text("is_primary")
    ),
)

# One reusable code per teacher, stored plain: it must be re-shown and exposes only a name.
teacher_invite = Table(
    "teacher_invite",
    metadata,
    Column("account_id", Uuid(), ForeignKey(account.c.id, ondelete="CASCADE"), primary_key=True),
    Column("code", Text(), nullable=False, unique=True),
    _timestamp("created_at"),
    CheckConstraint("code ~ '^[A-Za-z0-9]{16}$'", name="code"),
)

# SC-01 (ADR-0033). Cities are slugs from `cities.yaml`, no FK (as ADR-0019); no sentinels.
# The owner is `owner_id` and always has a staff row; staff and student are exclusive per shala.
_ROLES = "'{admin,teacher,assistant,office}'::text[]"
shala = Table(
    "shala",
    metadata,
    Column("id", Uuid(), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("name", Text(), nullable=False),
    Column("city", Text(), nullable=False),
    Column("moon_city", Text()),  # NULL = same as the city
    Column("online", Boolean(), nullable=False, server_default=text("false")),
    Column("owner_id", Uuid(), ForeignKey(account.c.id, ondelete="CASCADE"), nullable=False),
    Column("join_code", Text(), nullable=False, unique=True),
    _timestamp("created_at"),
    _timestamp("updated_at"),
    CheckConstraint("char_length(name) BETWEEN 1 AND 64", name="name"),
    CheckConstraint("city ~ '^[a-z][a-z-]{0,23}$'", name="city"),
    CheckConstraint("moon_city ~ '^[a-z][a-z-]{0,23}$'", name="moon_city"),
    CheckConstraint("join_code ~ '^[A-Za-z0-9]{16}$'", name="join_code"),
    Index("shala_owner_id_idx", "owner_id"),
    # SC-02: ISO weekday bitmask as `account.day_off` (NULL = not set); the moon policy (Q117).
    Column("days_off", SmallInteger()),
    Column("moon_policy", Text(), nullable=False, server_default=text("'closed'")),
    CheckConstraint("days_off BETWEEN 0 AND 127", name="days_off"),
    CheckConstraint("moon_policy IN ('closed', 'pranayama', 'open')", name="moon_policy"),
)

shala_staff = Table(
    "shala_staff",
    metadata,
    Column("shala_id", Uuid(), ForeignKey(shala.c.id, ondelete="CASCADE"), nullable=False),
    Column("account_id", Uuid(), ForeignKey(account.c.id, ondelete="CASCADE"), nullable=False),
    Column("roles", ARRAY(Text()), nullable=False, server_default=text("'{}'")),
    Column("joined_on", Date(), nullable=False),  # the member's local date at confirm
    _timestamp("created_at"),
    PrimaryKeyConstraint("shala_id", "account_id"),
    CheckConstraint(f"roles <@ {_ROLES}", name="roles"),
    Index("shala_staff_account_id_created_at_idx", "account_id", "created_at"),
)

shala_student = Table(
    "shala_student",
    metadata,
    Column("shala_id", Uuid(), ForeignKey(shala.c.id, ondelete="CASCADE"), nullable=False),
    Column("account_id", Uuid(), ForeignKey(account.c.id, ondelete="CASCADE"), nullable=False),
    Column("joined_on", Date(), nullable=False),
    _timestamp("created_at"),
    PrimaryKeyConstraint("shala_id", "account_id"),
    Index("shala_student_account_id_created_at_idx", "account_id", "created_at"),
)

# Single use, 7 days, one role (Q100); deleted when used, expired ones by the tick's pruning.
shala_staff_invite = Table(
    "shala_staff_invite",
    metadata,
    Column("code", Text(), primary_key=True),
    Column("shala_id", Uuid(), ForeignKey(shala.c.id, ondelete="CASCADE"), nullable=False),
    Column("role", Text(), nullable=False),
    Column("created_by", Uuid(), ForeignKey(account.c.id, ondelete="CASCADE"), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("code ~ '^[A-Za-z0-9]{16}$'", name="code"),
    CheckConstraint(f"role = ANY ({_ROLES})", name="role"),
    Index("shala_staff_invite_shala_id_idx", "shala_id"),
)

# SC-02 (ADR-0034): a weekly rule as columns, expanded at read time. The teacher is a staff row
# of the same shala; removing them (or deleting their account) leaves the class untaught:
# `ON DELETE SET NULL (teacher_id)` (Postgres >= 15) keeps `shala_id`. No account FK.
_CLASS_TYPES = "'mysore', 'led', 'private', 'conference', 'pranayama', 'chanting', 'workshop'"


def _teacher_fk(table: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["shala_id", "teacher_id"],
        [shala_staff.c.shala_id, shala_staff.c.account_id],
        name=f"{table}_teacher_id_fkey",
        ondelete="SET NULL (teacher_id)",
    )


shala_class = Table(
    "shala_class",
    metadata,
    Column("id", Uuid(), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("shala_id", Uuid(), ForeignKey(shala.c.id, ondelete="CASCADE"), nullable=False),
    Column("type", Text(), nullable=False),
    Column("title", Text()),
    Column("online", Boolean(), nullable=False, server_default=text("false")),
    Column("city", Text()),  # NULL = the shala's; only an online class names one (Q124)
    Column("teacher_id", Uuid()),
    Column("start_time", Time(), nullable=False),  # wall clock in the class zone
    Column("minutes", SmallInteger(), nullable=False),
    Column("weekdays", SmallInteger(), nullable=False),  # ISO bitmask; 0 = one date
    Column("every", SmallInteger(), nullable=False, server_default=text("1")),  # weeks
    Column("starts_on", Date(), nullable=False),
    Column("ends_on", Date()),
    _timestamp("created_at"),
    _timestamp("updated_at"),
    _teacher_fk("shala_class"),
    CheckConstraint(f"type IN ({_CLASS_TYPES})", name="type"),
    CheckConstraint("char_length(title) BETWEEN 1 AND 48", name="title"),
    CheckConstraint("city IS NULL OR (city ~ '^[a-z][a-z-]{0,23}$' AND online)", name="city"),
    CheckConstraint(
        "minutes BETWEEN 15 AND 480 AND extract(epoch FROM start_time) / 60 + minutes <= 1440",
        name="minutes",
    ),
    CheckConstraint("weekdays BETWEEN 0 AND 127", name="weekdays"),
    CheckConstraint("every BETWEEN 1 AND 4", name="every"),
    CheckConstraint("ends_on IS NULL OR (ends_on >= starts_on AND weekdays > 0)", name="ends_on"),
    Index("shala_class_shala_id_starts_on_idx", "shala_id", "starts_on"),
)

# One row per (class, rule date): cancelled, held anyway (Q126), or changed (move, time,
# length, substitute). `shala_id` is denormalised for the window read and the teacher FK.
shala_class_override = Table(
    "shala_class_override",
    metadata,
    Column("class_id", Uuid(), ForeignKey(shala_class.c.id, ondelete="CASCADE"), nullable=False),
    Column("on_date", Date(), nullable=False),
    Column("shala_id", Uuid(), nullable=False),
    Column("status", Text()),
    Column("moved_to", Date()),
    Column("start_time", Time()),
    Column("minutes", SmallInteger()),
    Column("teacher_id", Uuid()),
    _timestamp("updated_at"),
    PrimaryKeyConstraint("class_id", "on_date"),
    _teacher_fk("shala_class_override"),
    CheckConstraint("status IN ('cancelled', 'held')", name="status"),
    CheckConstraint("abs(moved_to - on_date) <= 6", name="moved_to"),
    CheckConstraint(
        "minutes BETWEEN 15 AND 480 AND (start_time IS NULL OR "
        "extract(epoch FROM start_time) / 60 + minutes <= 1440)",
        name="minutes",
    ),
    CheckConstraint(
        "status IS DISTINCT FROM 'cancelled' OR (moved_to IS NULL AND start_time IS NULL "
        "AND minutes IS NULL AND teacher_id IS NULL)",
        name="cancelled",
    ),
    Index("shala_class_override_shala_id_on_date_idx", "shala_id", "on_date"),
)

shala_closure = Table(
    "shala_closure",
    metadata,
    Column("id", Uuid(), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("shala_id", Uuid(), ForeignKey(shala.c.id, ondelete="CASCADE"), nullable=False),
    Column("start_date", Date(), nullable=False),
    Column("end_date", Date(), nullable=False),  # inclusive
    CheckConstraint("end_date >= start_date AND end_date - start_date <= 91", name="dates"),
    Index("shala_closure_shala_id_end_date_idx", "shala_id", "end_date"),
)

# Q125: A's auto-cancelled classes are held on B.
shala_swap = Table(
    "shala_swap",
    metadata,
    Column("shala_id", Uuid(), ForeignKey(shala.c.id, ondelete="CASCADE"), nullable=False),
    Column("from_date", Date(), nullable=False),
    Column("to_date", Date(), nullable=False),
    PrimaryKeyConstraint("shala_id", "from_date"),
    UniqueConstraint("shala_id", "to_date", name="shala_swap_shala_id_to_date_key"),
    CheckConstraint("from_date <> to_date AND abs(to_date - from_date) <= 6", name="dates"),
)
