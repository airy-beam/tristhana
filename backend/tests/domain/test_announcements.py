from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

import pytest

from tristhana.domain.announcements import (
    PIN_DAYS,
    STALE,
    TEXT_MAX,
    InvalidAnnouncement,
    Send,
    Source,
    SourceKind,
    announcement_key,
    due,
    normalize_text,
    pin_until,
    pinned,
)
from tristhana.domain.notifications import QuietHours

QUIET = QuietHours(time(22), time(7))
NOW = datetime(2026, 11, 9, 0, 30, tzinfo=UTC)  # 05:30 in Almaty (UTC+5)


# --- normalize_text ---------------------------------------------------------------


@pytest.mark.parametrize("raw", ["", "   ", "\n\n\t", "‎‮"])
def test_blank_text_is_none(raw: str) -> None:
    assert normalize_text(raw) is None


def test_limit_counts_code_points_and_an_emoji_counts_as_one() -> None:
    assert normalize_text("a" * TEXT_MAX) == "a" * TEXT_MAX
    assert normalize_text("a" * (TEXT_MAX + 1)) is None
    assert normalize_text("🙏" * TEXT_MAX) == "🙏" * TEXT_MAX


def test_control_chars_are_dropped_and_newlines_kept() -> None:
    assert normalize_text("Mysore\x00 \x07today\r\nclosed\ttoo") == "Mysore today\nclosed too"


def test_bidi_controls_are_dropped() -> None:
    assert normalize_text("a‮b") == "ab"


def test_three_or_more_blank_lines_collapse_to_two() -> None:
    assert normalize_text("a\n\n\n\n\nb") == "a\n\n\nb"
    assert normalize_text("a\n\n\nb") == "a\n\n\nb"


def test_trailing_spaces_and_outer_blank_lines_go() -> None:
    assert normalize_text("\n\n  Led class   \n6:00  \n\n") == "Led class\n6:00"


# --- due --------------------------------------------------------------------------


def test_inside_quiet_hours_across_midnight_it_goes_now_silently() -> None:
    created = NOW - timedelta(minutes=5)
    assert due(NOW, created, "Asia/Almaty", QUIET) == Send(
        silent=True, local_date=date(2026, 11, 9)
    )


def test_outside_quiet_hours_it_goes_now_with_sound() -> None:
    now = datetime(2026, 11, 9, 5, 0, tzinfo=UTC)  # 10:00 in Almaty
    assert due(now, now, "Asia/Almaty", QUIET) == Send(silent=False, local_date=date(2026, 11, 9))


def test_quiet_hours_never_hold_an_announcement() -> None:
    for hour in range(24):
        now = datetime(2026, 11, 9, hour, tzinfo=UTC)
        assert due(now, now - timedelta(minutes=1), "Asia/Almaty", QUIET) is not None


def test_the_end_of_quiet_hours_has_sound() -> None:
    now = datetime(2026, 11, 9, 2, 0, tzinfo=UTC)  # exactly 07:00 in Almaty
    assert due(now, now, "Asia/Almaty", QUIET) == Send(False, date(2026, 11, 9))


def test_the_start_of_quiet_hours_is_silent() -> None:
    now = datetime(2026, 11, 9, 17, 0, tzinfo=UTC)  # exactly 22:00 in Almaty
    assert due(now, now, "Asia/Almaty", QUIET) == Send(True, date(2026, 11, 9))


def test_a_dst_night_uses_the_local_wall_clock() -> None:
    # 2026-03-29 in Berlin: 02:00 jumps to 03:00; 01:30 UTC is 03:30 CEST, still quiet.
    now = datetime(2026, 3, 29, 1, 30, tzinfo=UTC)
    assert due(now, now, "Europe/Berlin", QUIET) == Send(True, date(2026, 3, 29))
    later = datetime(2026, 3, 29, 5, 0, tzinfo=UTC)  # 07:00 CEST
    assert due(later, later, "Europe/Berlin", QUIET) == Send(False, date(2026, 3, 29))


def test_no_zone_goes_now_silently_on_the_utc_date() -> None:
    now = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
    assert due(now, now, None, QUIET) == Send(True, date(2026, 11, 9))


def test_the_recipients_local_date_is_used() -> None:
    now = datetime(2026, 11, 9, 20, 0, tzinfo=UTC)  # 10:00 on both sides of the date line
    assert due(now, now, "Pacific/Kiritimati", QUIET) == Send(False, date(2026, 11, 10))
    assert due(now, now, "Pacific/Honolulu", QUIET) == Send(False, date(2026, 11, 9))


def test_stale_after_24_hours() -> None:
    created = NOW - STALE
    assert due(NOW, created, "Asia/Almaty", QUIET) is None
    assert due(NOW, created + timedelta(seconds=1), "Asia/Almaty", QUIET) is not None


def test_no_quiet_hours_means_always_with_sound() -> None:
    none = QuietHours(time(0), time(0))
    assert due(NOW, NOW, "Asia/Almaty", none) == Send(False, date(2026, 11, 9))


# --- pins, keys, sources ----------------------------------------------------------


def test_pinned_at_the_boundary() -> None:
    assert pinned(None, NOW) is False
    assert pinned(NOW + timedelta(seconds=1), NOW) is True
    assert pinned(NOW, NOW) is False


def test_pin_until() -> None:
    assert frozenset({7, 30}) == PIN_DAYS
    assert pin_until(NOW, 0) is None
    assert pin_until(NOW, 7) == NOW + timedelta(days=7)
    assert pin_until(NOW, 30) == NOW + timedelta(days=30)
    with pytest.raises(InvalidAnnouncement):
        pin_until(NOW, 14)


def test_the_key_format() -> None:
    uid = UUID("12345678-1234-5678-1234-567812345678")
    assert announcement_key(uid) == "ann:12345678-1234-5678-1234-567812345678"


def test_source_kinds_are_short() -> None:
    uid = UUID(int=1)
    assert Source(SourceKind.TEACHER, uid).kind == "t"
    assert Source(SourceKind.SHALA, uid).kind == "h"
