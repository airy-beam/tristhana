"""`AccountRepository` on Postgres. Each method is one statement (see the port)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Row, Text, case, func, insert, literal, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.application.ports.accounts import IdentityTaken
from tristhana.domain.accounts import Account, IdentityKey, NewAccount, ProfileUpdate
from tristhana.domain.locale import DEFAULT_LOCALE, LOCALES, Locale
from tristhana.infrastructure.db.engine import connection, sqlstate
from tristhana.infrastructure.db.tables import account, identity

_COLUMNS = (
    account.c.id,
    account.c.display_name,
    account.c.locale,
    account.c.timezone,
    account.c.last_seen_at,
    account.c.moon_location,
)


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
        changed = or_(
            account.c.display_name.is_distinct_from(changes.display_name),
            account.c.locale != changes.locale,
        )
        stmt = (
            update(account)
            .where(account.c.id == account_id)
            .values(
                display_name=changes.display_name,
                locale=changes.locale,
                last_seen_at=seen_at,
                updated_at=case((changed, func.now()), else_=account.c.updated_at),
            )
            .returning(*_COLUMNS)
        )
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
    )
