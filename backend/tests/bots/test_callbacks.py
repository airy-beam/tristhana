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
        "d1:o:20261018:p",
        "d1:q:20261018",
    ],
)
def test_malformed_or_out_of_range_is_none(data: str | None) -> None:
    assert decode(data) is None
