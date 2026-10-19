"""Callback data for the moon screens (MD-03), versioned `m1:`. Values are absolute (the
offsets to set, not "toggle"), so stale keyboards stay harmless.

    m1:v                 /moon screen            m1:r            reminder settings
    m1:c:2               city picker, page 2     m1:s:<slug>     follow a city
    m1:z:<slug>          use that city's zone for reminders (only while none is set)
    m1:o:71              set offsets to {7, 1}   (m1:o:0 = off)
    m1:t:1900            send time 19:00
    m1:q:20261105:p:1:0  from a reminder (date, phase p/a, days before, action):
                         1 = only the day before, 0 = turn off, a = turn back on
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Literal

from tristhana.domain.moon import MoonPhase
from tristhana.domain.notifications import MOON_OFFSETS

PREFIX = "m1"
type Action = Literal["view", "reminders", "cities", "city", "zone", "offsets", "time", "quick"]
type Quick = Literal["only1", "off", "on"]

_SLUG = re.compile(r"[a-z-]{1,24}")
_QUICK: dict[str, Quick] = {"1": "only1", "0": "off", "a": "on"}
_QUICK_CODES = {v: k for k, v in _QUICK.items()}
_PHASES = {"p": MoonPhase.PURNIMA, "a": MoonPhase.AMAVASYA}
_PHASE_CODES = {v: k for k, v in _PHASES.items()}


@dataclass(frozen=True, slots=True)
class MoonCallback:
    action: Action
    page: int = 0
    slug: str | None = None
    offsets: frozenset[int] | None = None
    at: time | None = None
    moon_date: date | None = None
    phase: MoonPhase | None = None
    days_before: int = 0
    quick: Quick | None = None


def offsets_code(offsets: frozenset[int]) -> str:
    return "".join(str(k) for k in sorted(offsets, reverse=True)) or "0"


def encode(cb: MoonCallback) -> str:
    match cb.action:
        case "view":
            return f"{PREFIX}:v"
        case "reminders":
            return f"{PREFIX}:r"
        case "cities":
            return f"{PREFIX}:c:{cb.page}"
        case "city":
            return f"{PREFIX}:s:{cb.slug}"
        case "zone":
            return f"{PREFIX}:z:{cb.slug}"
        case "offsets":
            assert cb.offsets is not None  # noqa: S101
            return f"{PREFIX}:o:{offsets_code(cb.offsets)}"
        case "time":
            assert cb.at is not None  # noqa: S101
            return f"{PREFIX}:t:{cb.at:%H%M}"
        case "quick":
            assert cb.moon_date  # noqa: S101
            assert cb.phase  # noqa: S101
            assert cb.quick  # noqa: S101
            return (
                f"{PREFIX}:q:{cb.moon_date:%Y%m%d}:{_PHASE_CODES[cb.phase]}"
                f":{cb.days_before}:{_QUICK_CODES[cb.quick]}"
            )


def decode(data: str | None) -> MoonCallback | None:
    """None for anything malformed or forged."""
    parts = (data or "").split(":")
    if len(parts) < 2 or parts[0] != PREFIX:
        return None
    match parts[1:]:
        case ["v"]:
            return MoonCallback("view")
        case ["r"]:
            return MoonCallback("reminders")
        case ["c", page] if page.isdigit() and int(page) < 20:
            return MoonCallback("cities", page=int(page))
        case ["s" | "z" as kind, slug] if _SLUG.fullmatch(slug):
            return MoonCallback("city" if kind == "s" else "zone", slug=slug)
        case ["o", code] if code == "0" or (
            code.isdigit()
            and {int(c) for c in code} <= MOON_OFFSETS
            and len(set(code)) == len(code)
        ):
            offsets = frozenset[int]() if code == "0" else frozenset(int(c) for c in code)
            return MoonCallback("offsets", offsets=offsets)
        case ["t", hhmm] if len(hhmm) == 4 and hhmm.isdigit():
            try:
                return MoonCallback("time", at=datetime.strptime(hhmm, "%H%M").time())
            except ValueError:
                return None
        case ["q", ymd, phase, k, quick] if (
            phase in _PHASES and k in ("1", "3", "7") and quick in _QUICK
        ):
            try:
                moon_date = datetime.strptime(ymd, "%Y%m%d").date()
            except ValueError:
                return None
            return MoonCallback(
                "quick",
                moon_date=moon_date,
                phase=_PHASES[phase],
                days_before=int(k),
                quick=_QUICK[quick],
            )
        case _:
            return None
