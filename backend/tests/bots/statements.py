"""Counts what one update costs in the in-memory storage (UI-06 §2, the "After" column).

Every public coroutine of the fake repositories is one statement, as in the SQL ones; a fake
calling another fake counts once. What the middleware's `EnsureAccount` does is left out, as
the spec's counts leave it out: the account lookup, the first contact's insert, and the
about-once-a-day `last_seen_at` refresh.
"""

import inspect
from collections.abc import Callable
from typing import Any

import pytest

from tests.fakes import (
    InMemoryCheckIns,
    InMemoryDiary,
    InMemoryPractices,
    InMemoryProgression,
    InMemoryStorage,
)

_MIDDLEWARE = frozenset({"find_by_identity", "create_with_identity", "update_profile"})


class Statements:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, storage: InMemoryStorage) -> None:
        self.names: list[str] = []
        self._depth = 0
        repos: list[Any] = [
            storage.repo,
            storage.day_repo,
            storage.day_repo.periods,
            storage.moon_repo,
            storage.notifications,
            storage.teacher_links,
            storage.teacher_view,
            storage.shalas,
            storage.schedule,
            storage.listings,
            storage.announcements,
            storage.attendance,
            storage.calendar_feed,
        ]
        # With their base classes: a storage built from subclassed fakes inherits most methods.
        classes: set[type[Any]] = {base for repo in repos for base in type(repo).__mro__}
        classes |= {InMemoryPractices, InMemoryCheckIns, InMemoryDiary, InMemoryProgression}
        classes.discard(object)
        for cls in classes:
            for name, member in vars(cls).items():
                if name.startswith("_") or not inspect.iscoroutinefunction(member):
                    continue
                if name in _MIDDLEWARE:
                    continue
                monkeypatch.setattr(cls, name, self._counted(f"{cls.__name__}.{name}", member))

    def _counted(self, label: str, original: Callable[..., Any]) -> Callable[..., Any]:
        async def counted(*args: Any, **kwargs: Any) -> Any:
            if self._depth == 0:
                self.names.append(label)
            self._depth += 1
            try:
                return await original(*args, **kwargs)
            finally:
                self._depth -= 1

        return counted

    def clear(self) -> None:
        self.names.clear()

    @property
    def count(self) -> int:
        return len(self.names)
