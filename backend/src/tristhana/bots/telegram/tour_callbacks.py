"""Callback data of the bot's quick tour (UI-02), versioned `q1:`. The tour itself was
retired by UI-06; only the decoder stays, for the buttons still in chat history, which land
on Help or Today (`home.py`). No screen builds this data any more.

q1:2:s    was "show step 2"; `s` or `h`: the tour was opened from /start or /help
q1:d:s    was "Done": back to where it was opened
"""

from dataclasses import dataclass
from typing import Literal

PREFIX = "q1"
STEPS = 6  # the tour had six steps
type Origin = Literal["s", "h"]


@dataclass(frozen=True, slots=True)
class TourTap:
    n: int | None  # None: Done
    origin: Origin


def decode(data: str | None) -> TourTap | None:
    """None for anything malformed. A step past the end is the last one."""
    parts = (data or "").split(":")
    if len(parts) != 3 or parts[0] != PREFIX or parts[2] not in ("s", "h"):
        return None
    origin = parts[2]
    if parts[1] == "d":
        return TourTap(None, origin)
    if not (parts[1].isascii() and parts[1].isdigit()) or int(parts[1]) < 1:
        return None
    return TourTap(min(int(parts[1]), STEPS), origin)
