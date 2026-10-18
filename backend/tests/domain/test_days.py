from datetime import UTC, date, datetime

import pytest

from tristhana.domain.days import (
    MAX_RANGE_DAYS,
    DateInFuture,
    DateTooEarly,
    DayStatus,
    InvalidRange,
    check_loggable,
    check_range,
    latest_loggable,
    local_today,
    provisional_zone,
    public_status,
)


def test_only_ladies_holiday_is_projected() -> None:
    assert public_status(DayStatus.LADIES) is DayStatus.REST
    for status in DayStatus:
        if status is not DayStatus.LADIES:
            assert public_status(status) is status


@pytest.mark.parametrize(
    ("utc", "zone", "expected"),
    [
        # 18:59 UTC is 23:59 in Almaty (UTC+5); 19:00 UTC is already the next day.
        (datetime(2026, 10, 18, 18, 59, tzinfo=UTC), "Asia/Almaty", date(2026, 10, 18)),
        (datetime(2026, 10, 18, 19, 0, tzinfo=UTC), "Asia/Almaty", date(2026, 10, 19)),
        (datetime(2026, 10, 18, 18, 29, tzinfo=UTC), "Asia/Kolkata", date(2026, 10, 18)),
        (datetime(2026, 10, 18, 18, 30, tzinfo=UTC), "Asia/Kolkata", date(2026, 10, 19)),
        (datetime(2026, 10, 18, 18, 15, tzinfo=UTC), "Asia/Kathmandu", date(2026, 10, 19)),
        (datetime(2026, 10, 18, 18, 14, tzinfo=UTC), "Asia/Kathmandu", date(2026, 10, 18)),
    ],
)
def test_local_today_turns_over_at_local_midnight(utc: datetime, zone: str, expected: date) -> None:
    assert local_today(utc, zone) == expected


@pytest.mark.parametrize(("locale", "zone"), [("ru", "Europe/Moscow"), ("en", "UTC")])
def test_provisional_zone_from_locale(locale: str, zone: str) -> None:
    assert provisional_zone(locale) == zone  # type: ignore[arg-type]


def test_latest_loggable_without_a_zone_is_the_latest_date_on_earth() -> None:
    # 10:00 UTC is already 00:00 the next day in Kiritimati (UTC+14).
    now = datetime(2026, 10, 18, 10, 0, tzinfo=UTC)

    assert latest_loggable(now, None) == date(2026, 10, 19)
    assert latest_loggable(now, "Asia/Almaty") == date(2026, 10, 18)


def test_check_loggable() -> None:
    now = datetime(2026, 10, 18, 6, 0, tzinfo=UTC)

    check_loggable(date(2026, 10, 18), now, "Asia/Almaty")
    check_loggable(date(2000, 1, 1), now, "Asia/Almaty")
    with pytest.raises(DateInFuture):
        check_loggable(date(2026, 10, 19), now, "Asia/Almaty")
    with pytest.raises(DateTooEarly):
        check_loggable(date(1999, 12, 31), now, "Asia/Almaty")


def test_check_range() -> None:
    start = date(2026, 1, 1)
    check_range(start, start)
    check_range(start, date.fromordinal(start.toordinal() + MAX_RANGE_DAYS - 1))
    with pytest.raises(InvalidRange):
        check_range(start, date.fromordinal(start.toordinal() + MAX_RANGE_DAYS))
    with pytest.raises(InvalidRange):
        check_range(date(2026, 1, 2), start)
