"""Check-in trends (ST-05): the caller's own, derived on every read. Nothing is written."""

from dataclasses import dataclass

from tristhana.application.policies import NotAllowed, Principal, can_view_check_ins
from tristhana.application.ports.check_in_trends import CheckInTrendsRepository
from tristhana.application.ports.storage import Clock
from tristhana.domain.accounts import moon_follow_of
from tristhana.domain.check_in_trends import Trends, trends, window
from tristhana.domain.days import local_today, provisional_zone
from tristhana.domain.moon import Cities, City


@dataclass(frozen=True, slots=True)
class TrendsView:
    trends: Trends
    city: City  # the calendar the moon view was read against: the one followed today


class GetCheckInTrends:
    def __init__(self, repo: CheckInTrendsRepository, cities: Cities, clock: Clock) -> None:
        self._repo, self._cities, self._clock = repo, cities, clock

    async def execute(self, principal: Principal) -> TrendsView:
        """Owner only (ADR-0024). One statement, then the rules in memory."""
        account = principal.account
        if not can_view_check_ins(account, account):
            raise NotAllowed
        # A provisional zone is fine: display only, like the stats and the badges.
        zone = account.timezone or provisional_zone(account.locale)
        today = local_today(self._clock.now(), zone)
        # The follow has no history (ADR-0032): today's city serves the whole window.
        city = moon_follow_of(account, self._cities).city
        start, end = window(today)
        facts = await self._repo.facts(account.id, city.slug, start, end)
        return TrendsView(trends(facts, today), city)
