"""Alembic environment: async, schema `tristhana`, one migrator at a time (advisory lock)."""

import asyncio
from pathlib import Path
from typing import cast

from alembic import context
from sqlalchemy import Connection, pool, text
from sqlalchemy.ext.asyncio import create_async_engine

from tristhana.infrastructure.db.engine import asyncpg_url, connect_args
from tristhana.infrastructure.db.tables import SCHEMA, metadata

# Any constant shared by all migrators; pg_advisory_lock serializes concurrent job runs.
_MIGRATION_LOCK = 0x7472_6973  # "tris"


def _include_name(name: str | None, type_: str, _parent: object) -> bool:
    # Only our schema: Supabase ships its own (auth, storage, ...) in the same database.
    return name == SCHEMA if type_ == "schema" else True


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=metadata,
        version_table_schema=SCHEMA,
        include_schemas=True,
        include_name=_include_name,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _migrate() -> None:
    config = context.config
    url = cast(str, config.attributes["url"])
    ca_file = cast(Path | None, config.attributes.get("ca_file"))
    engine = create_async_engine(
        asyncpg_url(url), poolclass=pool.NullPool, connect_args=connect_args(ca_file)
    )
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT pg_advisory_lock(:key)"), {"key": _MIGRATION_LOCK})
            # The version table lives in our schema, so the schema must exist first.
            await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
            await conn.run_sync(_run)
            await conn.commit()
    finally:
        await engine.dispose()


asyncio.run(_migrate())
