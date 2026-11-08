"""Stateless callback data for shala classes (SC-02, ADR-0008), versioned `c1:`. Ids are SC-01's
22-character base64url uuids, dates `yyyymmdd`; an id here is no capability: every write checks
the caller's membership. The longest datum is 59 bytes.

c1:w:<s>:<week>          the schedule, week 0-3 from the shala's today
c1:p:<s>                 staff: pick an occurrence of the next 48 h
c1:o|x|r|h:<s>:<c>:<d>   occurrence card · cancel (after the ask) · restore · hold anyway
c1:d:<s>                 make the shala's day off mine (Q109, Q119)
c1:m:<week>:<a|t|m>      My schedule (SC-03): week 0-3 from my today, filter all/teachers/mine
c1:f:<a>                 my calendar link (SC-06): s show · n create · r/R rotate ask/confirm ·
                         x/X turn off ask/confirm
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from tristhana.bots.telegram.shalas_callbacks import parse_short_id, short_id

PREFIX = "c1"
WEEKS = 4
type OnOccurrence = Literal["o", "x", "r", "h"]
_ON_OCCURRENCE = ("o", "x", "r", "h")
_WEEK_NAMES = frozenset(str(n) for n in range(WEEKS))


@dataclass(frozen=True, slots=True)
class Week:
    shala: UUID
    week: int


@dataclass(frozen=True, slots=True)
class Pick:
    shala: UUID


@dataclass(frozen=True, slots=True)
class Occurrence:
    action: OnOccurrence
    shala: UUID
    class_id: UUID
    key: date


@dataclass(frozen=True, slots=True)
class AdoptDayOff:
    shala: UUID


type Filter = Literal["a", "t", "m"]
FILTERS: tuple[Filter, ...] = ("a", "t", "m")


@dataclass(frozen=True, slots=True)
class MyWeek:
    week: int
    only: Filter


type FeedAction = Literal["s", "n", "r", "R", "x", "X"]
_FEED_ACTIONS = ("s", "n", "r", "R", "x", "X")


@dataclass(frozen=True, slots=True)
class Feed:
    action: FeedAction


type ClassTap = Week | Pick | Occurrence | AdoptDayOff | MyWeek | Feed


def week(shala: UUID, n: int) -> str:
    return f"{PREFIX}:w:{short_id(shala)}:{n}"


def pick(shala: UUID) -> str:
    return f"{PREFIX}:p:{short_id(shala)}"


def occurrence(action: OnOccurrence, shala: UUID, class_id: UUID, key: date) -> str:
    return f"{PREFIX}:{action}:{short_id(shala)}:{short_id(class_id)}:{key:%Y%m%d}"


def my_week(n: int, only: Filter) -> str:
    return f"{PREFIX}:m:{n}:{only}"


def feed(action: FeedAction) -> str:
    return f"{PREFIX}:f:{action}"


def adopt_day_off(shala: UUID) -> str:
    return f"{PREFIX}:d:{short_id(shala)}"


def _date(value: str) -> date | None:
    if len(value) != 8 or not value.isdigit():
        return None
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return None


def decode(data: str | None) -> ClassTap | None:
    parts = (data or "").split(":")
    if len(parts) < 3 or parts[0] != PREFIX:
        return None
    if parts[1] == "f":
        if len(parts) == 3 and parts[2] in _FEED_ACTIONS:
            return Feed(parts[2])  # type: ignore[arg-type]
        return None
    if parts[1] == "m":
        if len(parts) == 4 and parts[2] in _WEEK_NAMES and parts[3] in FILTERS:
            return MyWeek(int(parts[2]), parts[3])  # type: ignore[arg-type]
        return None
    kind, shala = parts[1], parse_short_id(parts[2])
    if shala is None:
        return None
    rest = parts[3:]
    if kind == "w" and len(rest) == 1 and rest[0] in _WEEK_NAMES:
        return Week(shala, int(rest[0]))
    if kind == "p" and not rest:
        return Pick(shala)
    if kind == "d" and not rest:
        return AdoptDayOff(shala)
    if kind in _ON_OCCURRENCE and len(rest) == 2:
        class_id, key = parse_short_id(rest[0]), _date(rest[1])
        if class_id is not None and key is not None:
            return Occurrence(kind, shala, class_id, key)  # type: ignore[arg-type]
    return None
