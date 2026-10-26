"""Callback data for rest periods (WH-01 part 2, ADR-0023), versioned `a1:`. Stateless,
absolute values, at most 34 bytes. Kind codes are PR-01's (`l` 🌸, `k` 🤒, `t` ✈️).

    a1:p:20261026:l:5            start a period on that day for 5 days (in the kind's set)
    a1:m:20261026:l:1            the "Other…" day counts (last digit: reminders on); no DB
    a1:b:20261026:l:1            back to the first day counts; no DB
    a1:k:20261024:20261028:l:20261026
                                 keep the pause: restore that period exactly (the last
                                 date: the 🧘 day that cut it, whose details come back)
    a1:e:20261024:1              end early (period start; last digit: reminders on)
    a1:er:20261024               end early from /remind → /remind
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

from tristhana.bots.telegram.callbacks import STATUS_CODES
from tristhana.domain.days import MIN_LOG_DATE, DayStatus
from tristhana.domain.rest_periods import PAUSABLE, allowed_days, max_days

PREFIX = "a1"
type Action = Literal["start", "more", "back", "keep", "end", "end_remind"]

_CODES = {s: c for s, c in STATUS_CODES.items() if s in PAUSABLE}
_KINDS = {c: s for s, c in _CODES.items()}
_LETTERS: dict[Action, str] = {
    "start": "p",
    "more": "m",
    "back": "b",
    "keep": "k",
    "end": "e",
    "end_remind": "er",
}
_LATEST = date(9000, 1, 1)


@dataclass(frozen=True, slots=True)
class RestCallback:
    action: Action
    day: date  # the period's start (the origin day for start / more / back)
    kind: DayStatus | None = None  # start, more, back, keep
    days: int = 0  # start
    end: date | None = None  # keep
    reminders_on: bool = False  # more, back, end
    practiced: date | None = None  # keep: the 🧘 day that cut it


def _ymd(day: date) -> str:
    return day.strftime("%Y%m%d")


def encode(cb: RestCallback) -> str:
    head = f"{PREFIX}:{_LETTERS[cb.action]}:{_ymd(cb.day)}"
    match cb.action:
        case "start":
            assert cb.kind is not None  # noqa: S101
            return f"{head}:{_CODES[cb.kind]}:{cb.days}"
        case "more" | "back":
            assert cb.kind is not None  # noqa: S101
            return f"{head}:{_CODES[cb.kind]}:{int(cb.reminders_on)}"
        case "keep":
            assert cb.kind is not None  # noqa: S101
            assert cb.end is not None  # noqa: S101
            assert cb.practiced is not None  # noqa: S101
            return f"{head}:{_ymd(cb.end)}:{_CODES[cb.kind]}:{_ymd(cb.practiced)}"
        case "end":
            return f"{head}:{int(cb.reminders_on)}"
        case "end_remind":
            return head


def _date(ymd: str) -> date | None:
    if len(ymd) != 8 or not ymd.isdigit():
        return None
    try:
        day = datetime.strptime(ymd, "%Y%m%d").date()
    except ValueError:
        return None
    return day if MIN_LOG_DATE <= day <= _LATEST else None


def decode(data: str | None) -> RestCallback | None:
    """None for anything malformed or forged, including a day count outside the kind's
    set and a kept period longer than the kind allows."""
    parts = (data or "").split(":")
    if len(parts) < 3 or parts[0] != PREFIX or (day := _date(parts[2])) is None:
        return None
    match parts[1], parts[3:]:
        case "p", [code, n] if code in _KINDS and n.isdigit():
            kind = _KINDS[code]
            if int(n) not in allowed_days(kind) or n != str(int(n)):
                return None
            return RestCallback("start", day, kind, days=int(n))
        case "m" | "b" as letter, [code, "0" | "1" as flag] if code in _KINDS:
            action: Action = "more" if letter == "m" else "back"
            return RestCallback(action, day, _KINDS[code], reminders_on=flag == "1")
        case "k", [ymd, code, d] if (
            code in _KINDS and (end := _date(ymd)) is not None and (on := _date(d)) is not None
        ):
            kind = _KINDS[code]
            if not day < end <= day + timedelta(days=max_days(kind) - 1) or not day <= on < end:
                return None
            return RestCallback("keep", day, kind, end=end, practiced=on)
        case "e", ["0" | "1" as flag]:
            return RestCallback("end", day, reminders_on=flag == "1")
        case "er", []:
            return RestCallback("end_remind", day)
        case _:
            return None
