"""The daily practice reminder (PR-10): when it is due, what it skips, the long-silence pause."""

from dataclasses import replace
from datetime import date, datetime, time, timedelta

import pytest

from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.domain.notifications import (
    DEFAULTS,
    GRACE,
    PRACTICE_TIMES,
    UNANSWERED_LIMIT,
    WEEKDAYS,
    Candidate,
    DayOffQuestion,
    InvalidSettings,
    NotificationSettings,
    PracticeReminders,
    StoredSettings,
    check_settings,
    day_off_question,
    default_practice_time,
    defaults_for,
    due_practice_reminder,
    effective,
    pause_key,
    practice_key,
    reminder_days,
    send_instant,
)

ZONE = "Asia/Almaty"
MON = date(2026, 10, 19)  # a Monday
SAT = date(2026, 10, 24)
EVERY_DAY = frozenset(range(1, 8))


def _settings(
    on: bool | None = True,
    at: time = time(10),
    days: frozenset[int] = EVERY_DAY,
    cap: int = 3,
) -> NotificationSettings:
    return NotificationSettings(DEFAULTS.moon, DEFAULTS.quiet, cap, PracticeReminders(on, at, days))


def _c(settings: NotificationSettings | None = None, **kw: object) -> Candidate:
    return Candidate(ZONE, settings or _settings(), (), **kw)  # type: ignore[arg-type]


def _at(day: date, at: time = time(10), zone: str = ZONE) -> datetime:
    return send_instant(day, at, zone)


def test_defaults_never_chosen_ten_am_sunday_to_friday() -> None:
    assert DEFAULTS.practice == PracticeReminders(None, time(10), frozenset({1, 2, 3, 4, 5, 7}))
    assert not DEFAULTS.practice.on
    assert tuple(time(h) for h in (9, 10, 12, 18, 20, 21)) == PRACTICE_TIMES


@pytest.mark.parametrize(
    ("tapped", "expected"),
    [(time(6, 40), time(10)), (time(13, 59), time(10)), (time(14), time(20)), (time(21), time(20))],
)
def test_default_time_follows_when_the_offer_was_accepted(tapped: time, expected: time) -> None:
    assert default_practice_time(tapped) == expected


def test_due_at_the_time_on_the_day() -> None:
    due = due_practice_reminder(_at(MON) + timedelta(minutes=9), _c())

    assert due is not None
    assert (due.key, due.local_date, due.pause) == (practice_key(MON), MON, False)
    assert due.key == "practice:2026-10-19"


@pytest.mark.parametrize(
    "now", [_at(MON) - timedelta(minutes=1), _at(MON) + GRACE, _at(MON) + timedelta(hours=5)]
)
def test_not_due_outside_the_window(now: datetime) -> None:
    assert due_practice_reminder(now, _c()) is None


@pytest.mark.parametrize("on", [None, False])
def test_off_or_never_chosen(on: bool | None) -> None:
    assert due_practice_reminder(_at(MON), _c(_settings(on=on))) is None


def test_skips_a_weekday_that_is_off() -> None:
    sun_to_fri = frozenset({1, 2, 3, 4, 5, 7})

    assert due_practice_reminder(_at(SAT), _c(_settings(days=sun_to_fri))) is None
    assert due_practice_reminder(_at(MON), _c(_settings(days=sun_to_fri))) is not None


def test_skips_a_logged_day() -> None:
    assert due_practice_reminder(_at(MON), _c(logged=frozenset({MON}))) is None


def test_skips_a_moon_day_of_the_followed_calendar() -> None:
    c = Candidate(ZONE, _settings(), (MoonDay(MON, MoonDayKind.PURNIMA),))

    assert due_practice_reminder(_at(MON), c) is None


def test_skips_a_key_already_sent() -> None:
    assert due_practice_reminder(_at(MON), _c(sent_keys=frozenset({practice_key(MON)}))) is None


def test_quiet_hours_win() -> None:
    late = _settings(at=time(21, 45))  # quiet hours 22-07: 22:10 is inside

    assert due_practice_reminder(_at(MON, time(22, 10)), _c(late)) is None


def test_the_daily_cap_is_shared_with_moon_reminders() -> None:
    capped = _settings(cap=2)

    assert due_practice_reminder(_at(MON), _c(capped, sent_today=1)) is not None
    assert due_practice_reminder(_at(MON), _c(capped, sent_today=1), picked=1) is None


def test_a_late_slot_crossing_midnight_is_about_the_day_it_belongs_to() -> None:
    no_quiet = replace(_settings(at=time(23, 30)), quiet=replace(DEFAULTS.quiet, end=time(22)))
    after_midnight = _at(MON, time(23, 30)) + timedelta(hours=1)

    due = due_practice_reminder(after_midnight, _c(no_quiet))

    assert due is not None
    assert due.local_date == MON


@pytest.mark.parametrize(
    ("zone", "utc_hour", "utc_minute"),
    [("Asia/Kolkata", 4, 30), ("Asia/Kathmandu", 4, 15), ("Pacific/Kiritimati", 20, 0)],
)
def test_odd_offsets(zone: str, utc_hour: int, utc_minute: int) -> None:
    send = _at(MON, zone=zone)
    c = Candidate(zone, _settings(), ())

    assert (send.hour, send.minute) == (utc_hour, utc_minute)
    due = due_practice_reminder(send, c)
    assert due is not None
    assert due.local_date == MON


def test_berlin_dst_keeps_the_wall_clock() -> None:
    before, after = date(2026, 10, 24), date(2026, 10, 26)  # clocks go back on the 25th
    c = Candidate("Europe/Berlin", _settings(), ())

    assert _at(before, zone="Europe/Berlin").hour == 8
    assert _at(after, zone="Europe/Berlin").hour == 9
    assert due_practice_reminder(_at(after, zone="Europe/Berlin"), c) is not None


def _silence(n: int, answered: frozenset[date] = frozenset()) -> Candidate:
    """`n` reminders sent on the n days before MON, none of them answered unless listed."""
    sent = tuple(MON - timedelta(days=i) for i in range(n, 0, -1))
    return _c(
        sent_keys=frozenset(practice_key(d) for d in sent),
        practice_sent=sent,
        logged=answered,
    )


def test_after_ten_unanswered_reminders_the_next_one_is_the_pause_note() -> None:
    due = due_practice_reminder(_at(MON), _silence(UNANSWERED_LIMIT))

    assert UNANSWERED_LIMIT == 10
    assert due is not None
    assert due.pause


def test_nine_unanswered_is_still_a_reminder() -> None:
    due = due_practice_reminder(_at(MON), _silence(UNANSWERED_LIMIT - 1))

    assert due is not None
    assert not due.pause


def test_one_answer_breaks_the_silence() -> None:
    answered = frozenset({MON - timedelta(days=3)})

    due = due_practice_reminder(_at(MON), _silence(UNANSWERED_LIMIT + 2, answered))

    assert due is not None
    assert not due.pause


def test_settings_checks() -> None:
    check_settings(_settings())
    check_settings(_settings(on=False, at=time(23)))  # off: quiet hours don't matter
    for bad in (
        _settings(days=frozenset()),
        _settings(days=frozenset({0, 1})),
        _settings(at=time(10, 5)),
        _settings(at=time(23)),
    ):
        with pytest.raises(InvalidSettings):
            check_settings(bad)


def test_turning_back_on_after_the_pause_note_starts_a_fresh_count() -> None:
    sent = tuple(MON - timedelta(days=i) for i in range(UNANSWERED_LIMIT, 0, -1))
    note = MON  # the pause note went out instead of MON's reminder
    tue = MON + timedelta(days=1)
    c = _c(
        sent_keys=frozenset({*(practice_key(d) for d in sent), pause_key(note)}),
        practice_sent=sent,
        practice_paused=(note,),
    )

    assert due_practice_reminder(_at(MON), c) is None  # the note counts as MON's message
    due = due_practice_reminder(_at(tue), c)
    assert due is not None
    assert (due.key, due.pause) == (practice_key(tue), False)


def test_the_pause_note_has_its_own_key() -> None:
    due = due_practice_reminder(_at(MON), _silence(UNANSWERED_LIMIT))

    assert due is not None
    assert due.key == pause_key(MON) == "practice-pause:2026-10-19"


def test_berlin_spring_forward_keeps_the_wall_clock() -> None:
    before, after = date(2026, 3, 28), date(2026, 3, 30)  # clocks go forward on the 29th
    c = Candidate("Europe/Berlin", _settings(), ())

    assert _at(before, zone="Europe/Berlin").hour == 9
    assert _at(after, zone="Europe/Berlin").hour == 8
    assert due_practice_reminder(_at(after, zone="Europe/Berlin"), c) is not None


# PR-09: reminder days follow the weekly day off; the one-time day-off question.


def test_reminder_days_follow_the_day_off() -> None:
    assert reminder_days(None) == frozenset({1, 2, 3, 4, 5, 7})  # never chosen: Sat off
    assert reminder_days(frozenset()) == WEEKDAYS
    assert reminder_days(frozenset({7})) == frozenset({1, 2, 3, 4, 5, 6})


def test_reminder_days_are_always_the_practice_days() -> None:
    sunday_off = defaults_for(frozenset({7}))
    assert effective(StoredSettings(), sunday_off).practice.days == frozenset({1, 2, 3, 4, 5, 6})
    weekend_off = defaults_for(frozenset({6, 7}))
    assert effective(StoredSettings(), weekend_off).practice.days == frozenset({1, 2, 3, 4, 5})
    assert defaults_for(None) is DEFAULTS


def _question(
    days_off: frozenset[int] | None, dismissed: bool, days: set[int], on: bool
) -> DayOffQuestion | None:
    practice = replace(DEFAULTS.practice, on=on, days=frozenset(days))
    return day_off_question(days_off, dismissed, replace(DEFAULTS, practice=practice))


def test_day_off_question_asks_about_the_one_skipped_weekday() -> None:
    assert _question(None, False, {1, 2, 3, 4, 5, 7}, True) == DayOffQuestion(6, True)
    assert _question(None, False, {1, 2, 3, 4, 6, 7}, False) == DayOffQuestion(5, False)


@pytest.mark.parametrize(
    ("days_off", "dismissed", "days"),
    [
        (frozenset({6}), False, {1, 2, 3, 4, 5, 7}),  # already chosen
        (frozenset[int](), False, {1, 2, 3, 4, 5, 6, 7}),  # chosen: no fixed day off
        (None, True, {1, 2, 3, 4, 5, 7}),  # "Not now"
        (None, False, {1, 2, 3, 4, 5, 6, 7}),  # reminders every day
        (None, False, {1, 2, 3, 4, 5}),  # two gaps
    ],
)
def test_day_off_question_is_skipped(
    days_off: frozenset[int] | None, dismissed: bool, days: set[int]
) -> None:
    assert _question(days_off, dismissed, days, True) is None


def test_an_unlogged_day_off_is_not_logged_for_the_tick() -> None:
    """ADR-0022: auto-rest is never a log, so custom days that include the day off still
    get their reminder."""
    sat = date(2026, 10, 24)
    practice = replace(DEFAULTS.practice, on=True, days=frozenset(range(1, 8)))
    c = Candidate("Asia/Almaty", replace(DEFAULTS, practice=practice), ())
    now = send_instant(sat, practice.at, "Asia/Almaty")
    assert due_practice_reminder(now, c) is not None
