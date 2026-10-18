"""Day status use cases (PR-01, PR-04). The bot and the API share them; every call acts on
the caller's own days (`Principal`). "Today" is always computed here, never by a client."""

from dataclasses import dataclass
from datetime import date, timedelta

from tristhana.application.policies import Principal
from tristhana.application.ports.days import DayLogRepository
from tristhana.application.ports.storage import Clock
from tristhana.domain.days import (
    DayLog,
    DayStatus,
    check_loggable,
    check_range,
    local_today,
    provisional_zone,
)

DEFAULT_WINDOW = timedelta(days=7)


@dataclass(frozen=True, slots=True)
class DaysView:
    today: date
    timezone_known: bool  # False: "today" came from a provisional zone (bot-only users)
    days: list[DayLog]


def _zone(principal: Principal) -> tuple[str, bool]:
    account = principal.account
    if account.timezone is not None:
        return account.timezone, True
    return provisional_zone(account.locale), False


class GetDays:
    def __init__(self, days: DayLogRepository, clock: Clock) -> None:
        self._days = days
        self._clock = clock

    def today(self, principal: Principal) -> tuple[date, bool]:
        """The caller's local date (no DB access), and whether their zone is known."""
        zone, known = _zone(principal)
        return local_today(self._clock.now(), zone), known

    async def execute(
        self, principal: Principal, start: date | None = None, end: date | None = None
    ) -> DaysView:
        """Raises `InvalidRange`. Defaults to the 7 days ending today."""
        today, known = self.today(principal)
        end = end or today
        start = start or end - DEFAULT_WINDOW + timedelta(days=1)
        check_range(start, end)
        logged = await self._days.list_range(principal.account.id, start, end)
        return DaysView(today=today, timezone_known=known, days=logged)


class SetDayStatus:
    def __init__(self, days: DayLogRepository, clock: Clock) -> None:
        self._days = days
        self._clock = clock

    async def execute(self, principal: Principal, local_date: date, status: DayStatus) -> DayLog:
        """Raises `DateInFuture` / `DateTooEarly`. Overwrites any earlier status."""
        account = principal.account
        check_loggable(local_date, self._clock.now(), account.timezone)
        day = DayLog(local_date=local_date, status=status)
        return await self._days.upsert(account.id, day, account.timezone)


class ClearDayStatus:
    def __init__(self, days: DayLogRepository) -> None:
        self._days = days

    async def execute(self, principal: Principal, local_date: date) -> None:
        await self._days.delete(principal.account.id, local_date)
