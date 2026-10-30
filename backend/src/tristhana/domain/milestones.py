"""Practice-count milestones (GM-01 part 2, ADR-0028): a quiet 🎉 when the number of
practised days reaches 100 / 365 / 1000. Each threshold celebrates once ever; the thresholds
are data (`data/seed/milestones.yaml`), never code.

A practice is a day logged as Practiced, in any context, once per day (the same definition
as ST-01's "practiced"). Rest, moon, 🌸, sick, travel and "No practice" never count.
"""

from dataclasses import dataclass
from itertools import pairwise

from tristhana.domain.days import DayStatus

MAX_THRESHOLD = 100_000
MAX_THRESHOLDS = 12


class InvalidThresholds(ValueError):
    """Thresholds must be 1..100 000, strictly ascending, at most 12 (the seed loader also
    refuses an empty list; empty is `NO_COUNTS`, for wiring that doesn't celebrate)."""


def counts_as_practice(status: DayStatus) -> bool:
    return status is DayStatus.PRACTICED


@dataclass(frozen=True, slots=True)
class PracticeCounts:
    thresholds: tuple[int, ...]

    def __post_init__(self) -> None:
        t = self.thresholds
        if len(t) > MAX_THRESHOLDS:
            raise InvalidThresholds(f"at most {MAX_THRESHOLDS} thresholds")
        if any(not 1 <= n <= MAX_THRESHOLD for n in t):
            raise InvalidThresholds(f"thresholds must be 1..{MAX_THRESHOLD}")
        if any(a >= b for a, b in pairwise(t)):
            raise InvalidThresholds("thresholds must be strictly ascending")

    def seen_by(self, count: int) -> tuple[int, ...]:
        """Thresholds at or below `count`: recorded in the ledger (maybe silently)."""
        return tuple(n for n in self.thresholds if n <= count)

    def reached(self, count: int) -> int | None:
        """The threshold equal to `count`, the one that may celebrate."""
        return count if count in self.thresholds else None


NO_COUNTS = PracticeCounts(())
