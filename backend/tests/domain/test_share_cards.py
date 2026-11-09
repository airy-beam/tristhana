"""Share cards (ST-07, ADR-0040): the two-tone projection (Q209), month/year builders, the
asana card's PR-08 precedence, count cards and emptiness."""

from datetime import date
from functools import cache
from pathlib import Path

import pytest

from tristhana.domain.days import DayStatus
from tristhana.domain.progression import STANDING_ONLY, EventKind, Position, ProgressionEvent, Track
from tristhana.domain.share_cards import (
    AsanaCard,
    AsanaVariant,
    CardFormat,
    CardTone,
    CountCard,
    asana_card,
    card_tone,
    count_card,
    is_empty,
    month_card,
    year_card,
)
from tristhana.domain.stats import Summary
from tristhana.infrastructure.seed.practice_catalog import load_practice_catalog

P, N = CardTone.PRACTICE, CardTone.NO_PRACTICE
TODAY = date(2026, 11, 9)


@cache
def track() -> Track:
    seed = Path(__file__).resolve().parents[3] / "data" / "seed"
    return Track(load_practice_catalog(seed).catalog)


def test_formats_have_story_and_square_sizes() -> None:
    assert CardFormat.STORY.size == (1080, 1920)
    assert CardFormat.SQUARE.size == (1080, 1080)


@pytest.mark.parametrize("status", [*DayStatus, None])
def test_only_practiced_is_a_practice_tone(status: DayStatus | None) -> None:
    expected = P if status is DayStatus.PRACTICED else N
    assert card_tone(status) is expected


def test_ladies_holiday_and_plain_rest_look_the_same() -> None:
    lh = [card_tone(s) for s in (DayStatus.PRACTICED, DayStatus.LADIES, DayStatus.LADIES)]
    rest = [card_tone(s) for s in (DayStatus.PRACTICED, DayStatus.REST, None)]
    assert lh == rest


def test_month_card_keeps_practice_figures_only() -> None:
    summary = Summary(
        practiced=3,
        skipped=2,
        rest={DayStatus.LADIES: 3},
        series={0: 1, 2: 1, 1: 1},
        duration_total=200,
        duration_count=2,
    )
    moon = [date(2026, 10, 6), date(2026, 10, 21), date(2026, 11, 5)]
    card = month_card(2026, 10, TODAY, [P, N, P, P], moon, summary)
    assert card.practiced == 3
    assert card.series == (1, 2)  # catalog order, "short" never shown
    assert card.minutes == 200
    assert card.moon_days == frozenset({6, 21})
    assert not card.current
    assert not hasattr(card, "skipped")
    assert not hasattr(card, "rest")


def test_month_card_hides_series_when_only_short_and_time_without_durations() -> None:
    card = month_card(2026, 11, TODAY, [P], [], Summary(practiced=1, series={0: 1}))
    assert card.series == ()
    assert card.minutes is None
    assert card.current


def test_builders_refuse_raw_statuses() -> None:
    with pytest.raises(TypeError):
        month_card(2026, 10, TODAY, [DayStatus.LADIES], [], Summary())  # type: ignore[list-item]
    with pytest.raises(TypeError):
        year_card(2026, TODAY, ["rest"], [], 0)  # type: ignore[list-item]


def test_year_card_current_and_finished() -> None:
    moon = [date(2025, 12, 30), date(2026, 1, 3)]
    current = year_card(2026, TODAY, [P, N], moon, 1)
    assert not current.finished
    assert current.moon_days == frozenset({date(2026, 1, 3)})
    assert year_card(2025, TODAY, [P], [], 1).finished


def _given(before: Position, after: Position, on: date = date(2026, 10, 27)) -> ProgressionEvent:
    return ProgressionEvent(1, EventKind.GIVEN, on, before, after)


def test_new_asana_card() -> None:
    card = asana_card(
        track(), _given(Position("primary", "navasana"), Position("primary", "bhujapidasana"))
    )
    assert card == AsanaCard(AsanaVariant.NEW_ASANA, "primary", "bhujapidasana", 2026, 10)


def test_series_begins_beats_complete_and_new_asana() -> None:
    # A jump from the end of Primary over Setu Bandhasana into Pasasana.
    event = _given(
        Position("primary", "urdhva-mukha-paschimottanasana"), Position("intermediate", "pasasana")
    )
    card = asana_card(track(), event)
    assert card is not None
    assert (card.variant, card.series) == (AsanaVariant.SERIES_BEGINS, "intermediate")


def test_primary_begins_from_standing_only() -> None:
    card = asana_card(
        track(), _given(STANDING_ONLY, Position("primary", "utthita-hasta-padangusthasana"))
    )
    assert card is not None
    assert (card.variant, card.series) == (AsanaVariant.SERIES_BEGINS, "primary")


def test_full_series_card() -> None:
    event = _given(
        Position("primary", "urdhva-mukha-paschimottanasana"),
        Position("primary", "setu-bandhasana"),
    )
    card = asana_card(track(), event)
    assert card is not None
    assert (card.variant, card.series, card.key) == (AsanaVariant.SERIES_COMPLETE, "primary", None)


@pytest.mark.parametrize(
    ("before", "after", "variant"),
    [
        ("vasisthasana", "raja-kapotasana", AsanaVariant.NEW_ASANA),
        ("raja-kapotasana", "eka-pada-raja-kapotasana", AsanaVariant.SERIES_COMPLETE),
    ],
)
def test_advanced_a_cards(before: str, after: str, variant: AsanaVariant) -> None:
    card = asana_card(
        track(), _given(Position("advanced-a", before), Position("advanced-a", after))
    )
    assert card is not None
    assert (card.variant, card.series) == (variant, "advanced-a")


@pytest.mark.parametrize("kind", [EventKind.START, EventKind.CHANGED, EventKind.ITEM_GIVEN])
def test_no_card_for_starts_corrections_and_items(kind: EventKind) -> None:
    event = ProgressionEvent(
        1, kind, TODAY, Position("primary", "navasana"), Position("primary", "bhujapidasana")
    )
    assert asana_card(track(), event) is None


def test_no_card_for_a_backward_given_or_a_stale_stop() -> None:
    back = _given(Position("primary", "bhujapidasana"), Position("primary", "navasana"))
    assert asana_card(track(), back) is None
    stale = _given(Position("primary", "navasana"), Position("primary", "no-such-asana"))
    assert asana_card(track(), stale) is None


def test_count_card_needs_the_ledger() -> None:
    assert count_card(100, seen=True) == CountCard(100)
    assert count_card(100, seen=False) is None


def test_empty_cards() -> None:
    assert is_empty(year_card(2026, TODAY, [N, N], [], 0))
    assert not is_empty(month_card(2026, 11, TODAY, [P], [], Summary(practiced=1)))
    assert not is_empty(CountCard(100))
