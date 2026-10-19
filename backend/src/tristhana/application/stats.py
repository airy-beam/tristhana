"""Practice stats for one year (ST-01..03, ADR-0020). The caller's own data only
(`Principal`): a later teacher view goes through a policy and `public_status`, so it can
never see a ladies' holiday."""

from dataclasses import dataclass
from datetime import date

from tristhana.application.policies import Principal
from tristhana.application.ports.days import DayLogRepository
from tristhana.application.ports.moon import MoonCalendarRepository
from tristhana.application.ports.storage import Clock
from tristhana.domain.days import MIN_LOG_DATE, local_today, provisional_zone
from tristhana.domain.moon import Cities, City, MoonDay
from tristhana.domain.practice import PracticeCatalog
from tristhana.domain.stats import YearStats, year_stats


class InvalidYear(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class YearStatsView:
    today: date
    timezone_known: bool
    year: int
    first_year: int | None  # the earliest year with a logged day
    city: City  # whose moon days are marked
    moon_days: list[MoonDay]  # the whole year (future ones are markers too)
    stats: YearStats


class GetYearStats:
    def __init__(
        self,
        days: DayLogRepository,
        moon: MoonCalendarRepository,
        cities: Cities,
        catalog: PracticeCatalog,
        clock: Clock,
    ) -> None:
        self._days, self._moon, self._cities = days, moon, cities
        self._catalog, self._clock = catalog, clock

    async def execute(self, principal: Principal, year: int | None = None) -> YearStatsView:
        """Defaults to the local current year. Raises `InvalidYear`. Two statements."""
        account = principal.account
        known = account.timezone is not None
        # A provisional zone is fine here: display only, like GetDays.
        today = local_today(self._clock.now(), account.timezone or provisional_zone(account.locale))
        year = year if year is not None else today.year
        if not MIN_LOG_DATE.year <= year <= today.year:
            raise InvalidYear(str(year))
        # The year either side, so a run crossing New Year is counted whole from both years.
        history = await self._days.history(
            account.id, date(year - 1, 1, 1), min(date(year + 1, 12, 31), today)
        )
        city = self._cities.get(account.moon_location) or self._cities.default
        moon_days = await self._moon.days(city.slug, date(year, 1, 1), date(year, 12, 31))
        by_date = {d.local_date: d for d in history.days}
        stats = year_stats(by_date, year, today, self._series_number)
        first_year = history.first_date.year if history.first_date else None
        return YearStatsView(today, known, year, first_year, city, moon_days, stats)

    def _series_number(self, slug: str) -> int | None:
        series = self._catalog.get(slug)
        return series.number if series else None
