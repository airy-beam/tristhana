"""Callback data for the settings screens (ID-06, UI-06), versioned `s1:`. Values are absolute.

s1:v            /settings: five rows, each label carrying its value
s1:lp           the language picker
s1:r            Reminders: the practice reminder, moon reminders, the quiet hours
s1:m            More: moon city, the 🌸 and "How do you feel?" switches, My data, the app
s1:l:a          language: as in Telegram (s1:l:en / s1:l:ru = chosen)
s1:cp:2         "My city" picker, page 2 (MD-04; old s1:zp:2 still decodes)
s1:c:<slug>     my city = that city, and its zone (old s1:z:<slug> still decodes)
s1:c:-          my city isn't listed → a location prompt (new message)
s1:u            time zone = UTC (no city)
s1:n            "Not now" on the city nudge, retired with UI-06: only on old messages
                (no city, nudge answered) → /settings
s1:o            day off picker (PR-09)
s1:o:67         days off = Saturday + Sunday (ISO digits, at most two; 0 = none) → picker
s1:h:1 / s1:h:0 hide / show the 🌸 button (WH-01) → More
s1:k:1 / s1:k:0 show / hide the "How do you feel?" button (PR-06, UI-06 Q313) → More
"""

import re
from dataclasses import dataclass
from typing import Literal

from tristhana.bots.telegram.remind_callbacks import days_off_code, parse_days_off
from tristhana.domain.locale import LOCALES, Locale

PREFIX = "s1"
type Action = Literal[
    "view",
    "language_pick",
    "reminders",
    "more",
    "language",
    "cities",
    "city",
    "unlisted",
    "utc",
    "not_now",
    "day_off_pick",
    "day_off",
    "hide_ladies",
    "offer_check_in",
]

_SLUG = re.compile(r"[a-z-]{1,24}")


@dataclass(frozen=True, slots=True)
class SettingsCallback:
    action: Action
    locale: Locale | None = None  # None = as in Telegram
    page: int = 0
    slug: str | None = None
    days_off: frozenset[int] = frozenset()  # empty = no fixed day off
    hide: bool = False  # hide_ladies
    offer: bool = False  # offer_check_in


def encode(cb: SettingsCallback) -> str:
    match cb.action:
        case "view":
            return f"{PREFIX}:v"
        case "language_pick":
            return f"{PREFIX}:lp"
        case "reminders":
            return f"{PREFIX}:r"
        case "more":
            return f"{PREFIX}:m"
        case "language":
            return f"{PREFIX}:l:{cb.locale or 'a'}"
        case "cities":
            return f"{PREFIX}:cp:{cb.page}"
        case "city":
            return f"{PREFIX}:c:{cb.slug}"
        case "unlisted":
            return f"{PREFIX}:c:-"
        case "utc":
            return f"{PREFIX}:u"
        case "not_now":
            return f"{PREFIX}:n"
        case "day_off_pick":
            return f"{PREFIX}:o"
        case "day_off":
            return f"{PREFIX}:o:{days_off_code(cb.days_off)}"
        case "hide_ladies":
            return f"{PREFIX}:h:{int(cb.hide)}"
        case "offer_check_in":
            return f"{PREFIX}:k:{int(cb.offer)}"


def decode(data: str | None) -> SettingsCallback | None:
    """None for anything malformed or forged."""
    parts = (data or "").split(":")
    if len(parts) < 2 or parts[0] != PREFIX:
        return None
    match parts[1:]:
        case ["v"]:
            return SettingsCallback("view")
        case ["lp"]:
            return SettingsCallback("language_pick")
        case ["r"]:
            return SettingsCallback("reminders")
        case ["m"]:
            return SettingsCallback("more")
        case ["l", "a"]:
            return SettingsCallback("language")
        case ["l", code] if code in LOCALES:
            return SettingsCallback("language", locale=code)  # type: ignore[arg-type]
        case ["cp" | "zp", page] if page.isdigit() and int(page) < 20:
            return SettingsCallback("cities", page=int(page))
        case ["c", "-"]:
            return SettingsCallback("unlisted")
        case ["c" | "z", slug] if _SLUG.fullmatch(slug):
            return SettingsCallback("city", slug=slug)
        case ["u"]:
            return SettingsCallback("utc")
        case ["n"]:
            return SettingsCallback("not_now")
        case ["o"]:
            return SettingsCallback("day_off_pick")
        case ["o", code] if (days := parse_days_off(code)) is not None:
            return SettingsCallback("day_off", days_off=days)
        case ["h", "0" | "1" as flag]:
            return SettingsCallback("hide_ladies", hide=flag == "1")
        case ["k", "0" | "1" as flag]:
            return SettingsCallback("offer_check_in", offer=flag == "1")
        case _:
            return None
