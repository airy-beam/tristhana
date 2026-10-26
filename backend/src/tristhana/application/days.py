"""Day status use cases (PR-01, PR-04). The bot and the API share them; every call acts on
the caller's own days (`Principal`). "Today" is always computed here, never by a client."""

from dataclasses import dataclass, field
from datetime import date, timedelta

from tristhana.application.policies import Principal
from tristhana.application.ports.days import DayLogRepository
from tristhana.application.ports.storage import Clock
from tristhana.domain.accounts import Account
from tristhana.domain.days import (
    MIN_LOG_DATE,
    DayLog,
    DayStatus,
    check_loggable,
    check_range,
    local_today,
    provisional_zone,
)
from tristhana.domain.moon import Cities, City
from tristhana.domain.rest_days import AutoDay, auto_days, joined_on
from tristhana.domain.rest_periods import (
    PauseOffer,
    RestPeriod,
    covered_days,
    offer_today,
    pause_offer,
)

DEFAULT_WINDOW = timedelta(days=7)


@dataclass(frozen=True, slots=True)
class DaysView:
    today: date
    timezone_known: bool  # False: "today" came from a provisional zone (bot-only users)
    days: list[DayLog]
    auto: dict[date, AutoDay]  # unlogged days shown as rest (PR-09, ADR-0022)
    city: City  # whose moon days the auto days follow
    periods: tuple[RestPeriod, ...] = ()  # overlapping the window, unclipped (WH-01)
    covered: dict[date, DayStatus] = field(default_factory=dict[date, DayStatus])
    practice_on: bool = False  # practice reminders on (labels on covered days)

    def period_on(self, day: date) -> RestPeriod | None:
        return next((p for p in self.periods if p.covers(day)), None)


@dataclass(frozen=True, slots=True)
class DaySaved:
    day: DayLog
    offer: PauseOffer | None = None  # "for how many days?" (WH-01)
    period: RestPeriod | None = None  # the period now covering `day`
    cut: RestPeriod | None = None  # the period as it was before a 🧘 cut it ("keep")
    practice_on: bool = False


def _zone(principal: Principal) -> tuple[str, bool]:
    account = principal.account
    if account.timezone is not None:
        return account.timezone, True
    return provisional_zone(account.locale), False


def joined(account: Account, zone: str) -> date:
    """The first date auto-rest may fill: the local date the account was created."""
    return joined_on(account.created_at, zone) if account.created_at else MIN_LOG_DATE


class GetDays:
    def __init__(self, days: DayLogRepository, cities: Cities, clock: Clock) -> None:
        self._days = days
        self._cities = cities
        self._clock = clock

    def today(self, principal: Principal) -> tuple[date, bool]:
        """The caller's local date (no DB access), and whether their zone is known."""
        zone, known = _zone(principal)
        return local_today(self._clock.now(), zone), known

    async def execute(
        self, principal: Principal, start: date | None = None, end: date | None = None
    ) -> DaysView:
        """Raises `InvalidRange`. Defaults to the 7 days ending today. One statement."""
        account = principal.account
        zone, known = _zone(principal)
        today = local_today(self._clock.now(), zone)
        end = end or today
        start = start or end - DEFAULT_WINDOW + timedelta(days=1)
        check_range(start, end)
        city = self._cities.get(account.moon_location) or self._cities.default
        view = await self._days.range_with_moon(account.id, start, end, city.slug)
        logged = {d.local_date for d in view.days}
        covered = covered_days(view.periods, start, end, today, logged)
        auto = auto_days(
            start,
            end,
            today,
            joined(account, zone),
            logged,
            account.day_off,
            view.moon_dates,
            covered=covered.keys(),
        )
        return DaysView(
            today, known, view.days, auto, city, view.periods, covered, view.practice_on
        )


class SetDayStatus:
    def __init__(self, days: DayLogRepository, clock: Clock) -> None:
        self._days = days
        self._clock = clock

    async def execute(self, principal: Principal, local_date: date, status: DayStatus) -> DaySaved:
        """Raises `DateInFuture` / `DateTooEarly`. Overwrites any earlier status. 🧘 inside a
        rest period cuts it (returned as `cut`); after 🌸/🤒/✈️ on today or yesterday the
        pause question may follow (`offer`). One statement."""
        account = principal.account
        now = self._clock.now()
        check_loggable(local_date, now, account.timezone)
        day = DayLog(local_date=local_date, status=status)
        saved = await self._days.upsert(account.id, day, account.timezone)
        yesterday = local_date - timedelta(days=1)
        covering = next((p for p in saved.periods if p.covers(local_date)), None)
        before = next((p for p in saved.periods if p.covers(yesterday)), None)
        offer = pause_offer(
            local_date,
            offer_today(local_date, now, account.timezone),
            status,
            saved.prev,
            covering,
            before,
            saved.practice_on,
        )
        period = None if saved.cut is not None else covering
        return DaySaved(saved.day, offer, period, saved.cut, saved.practice_on)


class ClearDayStatus:
    def __init__(self, days: DayLogRepository) -> None:
        self._days = days

    async def execute(self, principal: Principal, local_date: date) -> None:
        await self._days.delete(principal.account.id, local_date)
