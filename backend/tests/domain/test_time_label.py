"""ADR-0044: a displayed time always names its place; the UTC offset shows only outside the
viewer's own IANA zone. Pure (`zoneinfo` only): the city name is the formatter's business."""

from datetime import date, time

import pytest

from tristhana.domain.time_label import offset_shown, offset_text

DAY = date(2026, 11, 16)
AT = time(7)


def test_no_offset_in_the_viewers_own_zone() -> None:
    assert offset_shown("Asia/Almaty", "Asia/Almaty") is False


def test_another_zone_shows_the_offset() -> None:
    assert offset_shown("Europe/Berlin", "Asia/Almaty") is True


def test_another_zone_with_the_same_offset_still_shows_it() -> None:
    """Names are compared, not clocks: Almaty and Tashkent are both UTC+5 today."""
    assert offset_text("Asia/Almaty", DAY, AT) == offset_text("Asia/Tashkent", DAY, AT)
    assert offset_shown("Asia/Tashkent", "Asia/Almaty") is True


def test_an_unknown_viewer_zone_shows_the_offset() -> None:
    assert offset_shown("Asia/Almaty", None) is True


@pytest.mark.parametrize("viewer", [None, "UTC", "Asia/Almaty"])
def test_utc_never_gets_an_offset(viewer: str | None) -> None:
    """`07:00 UTC` already says it."""
    assert offset_shown("UTC", viewer) is False


def test_a_utc_viewer_sees_the_offset_of_a_place() -> None:
    assert offset_shown("Asia/Almaty", "UTC") is True


@pytest.mark.parametrize(
    ("zone", "day", "text"),
    [
        ("Asia/Almaty", DAY, "UTC+5"),
        ("Asia/Kolkata", DAY, "UTC+5:30"),  # a half-hour zone
        ("Asia/Kathmandu", DAY, "UTC+5:45"),
        ("America/New_York", date(2026, 1, 15), "UTC-5"),
        ("America/St_Johns", date(2026, 1, 15), "UTC-3:30"),
        ("Europe/London", date(2026, 1, 15), "UTC+0"),
        ("Europe/Berlin", date(2026, 3, 28), "UTC+1"),  # the day before the change
        ("Europe/Berlin", date(2026, 3, 29), "UTC+2"),  # 07:00 on the daylight-saving date
        ("Europe/Berlin", date(2026, 10, 25), "UTC+1"),
    ],
)
def test_the_offset_is_the_one_on_that_date(zone: str, day: date, text: str) -> None:
    assert offset_text(zone, day, AT) == text


def test_the_offset_is_the_one_at_that_time_on_a_change_night() -> None:
    change = date(2026, 3, 29)  # Berlin: 02:00 → 03:00

    assert offset_text("Europe/Berlin", change, time(1, 30)) == "UTC+1"
    assert offset_text("Europe/Berlin", change, time(3, 30)) == "UTC+2"


@pytest.mark.parametrize("day", [date(2026, 3, 28), date(2026, 3, 29), date(2026, 7, 1)])
def test_the_answer_never_flips_on_a_daylight_saving_date(day: date) -> None:
    """Berlin and Paris always share a clock, London and Lisbon too: still different zones.
    The rule takes no date at all."""
    assert offset_shown("Europe/Berlin", "Europe/Berlin") is False
    assert offset_shown("Europe/Paris", "Europe/Berlin") is True
    assert offset_text("Europe/Paris", day, AT) == offset_text("Europe/Berlin", day, AT)
