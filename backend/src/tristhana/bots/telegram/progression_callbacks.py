"""Callback data for the progression screens (PR-08), versioned `g1:`; positions are a series
number plus a stop key (natural keys, ADR-0010), dates absolute.

    g1:o                        open G
    g1:g:2:kapotasana-b         new asana given → G (+ `:20261027`: from P → P of that day)
    g1:s:2:laghu-vajrasana      set / change the position → G     g1:s:0:  standing only
    g1:i:drop-backs:1           item given (0: removed) → G
    g1:a:s                      series picker (set)               g1:c   ✏️ Change screen
    g1:p:s:2:1                  stop grid of series 2, page 1 (set)
    g1:p:g:0:1                  later stops, page 1 ("Another new asana…")
    g1:u:1234                   undo event 1234 → G
    g1:n:2:kapotasana-b:20261027  "Not new" → P of that day
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

from tristhana.domain.days import MIN_LOG_DATE
from tristhana.domain.practice import PracticeCatalog
from tristhana.domain.progression import STANDING_ONLY, Position

PREFIX = "g1"
type Action = Literal["open", "give", "set", "item", "series", "change", "grid", "undo", "not_new"]
type Mode = Literal["s", "g"]

_LETTER: dict[Action, str] = {
    "open": "o", "give": "g", "set": "s", "item": "i", "series": "a", "change": "c",
    "grid": "p", "undo": "u", "not_new": "n",
}  # fmt: skip
_ACTIONS = {v: k for k, v in _LETTER.items()}
_LATEST = date.max - timedelta(days=31)
_MAX_KEY = 48


@dataclass(frozen=True, slots=True)
class ProgressionCallback:
    action: Action
    number: int = 0  # series number (0 = standing only / later stops), event id, or flag
    key: str | None = None  # stop key or item key
    day: date | None = None  # from P: the practice day
    mode: Mode = "s"
    page: int = 0


def position(catalog: PracticeCatalog, number: int, key: str | None) -> Position | None:
    """The position a (series number, key) pair names; None when the series is unknown."""
    if number == 0:
        return STANDING_ONLY if not key else None
    series = catalog.by_number(number)
    return Position(series.slug, key) if series and key else None


def encode(cb: ProgressionCallback) -> str:
    base = f"{PREFIX}:{_LETTER[cb.action]}"
    day = f":{cb.day:%Y%m%d}" if cb.day else ""
    match cb.action:
        case "give" | "set" | "not_new":
            return f"{base}:{cb.number}:{cb.key or ''}{day}"
        case "item":
            return f"{base}:{cb.key}:{cb.number}"
        case "series":
            return f"{base}:{cb.mode}"
        case "grid":
            return f"{base}:{cb.mode}:{cb.number}:{cb.page}"
        case "undo":
            return f"{base}:{cb.number}"
        case _:
            return base


def _num(text: str) -> bool:
    """ASCII digits only ("²".isdigit() is True, and int() rejects it)."""
    return text.isascii() and text.isdigit()


def _day(text: str) -> date | None:
    if len(text) != 8 or not _num(text):
        return None
    try:
        day = datetime.strptime(text, "%Y%m%d").date()
    except ValueError:
        return None
    return day if MIN_LOG_DATE <= day <= _LATEST else None


def _key(text: str) -> bool:
    return 0 < len(text) <= _MAX_KEY and all(
        c.isascii() and (c.isalnum() or c == "-") for c in text
    )


def decode(data: str | None) -> ProgressionCallback | None:
    """None for anything malformed (old or forged keyboards stay harmless)."""
    parts = (data or "").split(":")
    if len(parts) < 2 or parts[0] != PREFIX or parts[1] not in _ACTIONS:
        return None
    action, rest = _ACTIONS[parts[1]], parts[2:]
    match action, rest:
        case (("open" | "change"), []):
            return ProgressionCallback(action)
        case (("give" | "set"), [n, key, *tail]) if _num(n) and int(n) <= 6 and len(tail) <= 1:
            if (key and not _key(key)) or (int(n) == 0) != (key == ""):
                return None
            day = _day(tail[0]) if tail else None
            if tail and day is None:
                return None
            return ProgressionCallback(action, int(n), key or None, day)
        case "not_new", [n, key, day_text] if _num(n) and 1 <= int(n) <= 6 and _key(key):
            day = _day(day_text)
            return ProgressionCallback(action, int(n), key, day) if day else None
        case "item", [key, "0" | "1" as flag] if _key(key):
            return ProgressionCallback(action, int(flag), key)
        case "series", ["s" | "g" as mode]:
            return ProgressionCallback(action, mode=mode)
        case "grid", ["s" | "g" as mode, n, page] if _num(n) and int(n) <= 6:
            if not _num(page) or int(page) >= 20:
                return None
            return ProgressionCallback(action, int(n), mode=mode, page=int(page))
        case "undo", [n] if _num(n) and 0 < int(n) < 2**62:
            return ProgressionCallback(action, int(n))
        case _:
            return None
