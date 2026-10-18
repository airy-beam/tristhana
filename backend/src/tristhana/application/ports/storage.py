from datetime import datetime
from typing import Protocol

from tristhana.application.ports.accounts import AccountRepository


class StorageUnavailable(Exception):
    """The database can't be reached (or isn't configured). Callers show a gentle retry."""


class Storage(Protocol):
    """The database as a whole: lifecycle, health and repositories."""

    async def start(self) -> None:
        """Build the pool and warm one connection. A down database doesn't raise (it must not
        block startup); a misconfiguration (bad URL, missing CA file) does, so a broken
        revision never receives traffic."""
        ...

    async def stop(self) -> None: ...

    async def ping(self) -> None:
        """One trivial query; raises `StorageUnavailable`."""
        ...

    @property
    def accounts(self) -> AccountRepository: ...


class Clock(Protocol):
    def now(self) -> datetime:
        """The current instant, timezone-aware UTC."""
        ...
