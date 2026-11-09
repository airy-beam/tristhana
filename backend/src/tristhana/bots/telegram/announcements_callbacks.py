"""Stateless callback data for announcements (NT-03, ADR-0008), versioned `b1:`. A source is
`<k>:<id>`: `t` + the teacher's account id, or `h` + a shala id (22-character base64url, as
`h1:`). An id here is no capability: every read and mute is keyed on the caller.

b1:l:<k>:<id>:<page>   the feed for one source (page 0-99)
b1:m:<k>:<id>:<w>      mute; `w` = n (on the message: edit the buttons only) or l (the feed)
b1:u:<k>:<id>:<w>      unmute
"""

from dataclasses import dataclass
from typing import Literal

from tristhana.bots.telegram.shalas_callbacks import parse_short_id, short_id
from tristhana.domain.announcements import Source, SourceKind

PREFIX = "b1"
type Where = Literal["n", "l"]
_KINDS = {k.value: k for k in SourceKind}


@dataclass(frozen=True, slots=True)
class List:
    source: Source
    page: int


@dataclass(frozen=True, slots=True)
class Mute:
    source: Source
    muted: bool
    where: Where


type AnnouncementTap = List | Mute


def _source(source: Source) -> str:
    return f"{source.kind.value}:{short_id(source.id)}"


def feed(source: Source, page: int = 0) -> str:
    return f"{PREFIX}:l:{_source(source)}:{page}"


def mute(source: Source, muted: bool, where: Where) -> str:
    return f"{PREFIX}:{'m' if muted else 'u'}:{_source(source)}:{where}"


def _page(value: str) -> bool:
    """At most 2 digits: a forged huge page never reaches the database as an offset."""
    return 1 <= len(value) <= 2 and value.isascii() and value.isdigit()


def decode(data: str | None) -> AnnouncementTap | None:
    """None for anything malformed or from another version."""
    match (data or "").split(":"):
        case [p, "l", k, s, page] if (
            p == PREFIX and k in _KINDS and (id := parse_short_id(s)) and _page(page)
        ):
            return List(Source(_KINDS[k], id), int(page))
        case [p, ("m" | "u") as action, k, s, ("n" | "l") as where] if (
            p == PREFIX and k in _KINDS and (id := parse_short_id(s))
        ):
            return Mute(Source(_KINDS[k], id), action == "m", where)
        case _:
            return None
