"""Stateless callback data for the directory listing (ID-05, ADR-0042), versioned `l1:`.

l1:o  l1:w  l1:wy                 my status screen, remove ask, remove
l1:a:<page>  l1:k:<page>          admin: waiting list, listed list (re-check)
l1:c:<uuid>                       admin: a card (a request, or a listed row)
l1:y:<uuid>:<rev>                 admin: Listed / Still listed
l1:n:<uuid>:<rev>                 admin: not-found ask
l1:ny:<uuid>:<rev>                admin: not found / no longer listed

`<rev>` makes an old button harmless after an edit; a forged uuid matches no row; every admin
tap re-checks the policy. Longest: `l1:ny:<uuid>:2147483647` = 53 bytes.
"""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

PREFIX = "l1"
type MineAction = Literal["o", "w", "wy"]
type DecideAction = Literal["y", "n", "ny"]
_MINE = ("o", "w", "wy")
_DECIDE = ("y", "n", "ny")
_MAX_REVISION = 2**31 - 1  # the column is an integer


@dataclass(frozen=True, slots=True)
class Mine:
    action: MineAction


@dataclass(frozen=True, slots=True)
class AdminList:
    listed: bool
    page: int


@dataclass(frozen=True, slots=True)
class AdminCard:
    id: UUID


@dataclass(frozen=True, slots=True)
class Decide:
    action: DecideAction
    id: UUID
    revision: int


type ListingTap = Mine | AdminList | AdminCard | Decide


def mine(action: MineAction) -> str:
    return f"{PREFIX}:{action}"


def admin_list(listed: bool, page: int) -> str:
    return f"{PREFIX}:{'k' if listed else 'a'}:{page}"


def admin_card(id: UUID) -> str:
    return f"{PREFIX}:c:{id}"


def decide(action: DecideAction, id: UUID, revision: int) -> str:
    return f"{PREFIX}:{action}:{id}:{revision}"


def _uuid(value: str) -> UUID | None:
    try:
        id = UUID(value)
    except ValueError:
        return None
    return id if str(id) == value else None


def _number(value: str, digits: int) -> bool:
    return 1 <= len(value) <= digits and value.isascii() and value.isdigit()


def decode(data: str | None) -> ListingTap | None:
    """None for anything malformed or from another version."""
    match (data or "").split(":"):
        case [p, action] if p == PREFIX and action in _MINE:
            return Mine(action)  # type: ignore[arg-type]
        case [p, "a" | "k" as which, page] if p == PREFIX and _number(page, 4):
            return AdminList(which == "k", int(page))
        case [p, "c", value] if p == PREFIX and (id := _uuid(value)):
            return AdminCard(id)
        case [p, action, value, rev] if (
            p == PREFIX
            and action in _DECIDE
            and _number(rev, 10)
            and int(rev) <= _MAX_REVISION
            and rev != "0"
            and (id := _uuid(value))
        ):
            return Decide(action, id, int(rev))  # type: ignore[arg-type]
        case _:
            return None
