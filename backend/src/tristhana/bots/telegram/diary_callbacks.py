"""Callback data for the diary-note screens (PR-07), versioned `n1:`; dates absolute.

    n1:o:20261027:d     open the note screen N       (origin: d = day picker, k = check-in K)
    n1:w:20261027:d     send the write prompt        n1:r:…  the same, replacing a note
    n1:y:20261027:d     ask to confirm removal       n1:x:…  remove → N
    n1:b:20261027:d     back to the origin screen

The rewrite flag rides in the data, so the prompt needs no read (stateless, ADR-0008).
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

from tristhana.domain.days import MIN_LOG_DATE

PREFIX = "n1"
type Action = Literal["open", "write", "rewrite", "confirm", "clear", "back"]
type Origin = Literal["d", "k"]

_ACTIONS: dict[str, Action] = {
    "o": "open",
    "w": "write",
    "r": "rewrite",
    "y": "confirm",
    "x": "clear",
    "b": "back",
}
_LETTER = {a: k for k, a in _ACTIONS.items()}
_ORIGINS: frozenset[str] = frozenset({"d", "k"})
_LATEST = date.max - timedelta(days=31)


@dataclass(frozen=True, slots=True)
class DiaryCallback:
    action: Action
    day: date
    origin: Origin = "d"


def encode(cb: DiaryCallback) -> str:
    return f"{PREFIX}:{_LETTER[cb.action]}:{cb.day:%Y%m%d}:{cb.origin}"


def decode(data: str | None) -> DiaryCallback | None:
    """None for anything malformed (old or forged keyboards stay harmless)."""
    parts = (data or "").split(":")
    if len(parts) != 4 or parts[0] != PREFIX or parts[1] not in _ACTIONS:
        return None
    if parts[3] not in _ORIGINS or len(parts[2]) != 8 or not parts[2].isdigit():
        return None
    try:
        day = datetime.strptime(parts[2], "%Y%m%d").date()
    except ValueError:
        return None
    if not MIN_LOG_DATE <= day <= _LATEST:
        return None
    return DiaryCallback(_ACTIONS[parts[1]], day, parts[3])  # type: ignore[arg-type]
