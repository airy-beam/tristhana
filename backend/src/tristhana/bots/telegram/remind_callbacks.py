"""Callback data for the practice reminder (PR-10), versioned `r1:`. Values are absolute
(the weekdays to set, not "toggle"), so stale keyboards stay harmless.

    r1:v                 /remind screen
    r1:o:1 / r1:o:0      turn on / off
    r1:t:1000            send time 10:00
    r1:w:123457          weekdays (ISO digits; at least one)
    r1:y:20261019        the offer under "practice saved": yes (date = the day shown)
    r1:n:20261019        the offer: no, thanks
    r1:s:20261019        from a reminder: practiced, same as last time
    r1:q:20261019:0      from a reminder: turn off (1 = turn back on)
"""

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Literal

from tristhana.domain.days import MIN_LOG_DATE
from tristhana.domain.notifications import WEEKDAYS

PREFIX = "r1"
type Action = Literal["view", "switch", "time", "days", "yes", "no", "same", "quick"]

_DATED: dict[str, Action] = {"y": "yes", "n": "no", "s": "same"}
_DATED_CODES = {v: k for k, v in _DATED.items()}


@dataclass(frozen=True, slots=True)
class RemindCallback:
    action: Action
    on: bool = False
    at: time | None = None
    days: frozenset[int] | None = None
    day: date | None = None


def days_code(days: frozenset[int]) -> str:
    return "".join(str(d) for d in sorted(days))


def encode(cb: RemindCallback) -> str:
    match cb.action:
        case "view":
            return f"{PREFIX}:v"
        case "switch":
            return f"{PREFIX}:o:{int(cb.on)}"
        case "time":
            assert cb.at is not None  # noqa: S101
            return f"{PREFIX}:t:{cb.at:%H%M}"
        case "days":
            assert cb.days  # noqa: S101
            return f"{PREFIX}:w:{days_code(cb.days)}"
        case "quick":
            assert cb.day is not None  # noqa: S101
            return f"{PREFIX}:q:{cb.day:%Y%m%d}:{int(cb.on)}"
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
        case ["w", code] if (
            code.isdigit() and len(set(code)) == len(code) and {int(c) for c in code} <= WEEKDAYS
        ):
            return RemindCallback("days", days=frozenset(int(c) for c in code))
        case ["y" | "n" | "s" as kind, ymd] if (day := _date(ymd)) is not None:
            return RemindCallback(_DATED[kind], day=day)
        case ["q", ymd, "0" | "1" as flag] if (day := _date(ymd)) is not None:
            return RemindCallback("quick", on=flag == "1", day=day)
        case _:
            return None
