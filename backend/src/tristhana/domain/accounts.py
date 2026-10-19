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

DISPLAY_NAME_MAX = 64
# Write `last_seen_at` (and refresh the profile) at most this often when nothing changed.
LAST_SEEN_PRECISION = timedelta(hours=24)

# Bidi controls can reorder the text around a name; zero-width joiners stay (emoji sequences).
_BIDI_CONTROLS = re.compile("[‪-‮⁦-⁩‎‏]")
_WHITESPACE = re.compile(r"\s+")
_UTC_NAMES = frozenset({"UTC", "Etc/UTC"})


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

    The locale follows the client language until the person picks one explicitly (ID-06).
    """
    fresh = new_account(profile)
    changed = (fresh.display_name, fresh.locale) != (account.display_name, account.locale)
    if changed or now - account.last_seen_at >= LAST_SEEN_PRECISION:
        return ProfileUpdate(display_name=fresh.display_name, locale=fresh.locale)
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
