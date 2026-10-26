"""Callback data for the practice reminder (PR-10), versioned `r1:`. Values are absolute
(the weekdays to set, not "toggle"), so stale keyboards stay harmless.

    r1:v                 /remind screen
    r1:o:1 / r1:o:0      turn on / off
    r1:t:1000            send time 10:00
    r1:w:123457          (retired with PR-09: reminder days follow the day off) → /remind
    r1:y:20261019        the offer under "practice saved": yes (date = the day shown)
    r1:n:20261019        the offer: no, thanks
    r1:s:20261019        from a reminder: practiced, same as last time
    r1:p:20261019        from a reminder: 🧘 practiced, insert-if-absent (Q26, WH-01)
    r1:r:20261019        from a reminder: 😌 rest, insert-if-absent (Q26, WH-01)
    r1:q:20261019:0      from a reminder: turn off (1 = turn back on)
    r1:d:6 / r1:d:67     the days off (ISO digits, at most two; 0 = none; PR-09) → /remind
    r1:dp                the day off picker, opened from /remind
    r1:dt:67             set the days off from that picker, and stay in it
    r1:dn                the one-time day-off question: not now
"""

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Literal

from tristhana.domain.days import MIN_LOG_DATE
from tristhana.domain.rest_days import MAX_DAYS_OFF, WEEKDAYS

PREFIX = "r1"
type Action = Literal[
    "view",
    "switch",
    "time",
    "yes",
    "no",
    "same",
    "log_practiced",
    "log_rest",
    "quick",
    "day_off",
    "day_off_pick",
    "day_off_toggle",
    "day_off_later",
]

_DATED: dict[str, Action] = {
    "y": "yes",
    "n": "no",
    "s": "same",
    "p": "log_practiced",
    "r": "log_rest",
}
_DATED_CODES = {v: k for k, v in _DATED.items()}


@dataclass(frozen=True, slots=True)
class RemindCallback:
    action: Action
    on: bool = False
    at: time | None = None
    day: date | None = None
    days_off: frozenset[int] = frozenset()  # empty = no fixed day off


def days_off_code(days: frozenset[int]) -> str:
    """ISO digits, "0" for no fixed day off (shared with `s1:o:`)."""
    return "".join(str(d) for d in sorted(days)) or "0"


def parse_days_off(code: str) -> frozenset[int] | None:
    """None for anything but "0" or 1-2 distinct weekday digits."""
    if code == "0":
        return frozenset()
    if not code.isdigit() or len(set(code)) != len(code) or len(code) > MAX_DAYS_OFF:
        return None
    days = frozenset(int(c) for c in code)
    return days if days <= WEEKDAYS else None


def encode(cb: RemindCallback) -> str:
    match cb.action:
        case "view":
            return f"{PREFIX}:v"
        case "switch":
            return f"{PREFIX}:o:{int(cb.on)}"
        case "time":
            assert cb.at is not None  # noqa: S101
            return f"{PREFIX}:t:{cb.at:%H%M}"
        case "quick":
            assert cb.day is not None  # noqa: S101
            return f"{PREFIX}:q:{cb.day:%Y%m%d}:{int(cb.on)}"
        case "day_off":
            return f"{PREFIX}:d:{days_off_code(cb.days_off)}"
        case "day_off_toggle":
            return f"{PREFIX}:dt:{days_off_code(cb.days_off)}"
        case "day_off_pick":
            return f"{PREFIX}:dp"
        case "day_off_later":
            return f"{PREFIX}:dn"
        case _:
            assert cb.day is not None  # noqa: S101
            return f"{PREFIX}:{_DATED_CODES[cb.action]}:{cb.day:%Y%m%d}"


def _date(ymd: str) -> date | None:
    try:
        day = datetime.strptime(ymd, "%Y%m%d").date()
    except ValueError:
        return None
    return day if MIN_LOG_DATE <= day <= date(9000, 1, 1) else None


def decode(data: str | None) -> RemindCallback | None:
    """None for anything malformed or forged."""
    parts = (data or "").split(":")
    if len(parts) < 2 or parts[0] != PREFIX:
        return None
    match parts[1:]:
        case ["v"]:
            return RemindCallback("view")
        case ["o", "0" | "1" as flag]:
            return RemindCallback("switch", on=flag == "1")
        case ["t", hhmm] if len(hhmm) == 4 and hhmm.isdigit():
            try:
                return RemindCallback("time", at=datetime.strptime(hhmm, "%H%M").time())
            except ValueError:
                return None
        case ["w", _]:  # an old keyboard: reminder days aren't chosen any more
            return RemindCallback("view")
        case ["y" | "n" | "s" | "p" | "r" as kind, ymd] if (day := _date(ymd)) is not None:
            return RemindCallback(_DATED[kind], day=day)
        case ["q", ymd, "0" | "1" as flag] if (day := _date(ymd)) is not None:
            return RemindCallback("quick", on=flag == "1", day=day)
        case ["d", code] if (days := parse_days_off(code)) is not None:
            return RemindCallback("day_off", days_off=days)
        case ["dt", code] if (days := parse_days_off(code)) is not None:
            return RemindCallback("day_off_toggle", days_off=days)
        case ["dp"]:
            return RemindCallback("day_off_pick")
        case ["dn"]:
            return RemindCallback("day_off_later")
        case _:
            return None
