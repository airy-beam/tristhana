"""After-practice check-in (PR-06, ADR-0024): mood, energy and effort (1 to 5 each, all
optional) plus body-and-mind tags, one per practice slot on a Practiced day.

Check-ins describe, never advise: nothing here infers anything from them (spec §1).
"""

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from typing import Literal

SCALE = range(1, 6)
OFFER_DAYS = 2  # the one-tap mood row: today and yesterday only


class CheckInTag(StrEnum):
    """Display order = definition order: body first, then mind (ashtanga-expert)."""

    STIFF = "stiff"
    OPEN = "open"
    STRONG = "strong"
    LIGHT = "light"
    HEAVY = "heavy"
    SORE = "sore"
    FOCUSED = "focused"
    CALM = "calm"
    SCATTERED = "scattered"
    STEADY_BREATH = "steady_breath"


_BODY = frozenset(
    {
        CheckInTag.STIFF,
        CheckInTag.OPEN,
        CheckInTag.STRONG,
        CheckInTag.LIGHT,
        CheckInTag.HEAVY,
        CheckInTag.SORE,
    }
)
TAG_GROUPS: dict[CheckInTag, Literal["body", "mind"]] = {
    t: "body" if t in _BODY else "mind" for t in CheckInTag
}


@dataclass(frozen=True, slots=True)
class CheckIn:
    mood: int | None = None  # 1 😔 … 5 😊; the emoji live in .ftl
    energy: int | None = None  # 1 low … 5 high
    effort: int | None = None  # 1 easy … 5 hard
    tags: frozenset[CheckInTag] = frozenset()
    slot: int = 1

    def is_empty(self) -> bool:
        """No scale and no tag: the same as no check-in at all."""
        return self.mood is None and self.energy is None and self.effort is None and not self.tags


class InvalidCheckIn(ValueError):
    pass


def check_check_in(check_in: CheckIn) -> CheckIn:
    """Raises `InvalidCheckIn` for a scale outside 1..5, an unknown tag or a slot other
    than 1 (one practice per day for now)."""
    if check_in.slot != 1:
        raise InvalidCheckIn(f"slot {check_in.slot}")
    for name in ("mood", "energy", "effort"):
        value = getattr(check_in, name)
        if value is not None and value not in SCALE:
            raise InvalidCheckIn(f"{name} {value}")
    # Typed as tags, but a caller may still pass raw keys ("sleepy" is not a tag).
    if any(not isinstance(t, CheckInTag) for t in check_in.tags):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise InvalidCheckIn("unknown tag")
    return check_in


def offer_mood_row(day: date, today: date, existing: CheckIn | None, enabled: bool) -> bool:
    """Whether the practice screens offer the one-tap mood row: the setting is on, the day
    is today or yesterday, and there is no check-in yet. Otherwise only ✨ Check-in."""
    if not enabled or (existing is not None and not existing.is_empty()):
        return False
    return today - timedelta(days=OFFER_DAYS - 1) <= day <= today
