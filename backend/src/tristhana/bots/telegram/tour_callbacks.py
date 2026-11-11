"""Stateless callback data for the quick tour (UI-02, ADR-0008), versioned `q1:`.

q1:2:s    show step 2; `s` or `h`: the tour was opened from /start or /help
q1:d:s    Done: back to where it was opened
"""

from dataclasses import dataclass
from typing import Literal

PREFIX = "q1"
STEP_KEYS = ("tour-log", "tour-rest", "tour-remind", "tour-asanas", "tour-links", "tour-app")
STEPS = len(STEP_KEYS)
type Origin = Literal["s", "h"]


@dataclass(frozen=True, slots=True)
class TourTap:
    n: int | None  # None: Done
    origin: Origin


def step(n: int, origin: Origin) -> str:
    return f"{PREFIX}:{n}:{origin}"


def done(origin: Origin) -> str:
    return f"{PREFIX}:d:{origin}"


def decode(data: str | None) -> TourTap | None:
    """None for anything malformed. A step past the end (an old keyboard) is the last one."""
    parts = (data or "").split(":")
    if len(parts) != 3 or parts[0] != PREFIX or parts[2] not in ("s", "h"):
        return None
    origin = parts[2]
    if parts[1] == "d":
        return TourTap(None, origin)
    if not (parts[1].isascii() and parts[1].isdigit()) or int(parts[1]) < 1:
        return None
    return TourTap(min(int(parts[1]), STEPS), origin)
