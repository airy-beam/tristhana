"""`AccountRepository` on Postgres. Each method is one statement (see the port)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Row, Text, case, delete, func, insert, literal, or_, select, update
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
from tristhana.domain.locale import DEFAULT_LOCALE, LOCALES, Locale
from tristhana.domain.rest_days import DayOff, Weekdays
from tristhana.infrastructure.db.engine import connection, sqlstate
from tristhana.infrastructure.db.tables import account, identity

_COLUMNS = (
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
            .returning(*_COLUMNS)
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
    )


ACCOUNT_COLUMNS = _COLUMNS
to_account = _account
