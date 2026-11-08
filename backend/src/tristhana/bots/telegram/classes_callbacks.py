"""Stateless callback data for shala classes (SC-02, ADR-0008), versioned `c1:`. Ids are SC-01's
22-character base64url uuids, dates `yyyymmdd`; an id here is no capability: every write checks
the caller's membership. The longest datum is 59 bytes.

c1:w:<s>:<week>          the schedule, week 0-3 from the shala's today
c1:p:<s>                 staff: pick an occurrence of the next 48 h
c1:o|x|r|h:<s>:<c>:<d>   occurrence card · cancel (after the ask) · restore · hold anyway
c1:d:<s>                 make the shala's day off mine (Q109, Q119)
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


type ClassTap = Week | Pick | Occurrence | AdoptDayOff


def week(shala: UUID, n: int) -> str:
    return f"{PREFIX}:w:{short_id(shala)}:{n}"


def pick(shala: UUID) -> str:
    return f"{PREFIX}:p:{short_id(shala)}"


def occurrence(action: OnOccurrence, shala: UUID, class_id: UUID, key: date) -> str:
    return f"{PREFIX}:{action}:{short_id(shala)}:{short_id(class_id)}:{key:%Y%m%d}"


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
    kind, shala = parts[1], parse_short_id(parts[2])
    if shala is None:
        return None
    rest = parts[3:]
    if kind == "w" and len(rest) == 1 and rest[0] in {str(n) for n in range(WEEKS)}:
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
