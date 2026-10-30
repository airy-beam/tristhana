import pytest

from tristhana.domain.days import DayStatus
from tristhana.domain.milestones import (
    NO_COUNTS,
    InvalidThresholds,
    PracticeCounts,
    counts_as_practice,
)

COUNTS = PracticeCounts((100, 365, 1000))


@pytest.mark.parametrize("status", list(DayStatus))
def test_only_practiced_counts(status: DayStatus) -> None:
    assert counts_as_practice(status) is (status is DayStatus.PRACTICED)


@pytest.mark.parametrize(
    "thresholds",
    [(365, 100), (100, 100), (0, 100), (100, 100_001), tuple(range(1, 14))],
)
def test_invalid_thresholds(thresholds: tuple[int, ...]) -> None:
    with pytest.raises(InvalidThresholds):
        PracticeCounts(thresholds)


def test_no_counts_is_empty() -> None:
    assert NO_COUNTS.thresholds == ()
    assert (NO_COUNTS.seen_by(100), NO_COUNTS.reached(100)) == ((), None)


@pytest.mark.parametrize(
    ("count", "seen", "reached"),
    [
        (0, (), None),
        (99, (), None),
        (100, (100,), 100),
        (101, (100,), None),
        (364, (100,), None),
        (365, (100, 365), 365),
        (1000, (100, 365, 1000), 1000),
        (5000, (100, 365, 1000), None),
    ],
)
def test_seen_by_and_reached(count: int, seen: tuple[int, ...], reached: int | None) -> None:
    assert (COUNTS.seen_by(count), COUNTS.reached(count)) == (seen, reached)


def test_a_threshold_added_later() -> None:
    later = PracticeCounts((100, 365, 500, 1000))

    assert later.seen_by(700) == (100, 365, 500)
    assert later.reached(500) == 500
