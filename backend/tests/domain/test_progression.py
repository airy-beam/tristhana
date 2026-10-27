from datetime import date
from functools import cache

import pytest

from tests.domain.test_practice import catalog
from tristhana.domain.practice import (
    FULL_PRIMARY,
    SHORT,
    Practice,
    PracticeContext,
    PracticeLength,
)
from tristhana.domain.progression import (
    STANDING_ONLY,
    Celebration,
    CelebrationKind,
    Earlier,
    EventKind,
    InvalidProgression,
    NotForward,
    Position,
    Progression,
    ProgressionNotSet,
    Track,
    celebrations,
    check_given,
    from_length,
    given_change,
    item_change,
    last_asana,
    my_presets,
    past_last,
    set_change,
    shows_traditional,
    suggest_start,
)

ON = date(2026, 10, 27)
K = CelebrationKind


@cache
def track() -> Track:
    return Track(catalog())


def P(series: str, key: str) -> Position:
    return Position(series, key)


def prog(series: str | None = None, key: str | None = None, **kw: object) -> Progression:
    return Progression(Position(series, key), **kw)  # type: ignore[arg-type]


def L(*series: str, end: str | None = None, part: str | None = None) -> PracticeLength:
    return PracticeLength(series, end, part)  # type: ignore[arg-type]


def practiced(length: PracticeLength, context: PracticeContext | None = None) -> Practice:
    return Practice(context=context, length=length)


SETU = P("primary", "setu-bandhasana")
NAVASANA = P("primary", "navasana")
PASASANA = P("intermediate", "pasasana")


# Track


def test_next_crosses_into_the_next_series() -> None:
    t = track()
    assert t.next(STANDING_ONLY) == P("primary", "utthita-hasta-padangusthasana")
    assert t.next(SETU) == PASASANA
    assert t.next(P("intermediate", "laghu-vajrasana")) == P("intermediate", "kapotasana-b")


def test_next_is_none_at_the_end_of_advanced_b_and_on_stale_keys() -> None:
    t = track()
    assert t.next(P("advanced-b", "omkarasana")) is None  # Advanced C is pending
    assert t.next(P("primary", "no-such-asana")) is None
    assert t.rank(P("primary", "no-such-asana")) is None


def test_after_lists_the_current_and_next_series_only() -> None:
    later = track().after(NAVASANA)
    assert later[0] == P("primary", "bhujapidasana")
    assert {p.series for p in later} == {"primary", "intermediate"}
    assert {p.series for p in track().after(SETU)} == {"intermediate"}


def test_after_standing_only_is_primary_only() -> None:
    assert {p.series for p in track().after(STANDING_ONLY)} == {"primary"}


def test_items_come_from_the_catalog() -> None:
    assert [i.key for i in track().items] == ["drop-backs", "standing-up", "viparita-chakrasana"]


# Checks


@pytest.mark.parametrize(
    "target",
    [P("primary", "navasana"), P("primary", "marichyasana-c"), STANDING_ONLY],
)
def test_given_must_be_forward(target: Position) -> None:
    with pytest.raises(NotForward):
        check_given(track(), NAVASANA, target)


@pytest.mark.parametrize(
    "target",
    [
        P("primary", "utthita-trikonasana-b"),  # a standing item, not a series stop
        P("intermediate", "kapotasana-a"),  # Kapotasana A, B is one stop after B
        P("advanced-c", "anything"),
    ],
)
def test_given_rejects_non_stops(target: Position) -> None:
    with pytest.raises(InvalidProgression):
        check_given(track(), STANDING_ONLY, target)


def test_set_change_starts_then_changes_and_ignores_the_same_target() -> None:
    first = set_change(track(), None, NAVASANA, ON)
    assert first is not None
    assert first.kind is EventKind.START
    assert first.before is None
    current = prog("primary", "navasana", items=frozenset({"drop-backs"}))
    again = set_change(track(), current, SETU, ON)
    assert again is not None
    assert again.kind is EventKind.CHANGED
    assert again.state.items == {"drop-backs"}
    assert again.before == NAVASANA
    assert set_change(track(), current, NAVASANA, ON) is None


def test_given_needs_a_position() -> None:
    with pytest.raises(ProgressionNotSet):
        given_change(track(), None, NAVASANA, ON)


def test_items_toggle_and_reject_unknown_keys() -> None:
    current = prog("primary", "setu-bandhasana")
    given = item_change(track(), current, "drop-backs", True, ON)
    assert given is not None
    assert given.kind is EventKind.ITEM_GIVEN
    assert given.state.items == {"drop-backs"}
    assert given.state.position == SETU
    assert item_change(track(), given.state, "drop-backs", True, ON) is None
    removed = item_change(track(), given.state, "drop-backs", False, ON)
    assert removed is not None
    assert removed.kind is EventKind.ITEM_REMOVED
    with pytest.raises(InvalidProgression):
        item_change(track(), current, "vrksasana", True, ON)  # optional, not a milestone
    with pytest.raises(ProgressionNotSet):
        item_change(track(), None, "drop-backs", True, ON)


# Per-series view and lengths


def test_lower_series_count_as_full() -> None:
    current = prog("intermediate", "kapotasana-b")
    assert last_asana(track(), current, "primary") == "setu-bandhasana"
    assert last_asana(track(), current, "intermediate") == "kapotasana-b"
    assert last_asana(track(), current, "advanced-a") is None
    assert last_asana(track(), prog(), "primary") is None


@pytest.mark.parametrize(
    ("length", "position"),
    [
        (SHORT, STANDING_ONLY),
        (FULL_PRIMARY, SETU),
        (L("primary", end="navasana"), NAVASANA),
        (
            L("primary", "intermediate", part="second_half"),
            P("intermediate", "baddha-hasta-sirsasana-d"),
        ),
        (L("primary", "intermediate", end="pasasana"), PASASANA),
    ],
)
def test_from_length(length: PracticeLength, position: Position) -> None:
    assert from_length(catalog(), length) == position


# Celebrations


def _given(before: Position, after: Position) -> tuple[Celebration, ...]:
    change = given_change(track(), Progression(before), after, ON)
    return celebrations(track(), Earlier(frozenset({before})), change)


def test_a_new_asana_celebrates() -> None:
    assert _given(NAVASANA, P("primary", "bhujapidasana")) == (
        Celebration(K.NEW_ASANA, "primary", "bhujapidasana"),
    )


def test_completing_a_series_and_beginning_the_next() -> None:
    before = P("primary", "urdhva-mukha-paschimottanasana")
    assert _given(before, SETU) == (
        Celebration(K.NEW_ASANA, "primary", "setu-bandhasana"),
        Celebration(K.SERIES_COMPLETE, "primary"),
    )
    assert _given(SETU, PASASANA) == (
        Celebration(K.NEW_ASANA, "intermediate", "pasasana"),
        Celebration(K.SERIES_BEGINS, "intermediate"),
    )
    assert _given(STANDING_ONLY, P("primary", "utthita-hasta-padangusthasana"))[1] == (
        Celebration(K.SERIES_BEGINS, "primary")
    )


def test_a_jump_over_several_stops_names_the_first_new_one() -> None:
    got = _given(P("primary", "marichyasana-c"), NAVASANA)
    assert got == (
        Celebration(K.NEW_ASANA, "primary", "navasana", first=P("primary", "marichyasana-d")),
    )
    crossing = _given(P("primary", "ubhaya-padangusthasana"), PASASANA)
    assert [c.kind for c in crossing] == [K.NEW_ASANA, K.SERIES_COMPLETE, K.SERIES_BEGINS]


def test_a_jump_across_series_keeps_the_first_stops_series() -> None:
    got = _given(NAVASANA, P("intermediate", "krounchasana"))
    assert got[0].first == P("primary", "bhujapidasana")


def test_given_again_after_a_change_back_is_quiet() -> None:
    # Was at Kapotasana, changed back to full Primary (injury), Pasasana given again.
    earlier = Earlier(frozenset({P("intermediate", "kapotasana-b"), SETU}))
    change = given_change(track(), Progression(SETU), PASASANA, ON)
    assert celebrations(track(), earlier, change) == ()


def test_only_the_stops_past_the_peak_count() -> None:
    earlier = Earlier(frozenset({P("intermediate", "pasasana"), P("primary", "navasana")}))
    change = given_change(track(), Progression(NAVASANA), P("intermediate", "bhekasana"), ON)
    got = celebrations(track(), earlier, change)
    # Pasasana was held before: no "Intermediate begins", no "full Primary".
    assert got == (
        Celebration(
            K.NEW_ASANA, "intermediate", "bhekasana", first=P("intermediate", "krounchasana")
        ),
    )


def test_start_and_changed_never_celebrate() -> None:
    start = set_change(track(), None, SETU, ON)
    changed = set_change(track(), Progression(NAVASANA), PASASANA, ON)
    assert start is not None
    assert changed is not None
    assert celebrations(track(), Earlier(), start) == ()
    assert celebrations(track(), Earlier(frozenset({NAVASANA})), changed) == ()


def test_an_item_celebrates_the_first_time_only() -> None:
    change = item_change(track(), Progression(SETU), "standing-up", True, ON)
    assert change is not None
    assert celebrations(track(), Earlier(), change) == (Celebration(K.ITEM, key="standing-up"),)
    assert celebrations(track(), Earlier(items=frozenset({"standing-up"})), change) == ()


def test_a_stale_peak_is_ignored() -> None:
    earlier = Earlier(frozenset({NAVASANA, P("intermediate", "renamed-asana")}))
    got = _given(NAVASANA, P("primary", "bhujapidasana"))
    change = given_change(track(), Progression(NAVASANA), P("primary", "bhujapidasana"), ON)
    assert celebrations(track(), earlier, change) == got


# Presets


def _mine(series: str, key: str, recent: list[Practice] | None = None) -> list[PracticeLength]:
    return list(my_presets(track(), prog(series, key), recent or []))


def test_primary_gives_one_preset() -> None:
    assert _mine("primary", "navasana") == []  # = ½ Primary (static)
    assert _mine("primary", "kurmasana") == [L("primary", end="kurmasana")]
    assert _mine("primary", "setu-bandhasana") == []  # = Full Primary (static)


def test_early_intermediate_has_no_split() -> None:
    assert _mine("intermediate", "bakasana-b") == [L("primary", "intermediate", end="bakasana-b")]


def test_intermediate_split_at_pincha_or_after_a_recent_intermediate_alone() -> None:
    assert _mine("intermediate", "pincha-mayurasana") == [
        L("primary", "intermediate", end="pincha-mayurasana"),
        L("intermediate", end="pincha-mayurasana"),
    ]
    recent = [practiced(L("intermediate", end="ustrasana"))]
    assert _mine("intermediate", "bakasana-b", recent)[1] == L("intermediate", end="bakasana-b")
    half = [practiced(L("primary", "intermediate", part="second_half"))]
    assert len(_mine("intermediate", "bakasana-b", half)) == 1  # not Intermediate alone


def test_advanced_a_presets_never_include_primary() -> None:
    assert _mine("advanced-a", "galavasana") == [
        L("intermediate", "advanced-a", end="galavasana"),
        L("advanced-a", end="galavasana"),
    ]
    assert _mine("advanced-a", "eka-pada-raja-kapotasana") == [
        L("intermediate", "advanced-a"),
        L("advanced-a"),
    ]


def test_no_presets_when_unset_standing_only_or_stale() -> None:
    assert my_presets(track(), None, []) == ()
    assert my_presets(track(), prog(), []) == ()
    assert my_presets(track(), prog("primary", "renamed"), []) == ()


# "New asana?" question


@pytest.mark.parametrize("context", [PracticeContext.MYSORE, PracticeContext.PRIVATE])
def test_asks_after_mysore_and_one_to_one_past_the_last_asana(context: PracticeContext) -> None:
    got = past_last(track(), prog("primary", "navasana"), L("primary", end="kurmasana"), context)
    assert got == P("primary", "kurmasana")


@pytest.mark.parametrize("context", [PracticeContext.SELF, PracticeContext.LED, None])
def test_never_asks_for_self_practice_led_or_no_context(context: PracticeContext | None) -> None:
    length = L("primary", end="kurmasana")
    assert past_last(track(), prog("primary", "navasana"), length, context) is None


@pytest.mark.parametrize(
    "length", [L("primary", end="navasana"), L("primary", end="marichyasana-a"), SHORT, None]
)
def test_never_asks_at_or_before_the_last_asana(length: PracticeLength | None) -> None:
    mysore = PracticeContext.MYSORE
    assert past_last(track(), prog("primary", "navasana"), length, mysore) is None


def test_not_new_holds_until_the_position_changes() -> None:
    mysore, length = PracticeContext.MYSORE, L("primary", end="kurmasana")
    target = P("primary", "kurmasana")
    dismissed = prog("primary", "navasana", last_event_id=5, hint=target, hint_event_id=5)
    assert past_last(track(), dismissed, length, mysore) is None
    farther = L("primary", end="supta-kurmasana")
    assert past_last(track(), dismissed, farther, mysore) == P("primary", "supta-kurmasana")
    moved = prog("primary", "navasana", last_event_id=6, hint=target, hint_event_id=5)
    assert past_last(track(), moved, length, mysore) == target


def test_never_asks_when_unset_or_stale() -> None:
    mysore, length = PracticeContext.MYSORE, L("primary", end="kurmasana")
    assert past_last(track(), None, length, mysore) is None
    assert past_last(track(), prog("primary", "renamed"), length, mysore) is None


# Suggestion and names


def test_suggest_start_uses_the_most_used_non_led_length() -> None:
    led, mysore = PracticeContext.LED, PracticeContext.MYSORE
    recent = [
        practiced(FULL_PRIMARY, led),
        practiced(FULL_PRIMARY, led),
        practiced(L("primary", end="navasana"), mysore),
        practiced(L("primary", end="kurmasana")),
        practiced(L("primary", end="navasana"), mysore),
        practiced(L("no-such-series")),
    ]
    assert suggest_start(catalog(), recent) == NAVASANA
    assert suggest_start(catalog(), [practiced(SHORT)]) == STANDING_ONLY
    assert suggest_start(catalog(), [practiced(FULL_PRIMARY, led)]) is None
    assert suggest_start(catalog(), []) is None


def test_traditional_names_only_up_to_intermediate() -> None:
    shown = [s.slug for s in catalog().series if shows_traditional(s)]
    assert shown == ["primary", "intermediate"]
