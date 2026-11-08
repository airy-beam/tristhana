"""SC-06 domain (spec §3, ADR-0036): the feed window and cap (Q148), the stable UIDs (ADR-0034's
rule-date identity: a moved or swapped occurrence keeps `<class_id>-<rule date>@tristhana`),
the moon UID, `FeedEvent`, and the token format (43 base64url characters, 256 bits).

Assumed shapes: `FeedWindow` holds the window constants as class attributes; `uid_moon(day,
phase)` takes the `MoonDayKind`."""

import secrets
from datetime import UTC, date, datetime
from uuid import UUID

import pytest

from tristhana.domain.calendar_feed import (
    MAX_EVENTS,
    TOKEN_RE,
    FeedEvent,
    FeedWindow,
    uid_class,
    uid_moon,
)
from tristhana.domain.moon import MoonDayKind

CLASS = UUID("0b0e5c1a-6d8e-4f3e-9a51-000000000001")


def test_the_window_is_two_weeks_back_to_eight_ahead_and_a_year_of_moon_days() -> None:
    assert (FeedWindow.CLASSES_BACK, FeedWindow.CLASSES_AHEAD) == (14, 56)
    assert (FeedWindow.MOON_BACK, FeedWindow.MOON_AHEAD) == (30, 365)


def test_the_cap() -> None:
    assert MAX_EVENTS == 2000


def test_a_class_uid_is_the_class_and_its_rule_date() -> None:
    assert uid_class(CLASS, date(2026, 11, 9)) == f"{CLASS}-20261109@tristhana"


def test_the_class_uid_does_not_depend_on_where_the_occurrence_went() -> None:
    """Moved to Saturday or swapped to B: the key (the rule's date) is what names it."""
    key = date(2026, 11, 12)

    assert uid_class(CLASS, key) == uid_class(CLASS, date(2026, 11, 12))
    assert uid_class(CLASS, key) != uid_class(CLASS, date(2026, 11, 13))
    other = UUID("0b0e5c1a-6d8e-4f3e-9a51-000000000002")
    assert uid_class(CLASS, key) != uid_class(other, key)


def test_a_moon_uid_is_stable_and_distinct_per_day() -> None:
    day = date(2025, 1, 13)

    first = uid_moon(day, MoonDayKind.PURNIMA)

    assert first == uid_moon(day, MoonDayKind.PURNIMA)
    assert first.endswith("@tristhana")
    assert first != uid_moon(date(2025, 1, 29), MoonDayKind.AMAVASYA)
    assert first != uid_class(CLASS, day)
    assert all(ch.isascii() and not ch.isspace() for ch in first)


def test_a_feed_event_holds_an_instant_or_a_date() -> None:
    timed = FeedEvent(
        uid=uid_class(CLASS, date(2026, 11, 9)),
        summary="Mysore · Anna",
        description="Ashtanga Almaty",
        location=None,
        start=datetime(2026, 11, 9, 1, 0, tzinfo=UTC),
        end=datetime(2026, 11, 9, 3, 30, tzinfo=UTC),
        all_day=False,
    )
    moon = FeedEvent(
        uid=uid_moon(date(2026, 11, 24), MoonDayKind.PURNIMA),
        summary="🌕 Full moon (Purnima)",
        description="…",
        location=None,
        start=date(2026, 11, 24),
        end=date(2026, 11, 25),
        all_day=True,
    )

    assert (timed.all_day, moon.all_day) == (False, True)
    assert timed == FeedEvent(**{f: getattr(timed, f) for f in timed.__dataclass_fields__})


def test_a_real_token_matches_the_format() -> None:
    for _ in range(50):
        assert TOKEN_RE.fullmatch(secrets.token_urlsafe(32))


@pytest.mark.parametrize(
    "token",
    [
        "",
        "short",
        "A" * 42,
        "A" * 44,
        "A" * 42 + "+",
        "A" * 42 + "/",
        "A" * 42 + "=",
        "A" * 42 + ".",
        "\u0410" * 43,  # a Cyrillic capital A
        "A" * 42 + "\n",
        "../../../../etc/passwd/xxxxxxxxxxxxxxxxxxxx",
    ],
    ids=lambda t: repr(t)[:16],
)
def test_malformed_tokens_do_not_match(token: str) -> None:
    assert TOKEN_RE.fullmatch(token) is None


def test_the_alphabet_is_base64url() -> None:
    assert TOKEN_RE.fullmatch("aZ09-_" * 7 + "x")
