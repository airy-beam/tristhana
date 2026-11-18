"""`AccountRepository` on Postgres. Each method is one statement (see the port)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Date,
    Row,
    Select,
    Text,
    case,
    delete,
    exists,
    false,
    func,
    insert,
    literal,
    null,
    or_,
    select,
    true,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, aggregate_order_by
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.application.ports.accounts import IdentityTaken
from tristhana.domain.accounts import (
    Account,
    IdentityKey,
    NewAccount,
    ProfileChange,
    ProfileUpdate,
)
from tristhana.domain.journey import JourneyFacts, OwnedShala
from tristhana.domain.locale import DEFAULT_LOCALE, LOCALES, Locale
from tristhana.domain.moon import ShalaMoon, TeacherMoon
from tristhana.domain.rest_days import DayOff, Weekdays
from tristhana.infrastructure.db.engine import connection, sqlstate
from tristhana.infrastructure.db.tables import (
    account,
    day_log,
    identity,
    notification_settings,
    progression,
    shala,
    shala_class,
    shala_staff,
    shala_student,
    teacher_invite,
    teacher_link,
)

_TEACHER = account.alias("main_teacher")
_MAIN = teacher_link.alias("main_link")
# MD-02 inputs, in the same statement as the account (ADR-0032), so every RETURNING and SELECT
# of `_COLUMNS` carries them: `teaches` by the (teacher_id, student_id) index, the main teacher
# (ID-04 `effective_primary`) by the student_id PK prefix, ≤ 20 rows.
_TEACHES = (
    exists()
    .where(teacher_link.c.teacher_id == account.c.id)
    .correlate_except(teacher_link)
    .label("teaches")
)


def _main_teacher_of(*columns: Any) -> Any:
    """The main teacher's columns, ID-04 `effective_primary` order."""
    return (
        select(*columns)
        .select_from(_MAIN.join(_TEACHER, _TEACHER.c.id == _MAIN.c.teacher_id))
        .where(_MAIN.c.student_id == account.c.id)
        .order_by(_MAIN.c.is_primary.desc(), _MAIN.c.created_at, _MAIN.c.teacher_id)
        .limit(1)
        .correlate_except(_MAIN, _TEACHER)
        .scalar_subquery()
    )


_MAIN_TEACHER = (
    _main_teacher_of(
        func.jsonb_build_object(
            "id", _TEACHER.c.id, "name", _TEACHER.c.display_name, "moon", _TEACHER.c.moon_location
        )
    )
    .cast(JSONB)
    .label("main_teacher")
)
MAIN_TEACHER = _MAIN_TEACHER  # correlated to `account`: whoever that row is in the statement
# The tick needs only the teacher's stored value (it never names them).
MAIN_TEACHER_LOCATION = _main_teacher_of(_TEACHER.c.moon_location).label("teacher_location")
TEACHES = _TEACHES

# SC-01 (ADR-0033, Q108): the main shala, same statement. Staff memberships first, then student
# ones where the main teacher is staff, then the oldest: two index reads (≤ 10 + 5 rows).
_STAFF_AT = shala_staff.alias("staff_at")
_TEACHER_AT = shala_staff.alias("teacher_at")
_STUDENT_OF = shala_student.alias("student_of")
_SHALA = shala.alias("main_shala")
_OWNED = shala.alias("owned_by")


def _shala_json(staff: Any, teacher_on_staff: Any, owner: Any, roles: Any, owns_any: Any) -> Any:
    return func.jsonb_build_object(
        "id",
        _SHALA.c.id,
        "name",
        _SHALA.c.name,
        "moon",
        func.coalesce(_SHALA.c.moon_city, _SHALA.c.city),
        "city",
        _SHALA.c.city,
        "staff",
        staff,
        "teacher_on_staff",
        teacher_on_staff,
        "owner",
        owner,
        "roles",
        roles,
        "owns",
        owns_any,
    )


# Q373: the seat at the main shala, and whether the person owns any shala (one probe of
# `shala_owner_id_idx`, on the staff branch only: an owner is always on their shala's staff).
# Correlated to the outer `account` explicitly: two levels down, auto-correlation would let
# the EXISTS read `account` as a FROM of its own (any owner of any shala).
_OWNS_ANY = exists().where(_OWNED.c.owner_id == account.c.id).correlate(account)


_AS_STAFF = (
    select(
        _shala_json(
            true(), false(), _SHALA.c.owner_id == account.c.id, _STAFF_AT.c.roles, _OWNS_ANY
        )
    )
    .select_from(_STAFF_AT.join(_SHALA, _SHALA.c.id == _STAFF_AT.c.shala_id))
    .where(_STAFF_AT.c.account_id == account.c.id)
    .order_by(_STAFF_AT.c.created_at, _SHALA.c.id)
    .limit(1)
    .correlate_except(_STAFF_AT, _SHALA)
    .scalar_subquery()
)
_TEACHER_ON_STAFF = exists().where(
    _TEACHER_AT.c.shala_id == _STUDENT_OF.c.shala_id,
    _TEACHER_AT.c.account_id == _main_teacher_of(_TEACHER.c.id),
)
_AS_STUDENT = (
    select(_shala_json(false(), _TEACHER_ON_STAFF, false(), null(), false()))
    .select_from(_STUDENT_OF.join(_SHALA, _SHALA.c.id == _STUDENT_OF.c.shala_id))
    .where(_STUDENT_OF.c.account_id == account.c.id)
    .order_by(_TEACHER_ON_STAFF.desc(), _STUDENT_OF.c.created_at, _SHALA.c.id)
    .limit(1)
    .correlate_except(_STUDENT_OF, _SHALA, _TEACHER_AT)
    .scalar_subquery()
)
MAIN_SHALA = func.coalesce(_AS_STAFF, _AS_STUDENT).cast(JSONB).label("main_shala")

_STORED = (
    account.c.id,
    account.c.display_name,
    account.c.locale,
    account.c.timezone,
    account.c.last_seen_at,
    account.c.moon_location,
    account.c.name_custom,
    account.c.locale_custom,
    account.c.created_at,
    account.c.day_off,
    account.c.day_off_since,
    account.c.day_off_before,
    account.c.day_off_dismissed_at,
    account.c.hide_ladies,
    account.c.offer_check_in,
    account.c.home_city,
    account.c.welcomed_at,
)
_COLUMNS = (*_STORED, _TEACHES, _MAIN_TEACHER, MAIN_SHALA)
# The same row shape for an INSERT's RETURNING. The subqueries above cannot be used there:
# an INSERT gives them no `account` to correlate to, so they would read every account's
# links and hand a new account somebody else's teacher and shala. A new account has none.
_NEW_COLUMNS = (
    *_STORED,
    false().label("teaches"),
    null().cast(JSONB).label("main_teacher"),
    null().cast(JSONB).label("main_shala"),
)


def journey_statement(account_id: UUID) -> Select[*tuple[Any, ...]]:
    """UI-06 stage 2: one row of scalar subqueries, each keyed by `account_id` alone (PK or
    index prefix), so no row of another account is read. Plain columns only. The owned
    shalas are the `shala_owner_id_idx` rows (at most `MAX_OWNED`), each with two counts by
    index prefix: `shala_class (shala_id, starts_on)` and the `shala_student` PK."""
    has_days = exists().where(day_log.c.account_id == account_id)
    # "Yes" and "no" both answer it; other settings create the row with the choice NULL.
    reminder_answered = exists().where(
        notification_settings.c.account_id == account_id,
        notification_settings.c.practice_on.is_not(None),
    )
    # As `to_progression`: a stored position has its event ("standing only" included).
    position_set = exists().where(
        progression.c.account_id == account_id, progression.c.last_event_id.is_not(None)
    )
    # A UTC date whatever the connection's zone: the link's age is counted in whole days.
    invite_made_on = (
        select(func.timezone("UTC", teacher_invite.c.created_at).cast(Date))
        .where(teacher_invite.c.account_id == account_id)
        .scalar_subquery()
    )
    classes = (
        select(func.count())
        .select_from(shala_class)
        .where(shala_class.c.shala_id == shala.c.id)
        .scalar_subquery()
    )
    students = (
        select(func.count())
        .select_from(shala_student)
        .where(shala_student.c.shala_id == shala.c.id)
        .scalar_subquery()
    )
    one = func.jsonb_build_object("id", shala.c.id, "classes", classes, "students", students)
    owned = (
        select(func.jsonb_agg(aggregate_order_by(one, shala.c.created_at, shala.c.id)))
        .where(shala.c.owner_id == account_id)
        .scalar_subquery()
    )
    return select(
        has_days.label("has_days"),
        reminder_answered.label("reminder_answered"),
        position_set.label("position_set"),
        invite_made_on.label("invite_made_on"),
        owned.cast(JSONB).label("owned"),
    )


def to_mask(days: Weekdays | None) -> int | None:
    """ISO weekdays as a bitmask (bit d-1); None stays None (never chosen)."""
    return None if days is None else sum(1 << (d - 1) for d in days)


def from_mask(mask: int | None) -> Weekdays | None:
    return None if mask is None else frozenset(d for d in range(1, 8) if mask & (1 << (d - 1)))


class SqlAccountRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def find_by_identity(self, key: IdentityKey) -> Account | None:
        stmt = (
            select(*_COLUMNS)
            .select_from(identity.join(account))
            .where(
                identity.c.provider == key.provider.value,
                identity.c.provider_user_id == key.provider_user_id,
            )
        )
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).one_or_none()
        return _account(row) if row else None

    async def create_with_identity(self, key: IdentityKey, new: NewAccount) -> Account:
        # Both rows in one statement: a unique violation on the identity rolls back the
        # account too, so a lost race leaves no orphan.
        created = (
            insert(account)
            .values(display_name=new.display_name, locale=new.locale)
            .returning(*_NEW_COLUMNS)
            .cte("created")
        )
        linked = (
            insert(identity)
            .from_select(
                ["provider", "provider_user_id", "account_id"],
                select(
                    literal(key.provider.value, Text),
                    literal(key.provider_user_id, Text),
                    created.c.id,
                ),
            )
            .cte("linked")
        )
        stmt = select(*created.c).add_cte(linked)
        try:
            async with connection(self._engine) as conn:
                row = (await conn.execute(stmt)).one()
        except IntegrityError as e:
            if sqlstate(e) == "23505":  # unique_violation: the identity exists
                raise IdentityTaken from e
            raise
        return _account(row)

    async def update_profile(
        self, account_id: UUID, changes: ProfileUpdate, seen_at: datetime
    ) -> Account:
        # A choice made in settings wins over a refresh racing it (ADR-0021).
        name = case(
            (account.c.name_custom, account.c.display_name),
            else_=literal(changes.display_name, Text),
        )
        locale = case(
            (account.c.locale_custom, account.c.locale), else_=literal(changes.locale, Text)
        )
        changed = or_(
            account.c.display_name.is_distinct_from(name),
            account.c.locale != locale,
        )
        stmt = (
            update(account)
            .where(account.c.id == account_id)
            .values(
                display_name=name,
                locale=locale,
                last_seen_at=seen_at,
                updated_at=case((changed, func.now()), else_=account.c.updated_at),
            )
            .returning(*_COLUMNS)
        )
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).one()
        return _account(row)

    async def update_settings(self, account_id: UUID, change: ProfileChange) -> Account:
        values: dict[str, object] = {"updated_at": func.now()}
        if "name" in change.fields:
            values |= {"display_name": change.display_name, "name_custom": change.name_custom}
        if "locale" in change.fields:
            values |= {"locale": change.locale, "locale_custom": change.locale_custom}
        if "timezone" in change.fields:
            values["timezone"] = change.timezone
        if "hide_ladies" in change.fields:
            values["hide_ladies"] = change.hide_ladies
        if "offer_check_in" in change.fields:
            values["offer_check_in"] = change.offer_check_in
        if "home_city" in change.fields:
            values["home_city"] = change.home_city
        stmt = update(account).where(account.c.id == account_id).values(values).returning(*_COLUMNS)
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).one()
        return _account(row)

    async def set_moon_location(self, account_id: UUID, slug: str | None) -> Account:
        stmt = (
            update(account)
            .where(account.c.id == account_id)
            .values(moon_location=slug, updated_at=func.now())
            .returning(*_COLUMNS)
        )
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).one()
        return _account(row)

    async def set_moon_location_if_unset(self, account_id: UUID, slug: str) -> Account | None:
        stmt = (
            update(account)
            .where(account.c.id == account_id, account.c.moon_location.is_(None))
            .values(moon_location=slug, updated_at=func.now())
            .returning(*_COLUMNS)
        )
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).one_or_none()
        return _account(row) if row else None

    async def set_day_off(self, account_id: UUID, day_off: DayOff) -> Account:
        stmt = (
            update(account)
            .where(account.c.id == account_id)
            .values(
                day_off=to_mask(day_off.days),
                day_off_since=day_off.since,
                day_off_before=to_mask(day_off.before),
                updated_at=func.now(),
            )
            .returning(*_COLUMNS)
        )
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).one()
        return _account(row)

    async def dismiss_day_off_question(self, account_id: UUID) -> None:
        stmt = (
            update(account)
            .where(account.c.id == account_id, account.c.day_off_dismissed_at.is_(None))
            .values(day_off_dismissed_at=func.now())
        )
        async with connection(self._engine) as conn:
            await conn.execute(stmt)

    async def mark_welcomed(self, account_id: UUID, at: datetime) -> bool | None:
        # Two `/start`s at once: the second waits for the row, re-checks the WHERE and
        # matches nothing, so the instant is set once and only one caller gets a row.
        has_days = exists().where(day_log.c.account_id == account.c.id).correlate_except(day_log)
        stmt = (
            update(account)
            .where(account.c.id == account_id, account.c.welcomed_at.is_(None))
            .values(welcomed_at=at)
            .returning(has_days.label("has_days"))
        )
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).one_or_none()
        return None if row is None else bool(row.has_days)

    async def journey_facts(self, account_id: UUID) -> JourneyFacts:
        async with connection(self._engine) as conn:
            row = (await conn.execute(journey_statement(account_id))).one()
        return JourneyFacts(
            has_days=row.has_days,
            reminder_answered=row.reminder_answered,
            position_set=row.position_set,
            invite_made_on=row.invite_made_on,
            owned=tuple(
                OwnedShala(UUID(s["id"]), s["classes"], s["students"]) for s in row.owned or ()
            ),
        )

    async def delete(self, account_id: UUID) -> bool:
        """ST-09: every per-account FK cascades; others' `progression_event.marked_by` → NULL."""
        stmt = delete(account).where(account.c.id == account_id).returning(literal(1))
        async with connection(self._engine) as conn:
            return (await conn.execute(stmt)).one_or_none() is not None

    async def set_timezone_if_unset(self, account_id: UUID, timezone: str) -> Account:
        stmt = (
            update(account)
            .where(account.c.id == account_id, account.c.timezone.is_(None))
            .values(timezone=timezone, updated_at=func.now())
            .returning(*_COLUMNS)
        )
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).one_or_none()
            if row is None:  # already set (e.g. by a concurrent request): keep it
                row = (
                    await conn.execute(select(*_COLUMNS).where(account.c.id == account_id))
                ).one()
        return _account(row)


def _account(row: Row[*tuple[Any, ...]]) -> Account:
    locale: Locale = row.locale if row.locale in LOCALES else DEFAULT_LOCALE
    return Account(
        id=row.id,
        display_name=row.display_name,
        locale=locale,
        timezone=row.timezone,
        last_seen_at=row.last_seen_at,
        moon_location=row.moon_location,
        name_custom=row.name_custom,
        locale_custom=row.locale_custom,
        created_at=row.created_at,
        day_off=DayOff(from_mask(row.day_off), row.day_off_since, from_mask(row.day_off_before)),
        day_off_dismissed=row.day_off_dismissed_at is not None,
        hide_ladies=row.hide_ladies,
        offer_check_in=row.offer_check_in,
        home_city=row.home_city,
        teaches=row.teaches,
        main_teacher=to_teacher(row.main_teacher),
        shala=to_shala(row.main_shala),
        welcomed=row.welcomed_at is not None,
    )


def to_shala(found: dict[str, Any] | None) -> ShalaMoon | None:
    if found is None:
        return None
    return ShalaMoon(
        UUID(found["id"]),
        found["name"],
        found["moon"],
        found["staff"],
        found["teacher_on_staff"],
        found.get("city"),
        owner=bool(found.get("owner")),
        roles=frozenset(found.get("roles") or ()),
        owns_any=bool(found.get("owns")),
    )


def to_teacher(found: dict[str, Any] | None) -> TeacherMoon | None:
    return None if found is None else TeacherMoon(UUID(found["id"]), found["name"], found["moon"])


ACCOUNT_COLUMNS = _COLUMNS
to_account = _account
