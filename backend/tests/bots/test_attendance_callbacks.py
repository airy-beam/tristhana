"""`v1:` callback data (SC-05 spec §5): round trips, ≤ 64 bytes, and forged data → None."""

from datetime import date
from uuid import UUID

import pytest

from tristhana.bots.telegram import attendance_callbacks as cb

C = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
A = UUID("12345678-1234-5678-1234-567812345678")
D = date(2026, 11, 9)


@pytest.mark.parametrize(
    ("data", "tap"),
    [
        (cb.my_list(), cb.MyList()),
        (cb.staff_pick(), cb.StaffPick()),
        (cb.mark("i", C, D), cb.MyMark("i", C, D)),
        (cb.mark("u", C, D), cb.MyMark("u", C, D)),
        (cb.roster("r", C, D, 3), cb.Roster("r", C, D, 3)),
        (cb.roster("a", C, D), cb.Roster("a", C, D, 0)),
        (cb.person("y", C, D, A, 999), cb.Person("y", C, D, A, 999)),
        (cb.person("n", C, D, A, 0), cb.Person("n", C, D, A, 0)),
    ],
)
def test_round_trip_and_size(data: str, tap: cb.AttendanceTap) -> None:
    assert cb.decode(data) == tap
    assert len(data.encode()) <= 64


def test_the_longest_is_63_bytes() -> None:
    assert len(cb.person("y", C, D, A, 999).encode()) == 63


@pytest.mark.parametrize(
    "data",
    [
        None, "", "v1", "v1:x", "v2:l", "v1:l:1", "v1:i:abc:20261109",
        cb.mark("i", C, D) + ":1", cb.roster("r", C, D, 0)[:-1] + "01",
        cb.roster("r", C, D, 0)[:-1] + "1000", cb.mark("i", C, D).replace("20261109", "20261340"),
        cb.person("y", C, D, A, 1).replace(":1", ":-1"), cb.person("q", C, D, A, 1),  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    ],
)  # fmt: skip
def test_forged_data_is_nothing(data: str | None) -> None:
    assert cb.decode(data) is None
