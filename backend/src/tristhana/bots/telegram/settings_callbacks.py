"""Callback data for the settings screen (ID-06), versioned `s1:`. Values are absolute.

s1:v            /settings screen
s1:l:a          language: as in Telegram (s1:l:en / s1:l:ru = chosen)
s1:zp:2         time zone city picker, page 2
s1:z:<slug>     time zone = that city's zone
s1:o            day off picker (PR-09)
s1:o:6          day off = Saturday (ISO digit; 0 = no fixed day off)
"""

import re
from dataclasses import dataclass
from typing import Literal

from tristhana.domain.locale import LOCALES, Locale

PREFIX = "s1"
type Action = Literal["view", "language", "zones", "zone", "day_off_pick", "day_off"]

_SLUG = re.compile(r"[a-z-]{1,24}")
_DAY_OFF_DIGITS = frozenset("01234567")


@dataclass(frozen=True, slots=True)
class SettingsCallback:
    action: Action
    locale: Locale | None = None  # None = as in Telegram
    page: int = 0
    slug: str | None = None
    weekday: int = 0  # the day off; 0 = no fixed day off


def encode(cb: SettingsCallback) -> str:
    match cb.action:
        case "view":
            return f"{PREFIX}:v"
        case "language":
            return f"{PREFIX}:l:{cb.locale or 'a'}"
        case "zones":
            return f"{PREFIX}:zp:{cb.page}"
        case "zone":
            return f"{PREFIX}:z:{cb.slug}"
        case "day_off_pick":
            return f"{PREFIX}:o"
        case "day_off":
            return f"{PREFIX}:o:{cb.weekday}"


def decode(data: str | None) -> SettingsCallback | None:
    """None for anything malformed or forged."""
    parts = (data or "").split(":")
    if len(parts) < 2 or parts[0] != PREFIX:
        return None
    match parts[1:]:
        case ["v"]:
            return SettingsCallback("view")
        case ["l", "a"]:
            return SettingsCallback("language")
        case ["l", code] if code in LOCALES:
            return SettingsCallback("language", locale=code)  # type: ignore[arg-type]
        case ["zp", page] if page.isdigit() and int(page) < 20:
            return SettingsCallback("zones", page=int(page))
        case ["z", slug] if _SLUG.fullmatch(slug):
            return SettingsCallback("zone", slug=slug)
        case ["o"]:
            return SettingsCallback("day_off_pick")
        case ["o", d] if d in _DAY_OFF_DIGITS:  # one digit: longer codes stay free (2 days)
            return SettingsCallback("day_off", weekday=int(d))
        case _:
            return None
