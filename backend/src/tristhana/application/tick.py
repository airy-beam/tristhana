"""The scheduler tick (ADR-0018): send due reminders, keep moon calendars filled, prune.

Runs inside one HTTP request (Cloud Run throttles the CPU after the response), so every
step watches the deadline and leaves the rest to the next tick (every 10 min).
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from tristhana.application.ports.moon import MoonCalculator, MoonCalendarRepository
from tristhana.application.ports.notifications import (
    DeliveryStatus,
    MoonCandidate,
    MoonReminder,
    NotificationRepository,
    Notifier,
    Recipient,
)
from tristhana.application.ports.storage import Clock
from tristhana.domain.moon import Cities, MoonDay, calendar_years
from tristhana.domain.notifications import DEFAULTS, Candidate, due_moon_reminders

log = logging.getLogger(__name__)

KEEP_DELIVERIES = timedelta(days=60)
LOOKBACK = timedelta(days=12)  # deliveries that matter for dedupe (offsets ≤ 7 + grace)


@dataclass(slots=True)
class TickResult:
    sent: int = 0
    skipped: int = 0
    failed: int = 0
    blocked: int = 0
    computed: int = 0
    pruned: int = 0
    stopped_early: bool = False


class RunTick:
    def __init__(
        self,
        clock: Clock,
        cities: Cities,
        moon: MoonCalendarRepository,
        calculator: MoonCalculator,
        notifications: NotificationRepository,
        notifier: Notifier,
    ) -> None:
        self._clock = clock
        self._cities = cities
        self._moon = moon
        self._calculator = calculator
        self._notifications = notifications
        self._notifier = notifier

    async def execute(self, budget: timedelta) -> TickResult:
        """Work for at most `budget` (measured on this use case's clock)."""
        deadline = self._clock.now() + budget
        result = TickResult()
        await self._send(deadline, result)
        await self._top_up(deadline, result)
        if self._clock.now() < deadline:
            result.pruned = await self._notifications.prune(self._clock.now() - KEEP_DELIVERIES)
        return result

    async def _send(self, deadline: datetime, result: TickResult) -> None:
        now = self._clock.now()
        candidates = await self._notifications.moon_candidates(now - LOOKBACK, DEFAULTS)
        if not candidates:
            return
        utc_today = now.date()
        start, end = utc_today - timedelta(days=1), utc_today + timedelta(days=9)
        calendars: dict[str, list[MoonDay]] = {}
        for c in candidates:
            if self._clock.now() >= deadline:
                result.stopped_early = True
                return
            city = self._cities.get(c.location) or self._cities.default
            if city.slug not in calendars:
                calendars[city.slug] = await self._moon.days(city.slug, start, end)
            if not await self._send_to(c, city.slug, calendars[city.slug], deadline, result):
                result.stopped_early = True  # rate limited or out of time: next tick
                return

    async def _send_to(
        self,
        c: MoonCandidate,
        slug: str,
        days: list[MoonDay],
        deadline: datetime,
        result: TickResult,
    ) -> bool:
        """False when Telegram asks to slow down or time is up (stop the whole run)."""
        now = self._clock.now()
        local_today = now.astimezone(ZoneInfo(c.zone)).date()
        candidate = Candidate(
            zone=c.zone,
            settings=c.settings,
            moon_days=tuple(days),
            sent_keys=frozenset(d.key for d in c.deliveries if d.final),
            sent_today=sum(
                1 for d in c.deliveries if d.local_date == local_today and d.counts_today
            ),
        )
        city = self._cities.get(slug) or self._cities.default
        intro = not c.had_moon_reminder
        for due in due_moon_reminders(now, candidate):
            if self._clock.now() >= deadline:  # never claim what this run may not finish
                return False
            if not await self._notifications.claim(c.account_id, due.key, "moon", due.local_date):
                result.skipped += 1  # another run has it
                continue
            outcome = await self._notifier.deliver(
                Recipient(c.telegram_id, c.locale),
                MoonReminder(
                    due.moon_day,
                    due.days_before,
                    city,
                    intro,
                    c.settings.moon.offsets,
                    due.local_date,
                ),
            )
            match outcome.status:
                case DeliveryStatus.SENT:
                    await self._notifications.finish(c.account_id, due.key, "sent")
                    result.sent += 1
                    intro = False  # only once it actually arrived
                case DeliveryStatus.BLOCKED:
                    await self._notifications.finish(c.account_id, due.key, "blocked")
                    await self._notifications.mark_unreachable(c.account_id, now)
                    result.blocked += 1
                    return True
                case DeliveryStatus.RETRY_AFTER:
                    await self._notifications.finish(c.account_id, due.key, "failed")
                    result.failed += 1
                    return False
                case DeliveryStatus.FAILED:
                    await self._notifications.finish(c.account_id, due.key, "failed")
                    result.failed += 1
        return True

    async def _top_up(self, deadline: datetime, result: TickResult) -> None:
        """Compute missing or outdated city-years (previous year … current + 2)."""
        coverage = await self._moon.coverage()
        version = self._calculator.version
        years = calendar_years(self._clock.now().date())
        for city in self._cities.all:
            for year in years:
                if coverage.get((city.slug, year)) == version:
                    continue
                if self._clock.now() >= deadline:
                    result.stopped_early = True
                    return
                days = await self._calculator.compute_year(city.location, year)
                await self._moon.replace_year(city.slug, year, days, version)
                result.computed += 1
