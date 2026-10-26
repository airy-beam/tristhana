"""Stateless callback data for the day-status screens (ADR-0008), versioned `d1:`.

Dates are absolute, so a keyboard tapped tomorrow still acts on the day it shows. Only the
legacy `d1:t` is relative: the "Log today" button under /start greetings sent before UI-01
(still in chat history; its tap opens a new message), so it means "today" whenever tapped.

    d1:t                today's status screen
    d1:o:20261018       status screen for a date
    d1:s:20261018:p     set a status (codes below)
    d1:x:20261018       clear the status
    d1:w:20261018       week picker ending on that date
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

from tristhana.domain.days import MIN_LOG_DATE, DayStatus

PREFIX = "d1"
type Action = Literal["today", "open", "set", "clear", "week"]

_CODES: dict[DayStatus, str] = {
    DayStatus.PRACTICED: "p",
    DayStatus.REST: "r",
    DayStatus.MOON: "m",
    DayStatus.LADIES: "l",
    DayStatus.SICK: "k",
    DayStatus.TRAVEL: "t",
    DayStatus.SKIPPED: "s",
}
STATUS_CODES = _CODES  # shared with `rest_callbacks` (a1:)
_STATUSES = {code: status for status, code in _CODES.items()}
_ACTIONS: dict[str, Action] = {"o": "open", "x": "clear", "w": "week"}
_LETTERS = {action: letter for letter, action in _ACTIONS.items()}
# Forged or ancient dates are dropped here, so date arithmetic downstream can't overflow.
_LATEST = date.max - timedelta(days=31)


@dataclass(frozen=True, slots=True)
class DayCallback:
    action: Action
    day: date | None = None  # None only for "today"
    status: DayStatus | None = None  # only for "set"


def encode(cb: DayCallback) -> str:
    if cb.action == "today":
        return f"{PREFIX}:t"
    if cb.day is None:
        raise ValueError(f"{cb.action} needs a date")
    day = cb.day.strftime("%Y%m%d")
    if cb.action == "set":
        if cb.status is None:
            raise ValueError("set needs a status")
        return f"{PREFIX}:s:{day}:{_CODES[cb.status]}"
    return f"{PREFIX}:{_LETTERS[cb.action]}:{day}"


def decode(data: str | None) -> DayCallback | None:
    """None for anything malformed or from another version (old keyboards stay harmless)."""
    parts = (data or "").split(":")
    if len(parts) < 2 or parts[0] != PREFIX:
        return None
    if parts[1:] == ["t"]:
        return DayCallback("today")
    try:
        day = datetime.strptime(parts[2], "%Y%m%d").date() if len(parts) > 2 else None
    except ValueError:
        return None
    if day is None or not MIN_LOG_DATE <= day <= _LATEST:
        return None
    if parts[1] == "s" and len(parts) == 4 and parts[3] in _STATUSES:
        return DayCallback("set", day, _STATUSES[parts[3]])
    if parts[1] in _ACTIONS and len(parts) == 3:
        return DayCallback(_ACTIONS[parts[1]], day)
    return None
