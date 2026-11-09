"""Badges (GM-02, ADR-0041): the caller's own, derived on every read. Nothing is written."""

from collections.abc import Sequence
from dataclasses import dataclass

from tristhana.application.days import joined
from tristhana.application.policies import NotAllowed, Principal, can_view_milestones
from tristhana.application.ports.badges import BadgeFactsRepository
from tristhana.application.ports.storage import Clock
from tristhana.domain.accounts import moon_follow_of
from tristhana.domain.badges import BadgeDef, Earned, earned
from tristhana.domain.days import local_today, provisional_zone
from tristhana.domain.moon import Cities
from tristhana.domain.progression import Track


@dataclass(frozen=True, slots=True)
class BadgesView:
    earned: tuple[Earned, ...]  # in definition order


class GetBadges:
    def __init__(
        self,
        badges: BadgeFactsRepository,
        defs: Sequence[BadgeDef],
        track: Track,
        cities: Cities,
        clock: Clock,
    ) -> None:
        self._badges, self._defs, self._track = badges, tuple(defs), track
        self._cities, self._clock = cities, clock

    async def execute(self, principal: Principal) -> BadgesView:
        """Owner only (Q59). One statement, then the rules in memory."""
        account = principal.account
        if not can_view_milestones(account, account):
            raise NotAllowed
        # A provisional zone is fine: display only, like the stats.
        zone = account.timezone or provisional_zone(account.locale)
        today = local_today(self._clock.now(), zone)
        location = moon_follow_of(account, self._cities).city.slug
        facts = await self._badges.facts(account.id, location, today)
        found = earned(
            self._defs,
            facts,
            self._track,
            off=account.day_off,
            joined=joined(account, zone),
            today=today,
        )
        return BadgesView(found)
