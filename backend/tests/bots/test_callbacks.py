from datetime import date

import pytest

from tristhana.bots.telegram.callbacks import DayCallback, decode, encode
from tristhana.domain.days import DayStatus

DAY = date(2026, 10, 18)


@pytest.mark.parametrize(
    "cb",
    [
        DayCallback("today"),
        DayCallback("open", DAY),
        DayCallback("clear", DAY),
        DayCallback("week", DAY),
        *(DayCallback("set", DAY, s) for s in DayStatus),
        *(DayCallback("now", DAY, s) for s in DayStatus),  # ADR-0051: a tap from Today
        DayCallback("reasons", DAY, origin="t"),  # UI-06: "Other reason", back to Today
        DayCallback("reasons", DAY, origin="e"),  # ... or back to the day's editor
    ],
)
def test_round_trip_and_size(cb: DayCallback) -> None:
    data = encode(cb)

    assert decode(data) == cb
    assert len(data.encode()) <= 64


@pytest.mark.parametrize(
    "data",
    [
        None,
        "",
        "d1",
        "d2:t",
        "d1:o:20261399",
        "d1:o:19991231",
        "d1:w:00010103",
        "d1:w:99991231",
        "d1:s:20261018",
        "d1:s:20261018:?",
        "d1:n:20261018",
        "d1:n:20261018:?",
        "d1:n:20261018:p:1",
        "d1:o:20261018:p",
        "d1:q:20261018",
        "d1:r:20261018",
        "d1:r:20261018:x",
        "d1:r:20261018:t:1",
    ],
)
def test_malformed_or_out_of_range_is_none(data: str | None) -> None:
    assert decode(data) is None


def test_other_reason_data_is_short_and_needs_an_origin() -> None:
    assert encode(DayCallback("reasons", DAY, origin="t")) == "d1:r:20261018:t"
    assert len(encode(DayCallback("reasons", DAY, origin="e")).encode()) <= 22  # UI-06 §2
    with pytest.raises(ValueError, match="origin"):
        encode(DayCallback("reasons", DAY))


def test_a_tap_from_today_has_its_own_letter_and_the_editors_keeps_its_own() -> None:
    """ADR-0051: `d1:s` keeps meaning "save this date"; Today's buttons carry `d1:n`."""
    assert encode(DayCallback("now", DAY, DayStatus.PRACTICED)) == "d1:n:20261018:p"
    assert decode("d1:s:20261018:p") == DayCallback("set", DAY, DayStatus.PRACTICED)
    with pytest.raises(ValueError, match="status"):
        encode(DayCallback("now", DAY))
