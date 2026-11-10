"""ID-05, the pure rules (spec §3, §4; ADR-0042): cleaning the form, what a save does in each
state, the 24 h rule, and the mark that crosses accounts."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from tristhana.domain.directory_listing import (
    NAME_MAX,
    NOTE_MAX,
    REGION_MAX,
    RESEND_AFTER,
    DeclaredLevel,
    Details,
    InvalidListing,
    Listing,
    ListingMark,
    ListingStatus,
    ListingWait,
    Step,
    clean,
    mark_of,
    may_decide,
    next_state,
    wait_left,
)

T0 = datetime(2026, 11, 11, 6, 0, tzinfo=UTC)
ANNA = Details("Anna Petrova", "Russia", DeclaredLevel.AUTHORISED_2, None)


def _listing(status: ListingStatus, **changes: object) -> Listing:
    withdrawn = status is ListingStatus.WITHDRAWN
    base = Listing(
        status=status,
        name_as_listed=None if withdrawn else "Anna Petrova",
        region=None if withdrawn else "Russia",
        level=None if withdrawn else DeclaredLevel.AUTHORISED_2,
        note=None,
        revision=1,
        requested_at=T0,
        checked_on=date(2026, 11, 11) if status is ListingStatus.LISTED else None,
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def test_the_spec_numbers() -> None:
    assert (NAME_MAX, REGION_MAX, NOTE_MAX) == (100, 60, 300)
    assert timedelta(hours=24) == RESEND_AFTER


def test_levels_are_the_four_terms() -> None:
    assert [level.value for level in DeclaredLevel] == [
        "authorised",
        "authorised-1",
        "authorised-2",
        "certified",
    ]


def test_clean_trims_and_single_spaces() -> None:
    found = clean("  Anna \t Petrova\n", " Russia ", "certified", "  site  in the  directory ")
    assert found == Details(
        "Anna Petrova", "Russia", DeclaredLevel.CERTIFIED, "site in the directory"
    )


def test_clean_strips_bidi_and_control_characters() -> None:
    assert clean("‮Anna‏ Petrova\x00", "Russia", None, None).name_as_listed == ("Anna Petrova")


def test_clean_blank_level_and_note_are_none() -> None:
    found = clean("Anna", "Russia", "", "   ")
    assert (found.level, found.note) == (None, None)


@pytest.mark.parametrize(
    ("name", "region", "level", "note"),
    [
        ("", "Russia", None, None),
        ("  ‏ ", "Russia", None, None),
        ("Anna", "", None, None),
        (None, "Russia", None, None),
        ("a" * (NAME_MAX + 1), "Russia", None, None),
        ("Anna", "r" * (REGION_MAX + 1), None, None),
        ("Anna", "Russia", None, "n" * (NOTE_MAX + 1)),
        ("Anna", "Russia", "level-3", None),
        ("Anna", "Russia", "Certified", None),
    ],
)
def test_clean_refuses(
    name: str | None, region: str | None, level: str | None, note: str | None
) -> None:
    with pytest.raises(InvalidListing):
        clean(name, region, level, note)


def test_clean_keeps_the_longest_allowed_values() -> None:
    found = clean("a" * NAME_MAX, "r" * REGION_MAX, None, "n" * NOTE_MAX)
    assert len(found.name_as_listed) == NAME_MAX
    assert len(found.note or "") == NOTE_MAX


def test_invalid_listing_carries_no_value() -> None:
    with pytest.raises(InvalidListing) as caught:
        clean("Anna Secret", "", None, None)
    assert "Anna" not in str(caught.value)
    assert caught.value.args == ()


def test_a_first_request_is_a_send() -> None:
    assert next_state(None, ANNA, T0) is Step.SEND


@pytest.mark.parametrize("status", [ListingStatus.NOT_FOUND, ListingStatus.WITHDRAWN])
def test_sending_again_waits_a_day(status: ListingStatus) -> None:
    current = _listing(status)
    with pytest.raises(ListingWait) as caught:
        next_state(current, ANNA, T0 + timedelta(hours=23, minutes=59))
    assert caught.value.wait == timedelta(minutes=1)
    assert next_state(current, ANNA, T0 + RESEND_AFTER) is Step.SEND


def test_a_waiting_request_is_edited_in_place_any_time() -> None:
    current = _listing(ListingStatus.PENDING)
    other = replace(ANNA, name_as_listed="Anna Petrova-Smith")
    assert next_state(current, other, T0 + timedelta(minutes=1)) is Step.EDIT


def test_a_level_only_change_stays_listed() -> None:
    current = _listing(ListingStatus.LISTED)
    changed = replace(ANNA, level=DeclaredLevel.CERTIFIED, note="ignored")
    assert next_state(current, changed, T0 + timedelta(minutes=1)) is Step.LEVEL_ONLY


@pytest.mark.parametrize("field", ["name_as_listed", "region"])
def test_a_listed_name_or_region_change_is_checked_again(field: str) -> None:
    current = _listing(ListingStatus.LISTED)
    changed = replace(ANNA, **{field: "Other"})
    assert next_state(current, changed, T0 + RESEND_AFTER) is Step.RECHECK


def test_a_recheck_also_waits_a_day_since_the_last_send() -> None:
    current = _listing(ListingStatus.LISTED)
    with pytest.raises(ListingWait):
        next_state(current, replace(ANNA, region="Kazakhstan"), T0 + timedelta(hours=1))


def test_wait_left() -> None:
    assert wait_left(None, T0) is None
    current = _listing(ListingStatus.NOT_FOUND)
    assert wait_left(current, T0 + timedelta(hours=20)) == timedelta(hours=4)
    assert wait_left(current, T0 + RESEND_AFTER) is None


def test_mark_only_for_a_listed_row() -> None:
    listed = _listing(ListingStatus.LISTED)
    assert mark_of(listed) == ListingMark(
        "Anna Petrova", date(2026, 11, 11), DeclaredLevel.AUTHORISED_2
    )
    for status in (ListingStatus.PENDING, ListingStatus.NOT_FOUND, ListingStatus.WITHDRAWN):
        assert mark_of(_listing(status)) is None
    assert mark_of(None) is None


def test_mark_carries_exactly_three_fields() -> None:
    assert ListingMark.__slots__ == ("name_as_listed", "checked_on", "level")


def test_may_decide() -> None:
    assert may_decide(_listing(ListingStatus.PENDING))
    assert may_decide(_listing(ListingStatus.LISTED))
    assert not may_decide(_listing(ListingStatus.NOT_FOUND))
    assert not may_decide(_listing(ListingStatus.WITHDRAWN))
