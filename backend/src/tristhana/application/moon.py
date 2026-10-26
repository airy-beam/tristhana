"""Moon days and moon-reminder settings (MD-03). Shared by the bot and the API; every call
acts on the caller's own account (`Principal`)."""

from dataclasses import dataclass, replace
from datetime import date, timedelta

from tristhana.application.policies import Principal
from tristhana.application.ports.accounts import AccountRepository
from tristhana.application.ports.moon import MoonCalendarRepository
from tristhana.application.ports.notifications import (
    MoonPatch,
    NotificationRepository,
    PracticePause,
)
from tristhana.application.ports.storage import Clock
from tristhana.application.settings import PatchNotificationSettings, caller_today
from tristhana.domain.accounts import Account
from tristhana.domain.days import check_range, local_today, provisional_zone
from tristhana.domain.moon import Cities, City, MoonDay
from tristhana.domain.notifications import (
    KEEP,
    NotificationPatch,
    NotificationSettings,
    PracticeReminders,
    check_settings,
    defaults_for,
)

DEFAULT_WINDOW = timedelta(days=60)


class UnknownLocation(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MoonView:
    city: City
    explicit: bool  # False: the default city, never chosen
    today: date
    days: list[MoonDay]
    settings: NotificationSettings
    zone: str | None  # the account's own zone; reminders never use the provisional one

    @property
    def zone_known(self) -> bool:
        return self.zone is not None


def _city(cities: Cities, account: Account) -> tuple[City, bool]:
    city = cities.get(account.moon_location)
    if city is None:  # a city removed from the list: fall back, never fail
        return cities.default, False
    return city, account.moon_location is not None


class GetMoonView:
    def __init__(
        self,
        cities: Cities,
        moon: MoonCalendarRepository,
        notifications: NotificationRepository,
        clock: Clock,
    ) -> None:
        self._cities, self._moon, self._notifications, self._clock = (
            cities,
            moon,
            notifications,
            clock,
        )

    async def execute(
        self, principal: Principal, start: date | None = None, end: date | None = None
    ) -> MoonView:
        """Raises `InvalidRange`. Defaults to today … +60 days."""
        account = principal.account
        city, explicit = _city(self._cities, account)
        zone = account.timezone or provisional_zone(account.locale)
        today = local_today(self._clock.now(), zone)
        start = start or today
        end = end or start + DEFAULT_WINDOW
        check_range(start, end)
        days = await self._moon.days(city.slug, start, end)
        settings = await self._notifications.settings(
            account.id, defaults_for(account.day_off.days)
        )
        return MoonView(city, explicit, today, days, settings, account.timezone)


class SetMoonLocation:
    def __init__(self, cities: Cities, accounts: AccountRepository) -> None:
        self._cities, self._accounts = cities, accounts

    async def execute(self, principal: Principal, slug: str | None) -> Account:
        """`None` = back to the default. Raises `UnknownLocation`."""
        if slug is not None and self._cities.get(slug) is None:
            raise UnknownLocation(slug)
        stored = None if slug == self._cities.default.slug else slug
        return await self._accounts.set_moon_location(principal.account.id, stored)


class UseCityTimezone:
    """ "Use Almaty time for reminders?" Yes: an explicit choice, only while no zone is set
    (06 Time Zones: never a guess, never overwritten)."""

    def __init__(self, cities: Cities, accounts: AccountRepository) -> None:
        self._cities, self._accounts = cities, accounts

    async def execute(self, principal: Principal, slug: str) -> Account:
        city = self._cities.get(slug)
        if city is None:
            raise UnknownLocation(slug)
        account = principal.account
        if account.timezone is not None:
            return account
        return await self._accounts.set_timezone_if_unset(account.id, city.location.tz)


class UpdateMoonReminders:
    """The bot's moon reminder taps: a partial change, validated against the stored
    settings (custom quiet hours included)."""

    def __init__(self, notifications: NotificationRepository) -> None:
        self._patch = PatchNotificationSettings(notifications)

    async def execute(self, principal: Principal, patch: MoonPatch) -> NotificationSettings:
        """Raises `InvalidSettings`."""
        return await self._patch.execute(
            principal,
            NotificationPatch(
                moon_offsets=KEEP if patch.offsets is None else patch.offsets,
                moon_at=KEEP if patch.at is None else patch.at,
            ),
        )


class NotificationSettingsUseCase:
    """The API's full read/replace of the caller's notification settings."""

    def __init__(self, notifications: NotificationRepository, clock: Clock) -> None:
        self._notifications = notifications
        self._clock = clock

    async def get(self, principal: Principal) -> NotificationSettings:
        account = principal.account
        return await self._notifications.settings(account.id, defaults_for(account.day_off.days))

    async def get_with_pause(
        self, principal: Principal
    ) -> tuple[NotificationSettings, PracticePause | None]:
        """The settings and the rest period covering the caller's today, for "⏸ Paused
        through …" (WH-01). One statement."""
        account = principal.account
        defaults = defaults_for(account.day_off.days)
        today = caller_today(principal, self._clock)
        return await self._notifications.settings_with_pause(account.id, defaults, today)

    async def save(
        self,
        principal: Principal,
        settings: NotificationSettings,
        practice: PracticeReminders | None = None,
    ) -> NotificationSettings:
        """`practice` None = keep the stored one (older clients don't send it). Raises
        `InvalidSettings`."""
        account_id = principal.account.id
        if practice is None:  # validate against the stored one, but don't write it back
            defaults = defaults_for(principal.account.day_off.days)
            stored = (await self._notifications.settings(account_id, defaults)).practice
            check_settings(replace(settings, practice=stored))
            return await self._notifications.save(account_id, settings, with_practice=False)
        settings = replace(settings, practice=practice)
        return await self._notifications.save(account_id, check_settings(settings))
