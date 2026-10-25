"""Callback data for the settings screen (ID-06), versioned `s1:`. Values are absolute.

s1:v            /settings screen
s1:l:a          language: as in Telegram (s1:l:en / s1:l:ru = chosen)
s1:zp:2         time zone city picker, page 2
s1:z:<slug>     time zone = that city's zone
s1:o            day off picker (PR-09)
s1:o:67         days off = Saturday + Sunday (ISO digits, at most two; 0 = none) → picker
"""

import re
from dataclasses import dataclass
from typing import Literal

from tristhana.bots.telegram.remind_callbacks import days_off_code, parse_days_off
from tristhana.domain.locale import LOCALES, Locale

PREFIX = "s1"
type Action = Literal["view", "language", "zones", "zone", "day_off_pick", "day_off"]

_SLUG = re.compile(r"[a-z-]{1,24}")


@dataclass(frozen=True, slots=True)
class SettingsCallback:
    action: Action
    locale: Locale | None = None  # None = as in Telegram
    page: int = 0
    slug: str | None = None
    days_off: frozenset[int] = frozenset()  # empty = no fixed day off


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
            return f"{PREFIX}:o:{days_off_code(cb.days_off)}"


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
        case ["o", code] if (days := parse_days_off(code)) is not None:
            return SettingsCallback("day_off", days_off=days)
        case _:
            return None
