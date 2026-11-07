"""Moon days and moon-reminder settings (MD-03). Shared by the bot and the API; every call
acts on the caller's own account (`Principal`)."""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

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
from tristhana.domain.accounts import Account, home_city_of, moon_follow_of, moon_shared
from tristhana.domain.days import check_range, local_today, provisional_zone
from tristhana.domain.moon import (
    FOLLOW_SHALA,
    FOLLOW_TEACHER,
    Cities,
    City,
    MoonDay,
    MoonFollow,
    home_dates,
)
from tristhana.domain.notifications import (
    KEEP,
    NotificationPatch,
    NotificationSettings,
    defaults_for,
)

DEFAULT_WINDOW = timedelta(days=60)
_PAIRING = timedelta(days=1)  # MD-04: the home city's same phase within ±1 day


class UnknownLocation(ValueError):
    pass


_FOLLOWS = {"teacher": FOLLOW_TEACHER, "shala": FOLLOW_SHALA}


@dataclass(frozen=True, slots=True)
class MoonView:
    follow: MoonFollow  # MD-02: the effective city and where it comes from
    explicit: bool  # a city or "Follow my teacher" was chosen
    today: date
    days: list[MoonDay]
    settings: NotificationSettings
    zone: str | None  # the account's own zone; reminders never use the provisional one
    home: City | None = None  # MD-04: the person's own city, when it isn't the followed one
    home_dates: dict[date, date] = field(default_factory=dict[date, date])  # followed → home
    shared: bool | None = None  # None: no students; else whether students follow a choice

    @property
    def city(self) -> City:
        return self.follow.city

    @property
    def zone_known(self) -> bool:
        return self.zone is not None


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
        follow = moon_follow_of(account, self._cities)
        city = follow.city
        zone = account.timezone or provisional_zone(account.locale)
        today = local_today(self._clock.now(), zone)
        start = start or today
        end = end or start + DEFAULT_WINDOW
        check_range(start, end)
        home = home_city_of(account, self._cities)
        pairs: dict[date, date] = {}
        if home is None or home.slug == city.slug:
            home = None
            days = await self._moon.days(city.slug, start, end)
        else:  # both calendars in one statement, a day wider for the ±1 pairing
            both = await self._moon.days_for(
                [city.slug, home.slug], start - _PAIRING, end + _PAIRING
            )
            days = [d for d in both[city.slug] if start <= d.date <= end]
            pairs = home_dates(days, both[home.slug])
        settings = await self._notifications.settings(
            account.id, defaults_for(account.day_off.days)
        )
        return MoonView(
            follow,
            follow.explicit,
            today,
            days,
            settings,
            account.timezone,
            home,
            pairs,
            moon_shared(account, self._cities),
        )


class SetMoonLocation:
    def __init__(self, cities: Cities, accounts: AccountRepository) -> None:
        self._cities, self._accounts = cities, accounts

    async def execute(
        self,
        principal: Principal,
        slug: str | None,
        follow: Literal["teacher", "shala"] = "teacher",
    ) -> Account:
        """Stores what was chosen, so an explicit Mysuru isn't mistaken for never choosing
        (ID-04). `None` = "Follow my teacher" (MD-02), or "Follow my shala" with `follow`
        (SC-01): nothing writes NULL any more. Raises `UnknownLocation`."""
        if slug is not None and self._cities.find(slug) is None:
            raise UnknownLocation(slug)
        stored = slug if slug is not None else _FOLLOWS[follow]
        return await self._accounts.set_moon_location(principal.account.id, stored)


@dataclass(frozen=True, slots=True)
class KeepResult:
    kept: bool  # False: a choice was made in the meantime, nothing written
    follow: MoonFollow


class KeepMoonCity:
    """`[Keep 📍 …]` on the first-student note (MD-02, decision 3): the inherited city
    becomes the person's own choice, only while they have none. Bot only."""

    def __init__(self, cities: Cities, accounts: AccountRepository) -> None:
        self._cities, self._accounts = cities, accounts

    async def execute(self, principal: Principal, slug: str) -> KeepResult:
        """Raises `UnknownLocation`."""
        if self._cities.find(slug) is None:
            raise UnknownLocation(slug)
        saved = await self._accounts.set_moon_location_if_unset(principal.account.id, slug)
        if saved is None:
            return KeepResult(False, moon_follow_of(principal.account, self._cities))
        return KeepResult(True, moon_follow_of(saved, self._cities))


class UseCityTimezone:
    """ "Use Almaty time for reminders?" Yes: an explicit choice, only while no zone is set
    (06 Time Zones: never a guess, never overwritten)."""

    def __init__(self, cities: Cities, accounts: AccountRepository) -> None:
        self._cities, self._accounts = cities, accounts

    async def execute(self, principal: Principal, slug: str) -> Account:
        city = self._cities.find(slug)
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
    """The API's read of the caller's notification settings."""

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
