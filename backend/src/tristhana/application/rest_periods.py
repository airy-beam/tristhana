"""Rest periods (WH-01 part 2, ADR-0023). Shared by the bot and the API; every call acts on
the caller's own account (`Principal`), so no policy beyond it (as PR-01)."""

from datetime import date

from tristhana.application.policies import Principal
from tristhana.application.ports.rest_periods import Ended, Placed, RestPeriodRepository
from tristhana.application.ports.storage import Clock
from tristhana.application.settings import caller_today
from tristhana.domain.days import DayStatus
from tristhana.domain.rest_periods import RestPeriod, check_period, check_restore, is_recent


class StartRestPeriod:
    def __init__(self, periods: RestPeriodRepository, clock: Clock) -> None:
        self._periods, self._clock = periods, clock

    async def execute(
        self, principal: Principal, start: date, days: int, kind: DayStatus
    ) -> Placed:
        """Raises `InvalidRestPeriod`, `DateInFuture`. One statement (also says whether
        practice reminders are on, for the wording). `period` None: the start day is logged
        as something else by now (a stale day count), nothing written."""
        account = principal.account
        period = check_period(start, days, kind, self._clock.now(), account.timezone)
        return await self._periods.place(account.id, period)


class RestoreRestPeriod:
    def __init__(self, periods: RestPeriodRepository, clock: Clock) -> None:
        self._periods, self._clock = periods, clock

    async def execute(self, principal: Principal, period: RestPeriod) -> RestPeriod | None:
        """ "Keep the pause". Raises `InvalidRestPeriod`; None when nothing is left, or when
        no 🧘 Practiced day inside it shows a cut happened (never a backfill)."""
        account = principal.account
        checked = check_restore(period, self._clock.now(), account.timezone)
        if checked is None:
            return None
        today = caller_today(principal, self._clock)
        return await self._periods.restore(account.id, checked, today)


class EndRestPeriod:
    def __init__(self, periods: RestPeriodRepository, clock: Clock) -> None:
        self._periods, self._clock = periods, clock

    async def execute(self, principal: Principal, start: date) -> Ended:
        """End early: stops covering today. Idempotent. One statement."""
        today = caller_today(principal, self._clock)
        return await self._periods.end(principal.account.id, start, today)


class SkipRestPeriod:
    """ "Just today / yesterday": the day stays as logged, with no pause. Drops a pause that
    starts on that day (a re-asked first day); never touches one that started earlier, and
    does nothing for an old button tapped days later."""

    def __init__(self, periods: RestPeriodRepository, clock: Clock) -> None:
        self._periods, self._clock = periods, clock

    async def execute(self, principal: Principal, day: date) -> Ended:
        """At most one statement."""
        account = principal.account
        if not is_recent(day, self._clock.now(), account.timezone):
            return Ended(None)
        # `end_from` with "today" = its first day removes the period starting on `day`.
        return await self._periods.end(account.id, day, day)
