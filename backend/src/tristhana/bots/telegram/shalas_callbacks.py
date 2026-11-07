"""Stateless callback data for shalas (SC-01, ADR-0008), versioned `h1:`. Distinct from the
`h_<code>` / `hs_<code>` start payloads. Ids are 22-character base64url uuids, so two fit in
64 bytes; an id here is no capability: every write checks the caller's membership.

h1:a:<code>  h1:n  h1:l:<locale>:<code>  h1:b:<code>   join, not now, language, staff accept
h1:c:<s>  h1:m:<s>:<page>  h1:v:<s>:<acct>             card, students page, student
h1:i:<s>  h1:q:<s>  h1:w:<s>  h1:wy:<s>                join link, QR, new link ask, new link
h1:e:<s>  h1:e:<s>:<t|a|o|m>                           staff link: pick a role, create one
h1:u:<s>:<acct>  h1:x:<s>:<acct>  h1:k:<s>  h1:ky:<s>  remove ask, remove, leave ask, leave
"""

import base64
import binascii
import re
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from tristhana.domain.locale import LOCALES, Locale
from tristhana.domain.shalas import ShalaRole, parse_shala_invite

PREFIX = "h1"
type OnShala = Literal["c", "i", "q", "w", "wy", "e", "k", "ky"]
type OnMember = Literal["v", "u", "x"]
_ON_SHALA = ("c", "i", "q", "w", "wy", "e", "k", "ky")
_ON_MEMBER = ("v", "u", "x")
_SHORT = re.compile(r"[A-Za-z0-9_-]{22}")
ROLE_CODES: dict[str, ShalaRole] = {
    "t": ShalaRole.TEACHER,
    "a": ShalaRole.ASSISTANT,
    "o": ShalaRole.OFFICE,
    "m": ShalaRole.ADMIN,  # "Manager"
}
_CODE_OF = {role: code for code, role in ROLE_CODES.items()}


@dataclass(frozen=True, slots=True)
class Join:
    code: str


@dataclass(frozen=True, slots=True)
class AcceptStaff:
    code: str


@dataclass(frozen=True, slots=True)
class Language:
    locale: Locale
    code: str


@dataclass(frozen=True, slots=True)
class NotNow:
    pass


@dataclass(frozen=True, slots=True)
class Shala:
    action: OnShala
    id: UUID


@dataclass(frozen=True, slots=True)
class Students:
    id: UUID
    page: int


@dataclass(frozen=True, slots=True)
class Member:
    action: OnMember
    id: UUID
    account: UUID


@dataclass(frozen=True, slots=True)
class StaffLink:
    id: UUID
    role: ShalaRole


type ShalaTap = Join | AcceptStaff | Language | NotNow | Shala | Students | Member | StaffLink


def short_id(id: UUID) -> str:
    return base64.urlsafe_b64encode(id.bytes).rstrip(b"=").decode()


def parse_short_id(value: str) -> UUID | None:
    """Only the canonical form: one id has one callback string."""
    if not _SHORT.fullmatch(value):
        return None
    try:
        id = UUID(bytes=base64.urlsafe_b64decode(value + "=="))
    except (binascii.Error, ValueError):
        return None
    return id if short_id(id) == value else None


def join(code: str) -> str:
    return f"{PREFIX}:a:{code}"


def accept_staff(code: str) -> str:
    return f"{PREFIX}:b:{code}"


def language(locale: Locale, code: str) -> str:
    return f"{PREFIX}:l:{locale}:{code}"


def not_now() -> str:
    return f"{PREFIX}:n"


def on_shala(action: OnShala, id: UUID) -> str:
    return f"{PREFIX}:{action}:{short_id(id)}"


def students(id: UUID, page: int) -> str:
    return f"{PREFIX}:m:{short_id(id)}:{page}"


def on_member(action: OnMember, id: UUID, account: UUID) -> str:
    return f"{PREFIX}:{action}:{short_id(id)}:{short_id(account)}"


def staff_link(id: UUID, role: ShalaRole) -> str:
    return f"{PREFIX}:e:{short_id(id)}:{_CODE_OF[role]}"


def _code(value: str) -> str | None:
    found = parse_shala_invite(f"h_{value}")
    return found.code if found else None


def _page(value: str) -> bool:
    """At most 4 digits, so a forged huge page never reaches the database as an offset."""
    return 1 <= len(value) <= 4 and value.isascii() and value.isdigit()


def decode(data: str | None) -> ShalaTap | None:
    """None for anything malformed or from another version."""
    match (data or "").split(":"):
        case [p, "n"] if p == PREFIX:
            return NotNow()
        case [p, "a", value] if p == PREFIX and (code := _code(value)):
            return Join(code)
        case [p, "b", value] if p == PREFIX and (code := _code(value)):
            return AcceptStaff(code)
        case [p, "l", locale, value] if (
            p == PREFIX and locale in LOCALES and (code := _code(value))
        ):
            return Language(locale, code)  # type: ignore[arg-type]
        case [p, "m", s, page] if p == PREFIX and (id := parse_short_id(s)) and _page(page):
            return Students(id, int(page))
        case [p, "e", s, role] if p == PREFIX and (id := parse_short_id(s)) and role in ROLE_CODES:
            return StaffLink(id, ROLE_CODES[role])
        case [p, action, s] if p == PREFIX and action in _ON_SHALA and (id := parse_short_id(s)):
            return Shala(action, id)  # type: ignore[arg-type]
        case [p, action, s, a] if (
            p == PREFIX
            and action in _ON_MEMBER
            and (id := parse_short_id(s))
            and (account := parse_short_id(a))
        ):
            return Member(action, id, account)  # type: ignore[arg-type]
        case _:
            return None
