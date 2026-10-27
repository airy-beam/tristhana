"""Engine and connections (ADR-0014): asyncpg through the Supabase session pooler."""

import ssl
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from tristhana.application.ports.export import AccountGone
from tristhana.application.ports.storage import StorageUnavailable

# Fail fast: a tap should get a gentle "try again" rather than hang until Telegram gives up.
CONNECT_TIMEOUT_S = 5
COMMAND_TIMEOUT_S = 5

# Server-side SQLSTATEs that mean "the database can't serve us right now", not a bug:
# 08 connection, 53 resources (too many connections), 57 operator intervention (shutdown,
# cannot connect now, statement_timeout = 57014), 55P03 lock_timeout, XX000 (Supavisor
# pooler errors such as max client connections).
_UNAVAILABLE_CLASSES = ("08", "53", "57")
_UNAVAILABLE_STATES = frozenset({"55P03", "XX000"})


def asyncpg_url(url: str) -> str:
    """Accept the plain `postgresql://` URL Supabase shows and select the asyncpg driver."""
    for prefix in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url.removeprefix(prefix)
    raise ValueError("DATABASE_URL must be a postgresql:// URL")


def connect_args(ca_file: Path | None) -> dict[str, Any]:
    args: dict[str, Any] = {
        "timeout": CONNECT_TIMEOUT_S,
        "command_timeout": COMMAND_TIMEOUT_S,
        "server_settings": {"application_name": "tristhana"},
    }
    if ca_file is not None:
        args["ssl"] = tls_context(ca_file)
    return args


def tls_context(ca_file: Path) -> ssl.SSLContext:
    """verify-full against the pinned CA: chain and hostname are checked.

    Python 3.13 also enables VERIFY_X509_STRICT, which rejects Supabase's root CA (2021) for
    lacking a keyUsage extension; libpq doesn't apply that rule. Only that flag is dropped.
    """
    context = ssl.create_default_context(cafile=str(ca_file))
    context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return context


def build_engine(
    url: str, *, ca_file: Path | None, pool_size: int, max_overflow: int
) -> AsyncEngine:
    return create_async_engine(
        asyncpg_url(url),
        connect_args=connect_args(ca_file),
        # Exception messages would otherwise carry bound values (Telegram ids, names) into logs.
        hide_parameters=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=CONNECT_TIMEOUT_S,
        # A connection can die while Cloud Run throttles the CPU between requests.
        pool_pre_ping=True,
        pool_recycle=600,
        # Every repository call is a single statement, so no BEGIN/COMMIT round trips.
        isolation_level="AUTOCOMMIT",
    )


@asynccontextmanager
async def connection(engine: AsyncEngine) -> AsyncGenerator[AsyncConnection]:
    """A pooled connection; "database unavailable" failures become `StorageUnavailable`."""
    try:
        async with engine.connect() as conn:
            yield conn
    except (OSError, TimeoutError, OperationalError, InterfaceError, PoolTimeout) as e:
        raise StorageUnavailable(type(e).__name__) from e
    except DBAPIError as e:
        if e.connection_invalidated or is_unavailable(sqlstate(e)):
            raise StorageUnavailable(type(e).__name__) from e
        if is_account_gone(e):
            raise AccountGone from e
        raise


def sqlstate(error: DBAPIError) -> str:
    return str(getattr(error.orig, "sqlstate", "") or "")


def is_account_gone(error: DBAPIError) -> bool:
    """A write hit the missing parent row of a just-deleted account (ST-09): 23503 on an
    `<table>_account_id_fkey` constraint."""
    if sqlstate(error) != "23503":
        return False
    cause = getattr(error.orig, "__cause__", None)
    name = str(getattr(cause, "constraint_name", "") or getattr(error.orig, "constraint_name", ""))
    return name.endswith("_account_id_fkey")


def is_unavailable(state: str) -> bool:
    return state.startswith(_UNAVAILABLE_CLASSES) or state in _UNAVAILABLE_STATES
