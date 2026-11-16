"""Stateless callback data for the simple journey (UI-06, ADR-0008), versioned `w1:`.

w1:m        the Menu (the last row of every top-level screen)
w1:n        Today; relative on purpose ("today" whenever tapped), and it writes nothing
w1:h        Help
w1:o        "For teachers and shalas"
w1:f        the front door again (Back from "Shala and classes")
w1:p        front door: "My practice" (Today)
w1:t        front door: "Invite students" (the first-run invite screen)
w1:c        the teacher's closing screen (after the invite)
w1:s:f      "Shala and classes"; the letter is where Back goes: `f` the front door,
            `o` "For teachers and shalas", `c` the teacher's closing screen
w1:l:ru     the front door in that language
"""

from dataclasses import dataclass
from typing import Literal, get_args

from tristhana.domain.locale import LOCALES, Locale

PREFIX = "w1"
type Action = Literal[
    "menu", "today", "help", "teach", "front", "practice", "invite", "closing", "shala", "language"
]
type ShalaBack = Literal["f", "o", "c"]

_PLAIN: dict[str, Action] = {
    "m": "menu",
    "n": "today",
    "h": "help",
    "o": "teach",
    "f": "front",
    "p": "practice",
    "t": "invite",
    "c": "closing",
}
_BACKS: tuple[str, ...] = get_args(ShalaBack.__value__)

MENU = f"{PREFIX}:m"
TODAY = f"{PREFIX}:n"
HELP = f"{PREFIX}:h"
TEACH = f"{PREFIX}:o"
FRONT = f"{PREFIX}:f"
PRACTICE = f"{PREFIX}:p"
INVITE = f"{PREFIX}:t"
CLOSING = f"{PREFIX}:c"


@dataclass(frozen=True, slots=True)
class HomeTap:
    action: Action
    back: ShalaBack | None = None  # only for "shala"
    locale: Locale | None = None  # only for "language"


def shala(back: ShalaBack) -> str:
    return f"{PREFIX}:s:{back}"


def language(locale: Locale) -> str:
    return f"{PREFIX}:l:{locale}"


def decode(data: str | None) -> HomeTap | None:
    """None for anything malformed, forged or from another version."""
    parts = (data or "").split(":")
    if len(parts) < 2 or parts[0] != PREFIX:
        return None
    if len(parts) == 2 and parts[1] in _PLAIN:
        return HomeTap(_PLAIN[parts[1]])
    if len(parts) != 3:
        return None
    if parts[1] == "s" and parts[2] in _BACKS:
        return HomeTap("shala", back=parts[2])  # type: ignore[arg-type]
    if parts[1] == "l" and parts[2] in LOCALES:
        return HomeTap("language", locale=parts[2])  # type: ignore[arg-type]
    return None
