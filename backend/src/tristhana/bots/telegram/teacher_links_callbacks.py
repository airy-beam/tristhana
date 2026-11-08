"""Stateless callback data for teacher links (ID-04, ADR-0008), versioned `t1:`. Distinct from
the `t_<code>` start payload. A uuid here is no capability: every write is keyed on the
caller's account, so a forged id matches no row.

t1:a:<code>  t1:n  t1:l:<locale>:<code>     consent: confirm, not now, language
t1:y:<code>                                 old confirm (before ST-06): re-renders the consent only
t1:o  t1:s:<page>                           teachers screen, my students
t1:c:<id>  t1:p:<id>  t1:u:<id>  t1:x:<id>  teacher card, make main, remove ask, remove
t1:v:<id>[:<page>]  t1:r:<id>  t1:z:<id>    student card (Back keeps the page), remove ask, remove
t1:i  t1:q  t1:w  t1:wy                     invite screen, send QR, new link ask, new link
t1:g:<id>:<page>                            mark a new asana: the picker (PR-08 Phase 3)
t1:gp:<id>:<n>:<i>:<k>:<page>               picked → the confirm screen
t1:gy:<id>:<n>:<i>:<k>:<page>               confirm and mark

A position is `<n>:<i>`, the series number and the stop's index in it (`0:0` = standing only):
a stop key doesn't fit beside a uuid. `<k>` (1-3) counts the steps from there; the server
re-derives the target from the catalog and checks the position itself, so a forged value can
only fail. Longest: `t1:gy:<uuid>:6:99:3:9999` = 54 bytes.
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


@dataclass(frozen=True, slots=True)
class Give:
    """The picker of a student's next stops (PR-08 Phase 3)."""

    id: UUID
    page: int


@dataclass(frozen=True, slots=True)
class GiveStep:
    """`confirm` False: picked, show the confirm screen; True: mark it."""

    id: UUID
    number: int  # the series of the position the teacher saw (0 = standing only)
    index: int  # that stop's index in its series
    steps: int  # 1-3: how many stops further the target is
    page: int
    confirm: bool


type LinkTap = Confirm | Reopen | Card | Language | Students | OnPerson | Tap | Give | GiveStep


def plain(action: Plain) -> str:
    return f"{PREFIX}:{action}"


def person(action: Person, id: UUID) -> str:
    return f"{PREFIX}:{action}:{id}"


def confirm(code: str) -> str:
    return f"{PREFIX}:a:{code}"


def card(id: UUID, page: int) -> str:
    return f"{PREFIX}:v:{id}:{page}"


def give(id: UUID, page: int) -> str:
    return f"{PREFIX}:g:{id}:{page}"


def give_step(
    id: UUID, number: int, index: int, steps: int, page: int, confirm: bool = False
) -> str:
    return f"{PREFIX}:{'gy' if confirm else 'gp'}:{id}:{number}:{index}:{steps}:{page}"


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


def _step(id: str, n: str, i: str, k: str, page: str, confirm: bool) -> GiveStep | None:
    found = _person("v", id)
    if found is None or not _page(page) or k not in ("1", "2", "3"):
        return None
    if not (len(n) == 1 and n in "0123456") or not (1 <= len(i) <= 2 and i.isascii()):
        return None
    if not i.isdigit() or (n == "0" and i != "0"):  # standing only is `0:0`; `2:0` = Pasasana
        return None
    return GiveStep(found.id, int(n), int(i), int(k), int(page), confirm)


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
        case [p, "g", value, page] if p == PREFIX and _page(page):
            found = _person("v", value)
            return Give(found.id, int(page)) if found else None
        case [p, "gp" | "gy" as action, value, n, i, k, page] if p == PREFIX:
            return _step(value, n, i, k, page, action == "gy")
        case [p, action, value] if p == PREFIX and action in _PERSON:
            return _person(action, value)  # type: ignore[arg-type]
        case _:
            return None
