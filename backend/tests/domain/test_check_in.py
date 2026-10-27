"""After-practice check-in (PR-06, ADR-0024): the scales, the tag vocabulary and when the
one-tap mood row is offered. Pure: no I/O, "today" is passed in.

`tristhana.domain.check_in` is imported inside the tests (test-first: the rest of the suite
keeps collecting before the module exists)."""

from dataclasses import replace
from datetime import date, timedelta
from typing import Any

import pytest

TODAY = date(2026, 10, 19)

BODY = ["stiff", "open", "strong", "light", "heavy", "sore"]
MIND = ["focused", "calm", "scattered", "steady_breath"]


def _m() -> Any:
    from tristhana.domain import check_in

    return check_in


def _c(**values: Any) -> Any:
    """A CheckIn; `tags` given as keys."""
    m = _m()
    tags = values.pop("tags", ())
    return m.CheckIn(**values, tags=frozenset(m.CheckInTag(t) for t in tags))


# The scales: each optional, 1..5


def test_the_scale_is_one_to_five_and_the_row_covers_two_days() -> None:
    m = _m()

    assert list(m.SCALE) == [1, 2, 3, 4, 5]
    assert m.OFFER_DAYS == 2


@pytest.mark.parametrize("field", ["mood", "energy", "effort"])
@pytest.mark.parametrize("value", [None, 1, 5])
def test_each_scale_accepts_none_and_its_bounds(field: str, value: int | None) -> None:
    check_in = replace(_c(), **{field: value})

    assert _m().check_check_in(check_in) == check_in


@pytest.mark.parametrize("field", ["mood", "energy", "effort"])
@pytest.mark.parametrize("value", [0, 6, -1])
def test_each_scale_rejects_out_of_range(field: str, value: int) -> None:
    m = _m()

    with pytest.raises(m.InvalidCheckIn):
        m.check_check_in(replace(_c(), **{field: value}))


def test_only_slot_one_for_now() -> None:
    m = _m()

    with pytest.raises(m.InvalidCheckIn):
        m.check_check_in(_c(mood=3, slot=2))


def test_an_unknown_tag_is_rejected() -> None:
    m = _m()

    with pytest.raises(m.InvalidCheckIn):
        m.check_check_in(m.CheckIn(tags=frozenset({"sleepy"})))


def test_invalid_check_in_is_a_value_error() -> None:
    assert issubclass(_m().InvalidCheckIn, ValueError)


def test_every_field_is_optional_and_defaults_to_nothing() -> None:
    check_in = _m().CheckIn()

    assert (check_in.mood, check_in.energy, check_in.effort) == (None, None, None)
    assert check_in.tags == frozenset()
    assert check_in.slot == 1


@pytest.mark.parametrize(
    ("values", "empty"),
    [
        ({}, True),
        ({"slot": 1}, True),
        ({"mood": 1}, False),
        ({"energy": 5}, False),
        ({"effort": 3}, False),
        ({"tags": ["calm"]}, False),
    ],
)
def test_is_empty_means_no_scale_and_no_tag(values: dict[str, Any], empty: bool) -> None:
    assert _c(**values).is_empty() is empty


def test_check_ins_are_immutable_values() -> None:
    a = _c(mood=4, tags=["light", "calm"])
    b = _c(mood=4, tags=["calm", "light"])

    assert a == b
    assert hash(a) == hash(b)
    with pytest.raises(AttributeError):
        a.mood = 5


# The tags: body first, then mind (ashtanga-expert's final list)


def test_tag_display_order_is_body_then_mind() -> None:
    assert [t.value for t in _m().CheckInTag] == BODY + MIND


def test_every_tag_has_a_group_and_the_groups_split_six_and_four() -> None:
    m = _m()

    assert set(m.TAG_GROUPS) == set(m.CheckInTag)
    assert set(m.TAG_GROUPS.values()) == {"body", "mind"}
    assert [t.value for t in m.CheckInTag if m.TAG_GROUPS[t] == "body"] == BODY
    assert [t.value for t in m.CheckInTag if m.TAG_GROUPS[t] == "mind"] == MIND


def test_no_pain_injury_bandha_or_drishti_tags() -> None:
    keys = {t.value for t in _m().CheckInTag}

    assert not keys & {"pain", "injury", "injured", "bandha", "drishti", "sleepy"}


# The mood row: today or yesterday, setting on, no check-in yet


@pytest.mark.parametrize(
    ("back", "offered"),
    [
        (0, True),  # today
        (1, True),  # yesterday
        (2, False),
        (30, False),  # a backfilled day: only ✨ Check-in
        (-1, False),  # never ahead of the caller's today
    ],
)
def test_the_mood_row_is_for_today_and_yesterday_only(back: int, offered: bool) -> None:
    day = TODAY - timedelta(days=back)

    assert _m().offer_mood_row(day, TODAY, None, True) is offered


def test_no_mood_row_with_the_setting_off() -> None:
    m = _m()

    assert m.offer_mood_row(TODAY, TODAY, None, False) is False
    assert m.offer_mood_row(TODAY - timedelta(days=1), TODAY, None, False) is False


def test_no_mood_row_once_a_check_in_exists() -> None:
    m = _m()

    assert m.offer_mood_row(TODAY, TODAY, _c(mood=4), True) is False
    assert m.offer_mood_row(TODAY, TODAY, _c(tags=["sore"]), True) is False


def test_an_empty_check_in_counts_as_none() -> None:
    m = _m()

    assert m.offer_mood_row(TODAY, TODAY, _c(), True) is True
    assert m.offer_mood_row(TODAY - timedelta(days=1), TODAY, _c(), True) is True
