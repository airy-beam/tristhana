import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, make_url, select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.fakes import FixedClock
from tristhana.application.accounts import EnsureAccount
from tristhana.application.ports.accounts import IdentityTaken
from tristhana.application.ports.storage import StorageUnavailable
from tristhana.domain.accounts import (
    ExternalProfile,
    IdentityKey,
    IdentityProvider,
    NewAccount,
    ProfileUpdate,
)
from tristhana.infrastructure.db import migrate
from tristhana.infrastructure.db.accounts import SqlAccountRepository
from tristhana.infrastructure.db.engine import asyncpg_url, build_engine, connection
from tristhana.infrastructure.db.storage import PostgresStorage
from tristhana.infrastructure.db.tables import account, identity

pytestmark = pytest.mark.db

KEY = IdentityKey(IdentityProvider.TELEGRAM, "42")


async def _count(engine: AsyncEngine) -> tuple[int, int]:
    async with engine.connect() as conn:
        accounts = (await conn.execute(select(func.count()).select_from(account))).scalar_one()
        identities = (await conn.execute(select(func.count()).select_from(identity))).scalar_one()
    return accounts, identities


async def test_create_then_find(engine: AsyncEngine) -> None:
    repo = SqlAccountRepository(engine)

    created = await repo.create_with_identity(KEY, NewAccount(display_name="Аня", locale="ru"))
    found = await repo.find_by_identity(KEY)

    assert found == created
    assert (created.display_name, created.locale, created.timezone) == ("Аня", "ru", None)
    assert created.last_seen_at.tzinfo is not None
    assert await repo.find_by_identity(IdentityKey(IdentityProvider.TELEGRAM, "43")) is None


async def test_duplicate_identity_leaves_no_orphan(engine: AsyncEngine) -> None:
    repo = SqlAccountRepository(engine)
    await repo.create_with_identity(KEY, NewAccount(display_name="A", locale="en"))

    with pytest.raises(IdentityTaken):
        await repo.create_with_identity(KEY, NewAccount(display_name="B", locale="en"))

    assert await _count(engine) == (1, 1)


async def test_concurrent_first_contacts_make_one_account(engine: AsyncEngine) -> None:
    ensure = EnsureAccount(SqlAccountRepository(engine), FixedClock())
    profile = ExternalProfile(KEY, display_name="Ash", language_code="en")

    results = await asyncio.gather(*(ensure.execute(profile) for _ in range(5)))

    assert len({a.id for a in results}) == 1
    assert await _count(engine) == (1, 1)


async def test_update_profile_and_last_seen(engine: AsyncEngine) -> None:
    repo = SqlAccountRepository(engine)
    created = await repo.create_with_identity(KEY, NewAccount(display_name="Ash", locale="en"))
    seen = datetime(2030, 1, 1, tzinfo=UTC)

    updated = await repo.update_profile(
        created.id, ProfileUpdate(display_name="Ashley", locale="ru"), seen
    )

    assert (updated.display_name, updated.locale, updated.last_seen_at) == ("Ashley", "ru", seen)


async def test_timezone_is_set_only_once(engine: AsyncEngine) -> None:
    repo = SqlAccountRepository(engine)
    created = await repo.create_with_identity(KEY, NewAccount(display_name=None, locale="en"))

    first = await repo.set_timezone_if_unset(created.id, "Asia/Almaty")
    second = await repo.set_timezone_if_unset(created.id, "Europe/Moscow")

    assert first.timezone == second.timezone == "Asia/Almaty"


async def test_unreachable_database_is_storage_unavailable() -> None:
    storage = PostgresStorage(
        "postgresql://nobody:x@127.0.0.1:9/none", ca_file=None, pool_size=1, max_overflow=0
    )
    await storage.start()  # logs a warning, never raises
    try:
        with pytest.raises(StorageUnavailable):
            await storage.accounts.find_by_identity(KEY)
        with pytest.raises(StorageUnavailable):
            await storage.ping()
    finally:
        await storage.stop()


def test_migrations_match_tables_and_round_trip(migrated_url: str) -> None:
    migrate.check(migrated_url)
    migrate.downgrade(migrated_url, "base")
    migrate.upgrade(migrated_url)
    migrate.check(migrated_url)


async def test_app_role_has_dml_but_no_ddl(migrated_url: str, engine: AsyncEngine) -> None:
    # The same role infra/supabase/roles.sql creates; migration 0001 grants it DML only.
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tristhana_app')"
                " THEN CREATE ROLE tristhana_app LOGIN PASSWORD 'test'; END IF; END $$"
            )
        )
    # Alembic runs its own event loop, so off this one.
    await asyncio.to_thread(migrate.downgrade, migrated_url, "base")
    await asyncio.to_thread(migrate.upgrade, migrated_url)
    app_url = make_url(asyncpg_url(migrated_url)).set(username="tristhana_app", password="test")
    app_engine = build_engine(
        app_url.render_as_string(hide_password=False), ca_file=None, pool_size=1, max_overflow=0
    )
    try:
        repo = SqlAccountRepository(app_engine)
        created = await repo.create_with_identity(KEY, NewAccount(display_name="A", locale="en"))
        assert await repo.find_by_identity(KEY) == created
        async with app_engine.connect() as conn:
            with pytest.raises(ProgrammingError, match="permission denied"):
                await conn.execute(text("CREATE TABLE tristhana.nope (id int)"))
    finally:
        await app_engine.dispose()


async def test_statement_timeout_is_storage_unavailable(engine: AsyncEngine) -> None:
    # Server-side "can't serve you now" errors (here 57014) must not become 500s.
    async def slow_query() -> None:
        async with connection(engine) as conn:
            await conn.execute(text("SET statement_timeout = 50"))
            await conn.execute(text("SELECT pg_sleep(1)"))

    with pytest.raises(StorageUnavailable):
        await slow_query()


async def test_other_integrity_errors_are_not_identity_taken(engine: AsyncEngine) -> None:
    repo = SqlAccountRepository(engine)

    with pytest.raises(IntegrityError):  # CHECK violation, a bug: not a lost race
        await repo.create_with_identity(KEY, NewAccount(display_name="x" * 65, locale="en"))


async def test_errors_do_not_echo_parameters(engine: AsyncEngine) -> None:
    repo = SqlAccountRepository(engine)

    with pytest.raises(IntegrityError) as e:
        await repo.create_with_identity(KEY, NewAccount(display_name="Secretname" * 7, locale="en"))
    assert "Secretname" not in str(e.value)
