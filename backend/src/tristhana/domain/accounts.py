"""Accounts and identities (ID-01, ID-02, ADR-0015).

An `Account` is the person; an identity (provider + provider's user id) is one way to log in.
Telegram is the only provider today; email/Google/Apple add identities to the same account.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from functools import cache
from uuid import UUID
from zoneinfo import available_timezones

from tristhana.domain.locale import Locale, negotiate_locale
from tristhana.domain.moon import Cities, City, label_city
from tristhana.domain.rest_days import NEVER_CHOSEN, DayOff

DISPLAY_NAME_MAX = 64
# Write `last_seen_at` (and refresh the profile) at most this often when nothing changed.
LAST_SEEN_PRECISION = timedelta(hours=24)

# Bidi controls can reorder the text around a name; zero-width joiners stay (emoji sequences).
_BIDI_CONTROLS = re.compile("[‪-‮⁦-⁩‎‏]")
_WHITESPACE = re.compile(r"\s+")
_UTC_NAMES = frozenset({"UTC", "Etc/UTC"})
# `account.home_city` (ADR-0029): None = never chosen (the nudge shows), NOT_LISTED = chosen:
# not in the list / not now, otherwise a city slug whose zone is the account's zone.
NOT_LISTED = "-"


class IdentityProvider(StrEnum):
    TELEGRAM = "telegram"


@dataclass(frozen=True, slots=True)
class IdentityKey:
    provider: IdentityProvider
    provider_user_id: str  # text, so every provider's id format fits


@dataclass(frozen=True, slots=True)
class ExternalProfile:
    """What a provider tells us about the person on each contact (unverified for display)."""

    key: IdentityKey
    display_name: str | None
    language_code: str | None


@dataclass(frozen=True, slots=True)
class Account:
    id: UUID
    display_name: str | None
    locale: Locale
    timezone: str | None  # IANA name; None until the device reports it
    last_seen_at: datetime
    moon_location: str | None = None  # city slug (MD-03); None = the default (Mysuru)
    name_custom: bool = False  # chosen in settings: Telegram's name no longer overwrites it
    locale_custom: bool = False  # chosen in settings: Telegram's language no longer does
    created_at: datetime | None = None  # None only in tests: then no join-date bound
    day_off: DayOff = NEVER_CHOSEN  # PR-09
    day_off_dismissed: bool = False  # "Not now" on the one-time day-off question
    hide_ladies: bool = False  # WH-01: leave the 🌸 button out of the status grids
    offer_check_in: bool = True  # PR-06: the one-tap mood row after logging a practice
    home_city: str | None = None  # ADR-0029: None, NOT_LISTED or a city slug

    @property
    def home_city_chosen(self) -> bool:
        return self.home_city is not None


@dataclass(frozen=True, slots=True)
class NewAccount:
    display_name: str | None
    locale: Locale


@dataclass(frozen=True, slots=True)
class ProfileUpdate:
    """Fields to write on a refresh; `last_seen_at` is always set to now with it."""

    display_name: str | None
    locale: Locale


class InvalidTimezone(ValueError):
    pass


class InvalidDisplayName(ValueError):
    pass


class UnknownCity(ValueError):
    pass


class _Keep:
    """A patch field that was not sent: leave it as it is."""

    def __repr__(self) -> str:
        return "KEEP"


KEEP = _Keep()


class _NotNow:
    """ "Not now" on the city nudge: answers it only while it is unanswered, so a stale
    button never wipes a city chosen since (ADR-0029)."""

    def __repr__(self) -> str:
        return "NOT_NOW"


NOT_NOW = _NotNow()


@dataclass(frozen=True, slots=True)
class ProfilePatch:
    """From settings (ID-06). `None` = back to Telegram's (name, language)."""

    display_name: str | _Keep | None = KEEP
    locale: Locale | _Keep | None = KEEP
    timezone: str | _Keep = KEEP
    hide_ladies: bool | _Keep | None = KEEP  # None = the default (shown)
    offer_check_in: bool | _Keep | None = KEEP  # None = the default (offered)
    # A slug (sets its zone too); None = not listed; NOT_NOW = only if never chosen.
    home_city: str | _Keep | _NotNow | None = KEEP


@dataclass(frozen=True, slots=True)
class ProfileChange:
    """Only the groups in `fields` are written ("name", "locale", "timezone"), so two
    settings saves at once (a name, then a language) never undo each other (ADR-0021)."""

    display_name: str | None
    name_custom: bool
    locale: Locale
    locale_custom: bool
    timezone: str | None
    fields: frozenset[str] = frozenset({"name", "locale", "timezone"})
    hide_ladies: bool = False  # written only with "hide_ladies" in `fields`
    offer_check_in: bool = True  # written only with "offer_check_in" in `fields`
    home_city: str | None = None  # written only with "home_city" in `fields`


def resolve_profile(
    account: Account, patch: ProfilePatch, client: ExternalProfile, cities: Cities
) -> ProfileChange:
    """The account fields after applying `patch`. Raises `InvalidDisplayName`,
    `InvalidTimezone`, `UnknownCity`. An explicit zone may be UTC (only ever chosen, never
    guessed). Keeps the ADR-0029 invariant: a home city's zone is the account's zone."""
    fields: set[str] = set()
    name, name_custom = account.display_name, account.name_custom
    if not isinstance(patch.display_name, _Keep):
        fields.add("name")
        raw = patch.display_name
        # Measured after cleaning: stray spaces or bidi marks don't make a name too long.
        if (
            raw is not None
            and len(_WHITESPACE.sub(" ", _BIDI_CONTROLS.sub("", raw)).strip()) > DISPLAY_NAME_MAX
        ):
            raise InvalidDisplayName("too long")
        chosen = normalize_display_name(raw)
        if chosen is None:  # blank or null: back to the Telegram name
            name, name_custom = normalize_display_name(client.display_name), False
        else:
            name, name_custom = chosen, True
    locale, locale_custom = account.locale, account.locale_custom
    if not isinstance(patch.locale, _Keep):
        fields.add("locale")
        if patch.locale is None:
            locale, locale_custom = negotiate_locale(client.language_code), False
        else:
            locale, locale_custom = patch.locale, True
    zone = account.timezone
    if not isinstance(patch.timezone, _Keep):
        fields.add("timezone")
        zone = parse_timezone(patch.timezone)
    home = account.home_city
    if isinstance(patch.home_city, _Keep | _NotNow):
        if isinstance(patch.home_city, _NotNow) and home is None:
            fields.add("home_city")
            home = NOT_LISTED
        if "timezone" in fields:
            # Written with every zone, so a stale read can't leave a city in another zone.
            fields.add("home_city")
            if home not in (None, NOT_LISTED):
                city = cities.find(home)  # a removed city is normalised here too
                if city is None or city.location.tz != zone:
                    home = NOT_LISTED  # travel, UTC, a location: the city no longer holds
    elif patch.home_city is None:
        fields.add("home_city")
        home = NOT_LISTED
    else:
        city = cities.find(patch.home_city)
        if city is None:
            raise UnknownCity(patch.home_city[:80])
        if "timezone" in fields and zone != city.location.tz:
            raise InvalidTimezone(f"{zone} is not the zone of {city.slug}")
        fields |= {"home_city", "timezone"}
        home, zone = city.slug, city.location.tz
    hide_ladies = account.hide_ladies
    if not isinstance(patch.hide_ladies, _Keep):
        fields.add("hide_ladies")
        hide_ladies = bool(patch.hide_ladies)
    offer_check_in = account.offer_check_in
    if not isinstance(patch.offer_check_in, _Keep):
        fields.add("offer_check_in")
        offer_check_in = patch.offer_check_in is not False
    return ProfileChange(
        name,
        name_custom,
        locale,
        locale_custom,
        zone,
        frozenset(fields),
        hide_ladies,
        offer_check_in,
        home,
    )


def home_city_of(account: Account, cities: Cities) -> City | None:
    """The person's listed city while it still names their zone (time labels, MD-04)."""
    return label_city(cities.find(account.home_city), account.timezone)


def normalize_display_name(raw: str | None) -> str | None:
    """Printable, single-spaced, at most 64 characters; blank becomes None."""
    if raw is None:
        return None
    text = _BIDI_CONTROLS.sub("", raw)
    text = "".join(" " if unicodedata.category(ch) == "Cc" else ch for ch in text)
    text = _WHITESPACE.sub(" ", text).strip()[:DISPLAY_NAME_MAX].rstrip()
    return text or None


def new_account(profile: ExternalProfile) -> NewAccount:
    return NewAccount(
        display_name=normalize_display_name(profile.display_name),
        locale=negotiate_locale(profile.language_code),
    )


def profile_refresh(
    account: Account, profile: ExternalProfile, now: datetime
) -> ProfileUpdate | None:
    """The write needed on this contact, or None (the common case: no write at all).

    Name and locale follow the client until the person picks them in settings (ID-06).
    """
    fresh = new_account(profile)
    name = account.display_name if account.name_custom else fresh.display_name
    locale = account.locale if account.locale_custom else fresh.locale
    changed = (name, locale) != (account.display_name, account.locale)
    if changed or now - account.last_seen_at >= LAST_SEEN_PRECISION:
        return ProfileUpdate(display_name=name, locale=locale)
    return None


def parse_timezone(name: str) -> str:
    """An IANA zone name tied to a place (`Asia/Almaty`) or `UTC`.

    Fixed offsets (`Etc/GMT+5`, `EST`, `+05:00`) are rejected: they ignore daylight saving
    and politics, so practice days would drift (ADR-0005).
    """
    if name in _UTC_NAMES:
        return "UTC"
    if "/" in name and not name.startswith("Etc/") and name in _zones():
        return name
    raise InvalidTimezone(name[:80])


def device_timezone(name: str) -> str | None:
    """The zone a device reports, or None when it says nothing about where the person is.

    `UTC` is what misconfigured desktops, emulators and privacy-hardened browsers report;
    stored silently, it would put an Almaty practice near midnight on the wrong date. UTC is
    only ever an explicit choice (ID-06).
    """
    zone = parse_timezone(name)
    return None if zone == "UTC" else zone


@cache
def _zones() -> frozenset[str]:
    return frozenset(available_timezones())
