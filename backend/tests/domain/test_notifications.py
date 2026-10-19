from datetime import UTC, date, datetime, time, timedelta

import pytest

from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.domain.notifications import (
    DEFAULTS,
    GRACE,
    Candidate,
    InvalidSettings,
    MoonReminders,
    NotificationSettings,
    QuietHours,
    check_settings,
    due_moon_reminders,
    moon_key,
    send_instant,
)

FULL = MoonDay(date(2026, 11, 5), MoonDayKind.PURNIMA)  # hypothetical dates for the rules
NEW = MoonDay(date(2026, 11, 20), MoonDayKind.AMAVASYA)


def _settings(
    offsets: frozenset[int] = frozenset({7, 3, 1}), at: time = time(19), cap: int = 3
) -> NotificationSettings:
    return NotificationSettings(MoonReminders(frozenset(offsets), at), DEFAULTS.quiet, cap)


def test_defaults_are_seven_and_one_at_seven_pm() -> None:
    assert DEFAULTS.moon.offsets == {7, 1}
    assert DEFAULTS.moon.at == time(19)
    assert (DEFAULTS.quiet, DEFAULTS.daily_cap) == (QuietHours(time(22), time(7)), 3)


@pytest.mark.parametrize(
    ("quiet", "at", "inside"),
    [
        (QuietHours(time(22), time(7)), time(23), True),
        (QuietHours(time(22), time(7)), time(6, 59), True),
        (QuietHours(time(22), time(7)), time(7), False),
        (QuietHours(time(22), time(7)), time(19), False),
        (QuietHours(time(13), time(15)), time(14), True),
        (QuietHours(time(13), time(15)), time(15), False),
        (QuietHours(time(0), time(0)), time(3), False),  # none
    ],
)
def test_quiet_hours(quiet: QuietHours, at: time, inside: bool) -> None:
    assert quiet.contains(at) is inside


@pytest.mark.parametrize(
    ("day", "at", "zone", "utc"),
    [
        (date(2026, 11, 4), time(19), "Asia/Kolkata", datetime(2026, 11, 4, 13, 30, tzinfo=UTC)),
        (date(2026, 11, 4), time(19), "Asia/Kathmandu", datetime(2026, 11, 4, 13, 15, tzinfo=UTC)),
        (date(2026, 3, 28), time(19), "Europe/Berlin", datetime(2026, 3, 28, 18, 0, tzinfo=UTC)),
        (date(2026, 3, 29), time(19), "Europe/Berlin", datetime(2026, 3, 29, 17, 0, tzinfo=UTC)),
        # A wall-clock time inside the spring-forward gap moves forward (02:30 → 03:30).
        (date(2026, 3, 29), time(2, 30), "Europe/Berlin", datetime(2026, 3, 29, 1, 30, tzinfo=UTC)),
    ],
)
def test_send_instant(day: date, at: time, zone: str, utc: datetime) -> None:
    assert send_instant(day, at, zone) == utc


def test_reminders_fire_at_the_local_hour_on_the_right_day() -> None:
    c = Candidate("Asia/Kolkata", _settings(), (FULL,))
    day_before_at_19 = send_instant(date(2026, 11, 4), time(19), "Asia/Kolkata")

    [due] = due_moon_reminders(day_before_at_19, c)

    assert (due.key, due.days_before, due.local_date) == (
        moon_key(FULL.date, 1),
        1,
        date(2026, 11, 4),
    )
    assert due_moon_reminders(day_before_at_19 - timedelta(minutes=1), c) == []
    nine_min_late = due_moon_reminders(day_before_at_19 + timedelta(minutes=9), c)
    assert [d.key for d in nine_min_late] == [moon_key(FULL.date, 1)]


def test_late_reminders_are_dropped_after_the_grace_window() -> None:
    c = Candidate("Asia/Kolkata", _settings(at=time(12)), (FULL,))
    send_at = send_instant(date(2026, 11, 4), time(12), "Asia/Kolkata")

    assert due_moon_reminders(send_at + GRACE - timedelta(minutes=1), c) != []
    assert due_moon_reminders(send_at + GRACE, c) == []


def test_quiet_hours_hold_reminders_back() -> None:
    c = Candidate("Asia/Almaty", _settings(at=time(21), offsets=frozenset({1})), (FULL,))
    send_at = send_instant(date(2026, 11, 4), time(21), "Asia/Almaty")

    assert due_moon_reminders(send_at, c) != []
    assert due_moon_reminders(send_at + timedelta(hours=1, minutes=5), c) == []  # 22:05 local


def test_already_sent_keys_are_skipped() -> None:
    sent = frozenset({moon_key(FULL.date, 1)})
    c = Candidate("Asia/Kolkata", _settings(), (FULL,), sent_keys=sent)

    assert due_moon_reminders(send_instant(date(2026, 11, 4), time(19), "Asia/Kolkata"), c) == []


def test_daily_cap_keeps_the_day_before_first() -> None:
    # Two moon days whose 7-day and 1-day reminders land on the same evening.
    soon = MoonDay(date(2026, 11, 5), MoonDayKind.PURNIMA)
    later = MoonDay(date(2026, 11, 11), MoonDayKind.AMAVASYA)
    c = Candidate("Asia/Kolkata", _settings(cap=1), (soon, later))
    evening = send_instant(date(2026, 11, 4), time(19), "Asia/Kolkata")

    [due] = due_moon_reminders(evening, c)

    assert due.key == moon_key(soon.date, 1)
    assert (
        due_moon_reminders(evening, Candidate(c.zone, c.settings, c.moon_days, sent_today=1)) == []
    )


def test_off_means_nothing() -> None:
    c = Candidate("Asia/Kolkata", _settings(offsets=frozenset()), (FULL,))

    assert due_moon_reminders(send_instant(date(2026, 11, 4), time(19), "Asia/Kolkata"), c) == []


def test_a_moon_day_today_or_past_is_never_reminded() -> None:
    c = Candidate("Asia/Kolkata", _settings(offsets=frozenset({7})), (FULL,))

    assert due_moon_reminders(send_instant(FULL.date, time(19), "Asia/Kolkata"), c) == []


def test_following_mysuru_from_los_angeles_uses_the_mysuru_date_in_la_time() -> None:
    c = Candidate("America/Los_Angeles", _settings(offsets=frozenset({1})), (FULL,))
    la_evening = send_instant(date(2026, 11, 4), time(19), "America/Los_Angeles")

    [due] = due_moon_reminders(la_evening, c)

    assert due.local_date == date(2026, 11, 4)


@pytest.mark.parametrize(
    "settings",
    [
        NotificationSettings(MoonReminders(frozenset({2}), time(19)), DEFAULTS.quiet, 3),
        NotificationSettings(MoonReminders(frozenset({1}), time(19, 5)), DEFAULTS.quiet, 3),
        NotificationSettings(MoonReminders(frozenset({1}), time(19)), DEFAULTS.quiet, 0),
    ],
)
def test_invalid_settings(settings: NotificationSettings) -> None:
    with pytest.raises(InvalidSettings):
        check_settings(settings)


@pytest.mark.parametrize("zone", ["Pacific/Kiritimati", "Pacific/Pago_Pago"])  # UTC+14, UTC-11
def test_date_line_zones(zone: str) -> None:
    c = Candidate(zone, _settings(offsets=frozenset({1})), (FULL,))
    evening = send_instant(date(2026, 11, 4), time(19), zone)

    [due] = due_moon_reminders(evening, c)

    assert due.local_date == date(2026, 11, 4)


def test_a_send_time_inside_quiet_hours_is_refused() -> None:
    late = NotificationSettings(MoonReminders(frozenset({1}), time(22, 30)), DEFAULTS.quiet, 3)

    with pytest.raises(InvalidSettings):
        check_settings(late)
