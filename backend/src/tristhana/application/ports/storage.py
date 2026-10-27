from datetime import datetime
from typing import Protocol

from tristhana.application.ports.accounts import AccountRepository
from tristhana.application.ports.check_in import CheckInRepository
from tristhana.application.ports.days import DayLogRepository
from tristhana.application.ports.diary import DiaryRepository
from tristhana.application.ports.moon import MoonCalendarRepository
from tristhana.application.ports.notifications import NotificationRepository
from tristhana.application.ports.practice import PracticeRepository
from tristhana.application.ports.progression import ProgressionRepository
from tristhana.application.ports.rest_periods import RestPeriodRepository


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

    @property
    def days(self) -> DayLogRepository: ...

    @property
    def practices(self) -> PracticeRepository: ...

    @property
    def moon(self) -> MoonCalendarRepository: ...

    @property
    def notifications(self) -> NotificationRepository: ...

    @property
    def rest_periods(self) -> RestPeriodRepository: ...

    @property
    def check_ins(self) -> CheckInRepository: ...

    @property
    def diary(self) -> DiaryRepository: ...

    @property
    def progression(self) -> ProgressionRepository: ...


class Clock(Protocol):
    def now(self) -> datetime:
        """The current instant, timezone-aware UTC."""
        ...
