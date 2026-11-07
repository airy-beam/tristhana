"""Stateless callback data for teacher links (ID-04, ADR-0008), versioned `t1:`. Distinct from
the `t_<code>` start payload. A uuid here is no capability: every write is keyed on the
caller's account, so a forged id matches no row.

t1:a:<code>  t1:n  t1:l:<locale>:<code>     consent: confirm, not now, language
t1:y:<code>                                 old confirm (before ST-06): re-renders the consent only
t1:o  t1:s:<page>                           teachers screen, my students
t1:c:<id>  t1:p:<id>  t1:u:<id>  t1:x:<id>  teacher card, make main, remove ask, remove
t1:v:<id>[:<page>]  t1:r:<id>  t1:z:<id>    student card (Back keeps the page), remove ask, remove
t1:i  t1:q  t1:w  t1:wy                     invite screen, send QR, new link ask, new link
"""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from tristhana.domain.locale import LOCALES, Locale
from tristhana.domain.teacher_links import parse_invite

PREFIX = "t1"
type Plain = Literal["n", "o", "i", "q", "w", "wy"]
type Person = Literal["c", "p", "u", "x", "v", "r", "z"]
_PLAIN = ("n", "o", "i", "q", "w", "wy")
_PERSON = ("c", "p", "u", "x", "v", "r", "z")


@dataclass(frozen=True, slots=True)
class Confirm:
    code: str


@dataclass(frozen=True, slots=True)
class Reopen:
    """An old ✅ (`t1:y`): its screen may show older consent text, so it only shows the current
    one and never links (ST-06)."""

    code: str


@dataclass(frozen=True, slots=True)
class Card:
    id: UUID
    page: int


@dataclass(frozen=True, slots=True)
class Language:
    locale: Locale
    code: str


@dataclass(frozen=True, slots=True)
class Students:
    page: int


@dataclass(frozen=True, slots=True)
class OnPerson:
    action: Person
    id: UUID


@dataclass(frozen=True, slots=True)
class Tap:
    action: Plain


type LinkTap = Confirm | Reopen | Card | Language | Students | OnPerson | Tap


def plain(action: Plain) -> str:
    return f"{PREFIX}:{action}"


def person(action: Person, id: UUID) -> str:
    return f"{PREFIX}:{action}:{id}"


def confirm(code: str) -> str:
    return f"{PREFIX}:a:{code}"


def card(id: UUID, page: int) -> str:
    return f"{PREFIX}:v:{id}:{page}"


def language(locale: Locale, code: str) -> str:
    return f"{PREFIX}:l:{locale}:{code}"


def students(page: int) -> str:
    return f"{PREFIX}:s:{page}"


def _code(value: str) -> str | None:
    return parse_invite(f"t_{value}")


def _person(action: Person, value: str) -> OnPerson | None:
    try:
        id = UUID(value)
    except ValueError:
        return None
    return OnPerson(action, id) if str(id) == value else None


def _page(value: str) -> bool:
    """At most 4 digits: 500 students fit in 50 pages, and a forged huge page must never reach
    the database as an offset (a page past the end already falls back to page 0)."""
    return 1 <= len(value) <= 4 and value.isascii() and value.isdigit()


def decode(data: str | None) -> LinkTap | None:
    """None for anything malformed or from another version."""
    match (data or "").split(":"):
        case [p, action] if p == PREFIX and action in _PLAIN:
            return Tap(action)  # type: ignore[arg-type]
        case [p, "a", value] if p == PREFIX and (code := _code(value)):
            return Confirm(code)
        case [p, "y", value] if p == PREFIX and (code := _code(value)):
            return Reopen(code)
        case [p, "v", value, page] if p == PREFIX and _page(page):
            found = _person("v", value)
            return Card(found.id, int(page)) if found else None
        case [p, "l", locale, value] if (
            p == PREFIX and locale in LOCALES and (code := _code(value))
        ):
            return Language(locale, code)  # type: ignore[arg-type]
        case [p, "s", page] if p == PREFIX and _page(page):
            return Students(int(page))
        case [p, action, value] if p == PREFIX and action in _PERSON:
            return _person(action, value)  # type: ignore[arg-type]
        case _:
            return None
