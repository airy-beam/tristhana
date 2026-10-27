"""Callback data for the check-in screens (PR-06), versioned `k1:`; dates and values absolute.

    k1:o:20261018              check-in screen K         k1:v:20261018     done → V
    k1:g:20261018              tags screen T             k1:x:20261018     remove → V
    k1:m:20261018:4            mood 4 (0 = clear)        k1:e:… / k1:f:…   energy / effort
    k1:t:20261018:s:1          tag by code on (0 off)

Tag codes are an adapter table (like the practice contexts); the domain keys stay words.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

from tristhana.domain.check_in import SCALE, CheckInTag
from tristhana.domain.days import MIN_LOG_DATE

PREFIX = "k1"
type Action = Literal["open", "done", "tags", "clear", "mood", "energy", "effort", "tag"]

_SIMPLE: dict[str, Action] = {"o": "open", "v": "done", "g": "tags", "x": "clear"}
_SCALES: dict[str, Action] = {"m": "mood", "e": "energy", "f": "effort"}
_LETTER = {a: k for k, a in (_SIMPLE | _SCALES).items()} | {"tag": "t"}
TAG_CODES: dict[str, CheckInTag] = {
    "s": CheckInTag.STIFF,
    "o": CheckInTag.OPEN,
    "g": CheckInTag.STRONG,
    "l": CheckInTag.LIGHT,
    "h": CheckInTag.HEAVY,
    "r": CheckInTag.SORE,
    "f": CheckInTag.FOCUSED,
    "c": CheckInTag.CALM,
    "d": CheckInTag.SCATTERED,
    "b": CheckInTag.STEADY_BREATH,
}
_TAG_LETTERS = {t: k for k, t in TAG_CODES.items()}
_VALUES = frozenset({"0", *(str(n) for n in SCALE)})  # 0 = clear
_LATEST = date.max - timedelta(days=31)


@dataclass(frozen=True, slots=True)
class CheckInCallback:
    action: Action
    day: date
    value: int = 0  # a scale value; 0 = clear it
    tag: CheckInTag | None = None
    on: bool = False


def encode(cb: CheckInCallback) -> str:
    base = f"{PREFIX}:{_LETTER[cb.action]}:{cb.day:%Y%m%d}"
    match cb.action:
        case "mood" | "energy" | "effort":
            return f"{base}:{cb.value}"
        case "tag":
            assert cb.tag is not None  # noqa: S101
            return f"{base}:{_TAG_LETTERS[cb.tag]}:{int(cb.on)}"
        case _:
            return base


def decode(data: str | None) -> CheckInCallback | None:
    """None for anything malformed (old or forged keyboards stay harmless)."""
    parts = (data or "").split(":")
    if len(parts) < 3 or parts[0] != PREFIX:
        return None
    try:
        day = datetime.strptime(parts[2], "%Y%m%d").date()
    except ValueError:
        return None
    if not MIN_LOG_DATE <= day <= _LATEST:
        return None
    letter, rest = parts[1], parts[3:]
    if letter in _SIMPLE and not rest:
        return CheckInCallback(_SIMPLE[letter], day)
    match letter, rest:
        case _, [n] if letter in _SCALES and n in _VALUES:
            return CheckInCallback(_SCALES[letter], day, value=int(n))
        case "t", [code, "0" | "1" as on] if code in TAG_CODES:
            return CheckInCallback("tag", day, tag=TAG_CODES[code], on=on == "1")
        case _:
            return None
