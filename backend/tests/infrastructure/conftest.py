"""Real Postgres for infrastructure tests (ADR-0014: no SQLite).

Set TEST_DATABASE_URL (CI: a service container; locally see backend/README.md). The tests
are skipped without it, except in CI, where a missing database is an error.
"""

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.infrastructure.db import migrate
from tristhana.infrastructure.db.engine import build_engine


def _test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if url:
        return url
    if os.environ.get("CI"):
        pytest.fail("TEST_DATABASE_URL must be set in CI")
    pytest.skip("TEST_DATABASE_URL not set")


@pytest.fixture(scope="session")
def migrated_url() -> str:
    """The test database at the latest schema (migrated once per session)."""
    url = _test_database_url()
    migrate.upgrade(url)
    return url


@pytest.fixture
async def engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    engine = build_engine(migrated_url, ca_file=None, pool_size=3, max_overflow=2)
    async with engine.connect() as conn:
        await conn.execute(
            text("TRUNCATE tristhana.account, tristhana.identity, tristhana.day_log")
        )
    yield engine
    await engine.dispose()
