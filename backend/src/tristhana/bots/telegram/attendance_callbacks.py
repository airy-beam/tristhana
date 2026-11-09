"""Stateless callback data for class attendance (SC-05, ADR-0008), versioned `v1:`. Ids are
SC-01's 22-character base64url uuids, dates `yyyymmdd` (the rule date); an id here is no
capability: every tap re-checks the caller's membership. Each toggle carries its target state,
so a retry is idempotent. The longest datum is 63 bytes (page ≤ 999).

v1:l                          my "🙋 I was there…" list
v1:p                          staff: pick an occurrence of the last 7 days
v1:i|u:<c>:<d>                claim · remove my mark
v1:r|a:<c>:<d>:<page>         roster page · confirm every 🙋
v1:y|n:<c>:<d>:<acct>:<page>  mark present · unmark
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from tristhana.bots.telegram.shalas_callbacks import parse_short_id, short_id

PREFIX = "v1"
MAX_PAGE = 999
type Mine = Literal["i", "u"]
type OnRoster = Literal["r", "a"]
type Toggle = Literal["y", "n"]


@dataclass(frozen=True, slots=True)
class MyList:
    pass


@dataclass(frozen=True, slots=True)
class StaffPick:
    pass


@dataclass(frozen=True, slots=True)
class MyMark:
    action: Mine
    class_id: UUID
    key: date


@dataclass(frozen=True, slots=True)
class Roster:
    action: OnRoster
    class_id: UUID
    key: date
    page: int


@dataclass(frozen=True, slots=True)
class Person:
    action: Toggle
    class_id: UUID
    key: date
    account_id: UUID
    page: int


type AttendanceTap = MyList | StaffPick | MyMark | Roster | Person


def my_list() -> str:
    return f"{PREFIX}:l"


def staff_pick() -> str:
    return f"{PREFIX}:p"


def mark(action: Mine, class_id: UUID, key: date) -> str:
    return f"{PREFIX}:{action}:{short_id(class_id)}:{key:%Y%m%d}"


def roster(action: OnRoster, class_id: UUID, key: date, page: int = 0) -> str:
    return f"{PREFIX}:{action}:{short_id(class_id)}:{key:%Y%m%d}:{page}"


def person(action: Toggle, class_id: UUID, key: date, account_id: UUID, page: int) -> str:
    return f"{PREFIX}:{action}:{short_id(class_id)}:{key:%Y%m%d}:{short_id(account_id)}:{page}"


def _date(value: str) -> date | None:
    if len(value) != 8 or not value.isdigit():
        return None
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return None


def _page(value: str) -> int | None:
    if not value.isdigit() or (len(value) > 1 and value[0] == "0"):
        return None
    n = int(value)
    return n if n <= MAX_PAGE else None


def decode(data: str | None) -> AttendanceTap | None:
    parts = (data or "").split(":")
    if len(parts) < 2 or parts[0] != PREFIX:
        return None
    kind, rest = parts[1], parts[2:]
    if not rest:
        return {"l": MyList(), "p": StaffPick()}.get(kind)
    if len(rest) < 2:
        return None
    class_id, key = parse_short_id(rest[0]), _date(rest[1])
    if class_id is None or key is None:
        return None
    if kind in ("i", "u") and len(rest) == 2:
        return MyMark(kind, class_id, key)  # type: ignore[arg-type]
    if kind in ("r", "a") and len(rest) == 3:
        page = _page(rest[2])
        return None if page is None else Roster(kind, class_id, key, page)  # type: ignore[arg-type]
    if kind in ("y", "n") and len(rest) == 4:
        account_id, page = parse_short_id(rest[2]), _page(rest[3])
        if account_id is None or page is None:
            return None
        return Person(kind, class_id, key, account_id, page)  # type: ignore[arg-type]
    return None
