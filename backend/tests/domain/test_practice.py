from datetime import date, time
from functools import cache
from pathlib import Path

import pytest

from tristhana.domain.practice import (
    FULL_PRIMARY,
    HALF_PRIMARY,
    SHORT,
    STATIC_PRESETS,
    InvalidLength,
    InvalidPractice,
    Practice,
    PracticeCatalog,
    PracticeContext,
    PracticeLength,
    TimezoneUnknown,
    check_length,
    check_practice,
    derive_presets,
)
from tristhana.infrastructure.seed.catalog_yaml import load_catalog

SEED = Path(__file__).resolve().parents[3] / "data" / "seed"


@cache
def catalog() -> PracticeCatalog:
    return PracticeCatalog(load_catalog(SEED / "asanas.yaml", SEED / "sequences.yaml"))


def L(*series: str, end: str | None = None, part: str | None = None) -> PracticeLength:
    return PracticeLength(series, end, part)  # type: ignore[arg-type]


def test_only_confirmed_series_in_order() -> None:
    assert [s.slug for s in catalog().series] == [
        "primary",
        "intermediate",
        "advanced-a",
        "advanced-b",
    ]


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (SHORT, SHORT),
        (L("primary"), L("primary")),
        (L("primary", end="navasana"), L("primary", end="navasana")),
        (L("primary", end="setu-bandhasana"), L("primary")),  # last stop = full
        (
            L("primary", "intermediate", end="pasasana"),
            L("primary", "intermediate", end="pasasana"),
        ),
        (L("intermediate", end="karandavasana"), L("intermediate", end="karandavasana")),
        (L("intermediate", "advanced-a"), L("intermediate", "advanced-a")),
        # Half Primary + Intermediate (owner, 2026-10-19).
        (
            L("primary", "intermediate", end="pasasana", part="first_half"),
            L("primary", "intermediate", end="pasasana", part="first_half"),
        ),
        (
            L("primary", "intermediate", end="pasasana", part="second_half"),
            L("primary", "intermediate", end="pasasana", part="second_half"),
        ),
        (L("primary", part="first_half"), L("primary", end="navasana")),  # = ½ Primary
        (L("primary", end="navasana", part="first_half"), L("primary", end="navasana")),
    ],
)
def test_valid_lengths_normalise(given: PracticeLength, expected: PracticeLength) -> None:
    assert check_length(catalog(), given) == expected


@pytest.mark.parametrize(
    "length",
    [
        L("primary", "advanced-a"),  # not contiguous
        L("intermediate", "primary"),  # descending
        L("advanced-c"),  # pending series
        L("standing"),  # a block, not a series
        L("primary", end="dandasana"),  # not a stop point
        L("primary", end="paschimottanasana-d"),  # optional item, never a stop
        L("primary", "intermediate", end="navasana"),  # end must be in the last series
        L("primary", end="no-such-asana"),
        L(end="navasana"),  # short with an end
        L(part="first_half"),
        L("intermediate", "advanced-a", part="first_half"),  # Intermediate has no halves
        L("primary", part="second_half"),  # second half only together with Intermediate
        L("primary", end="kurmasana", part="second_half"),
        L("primary", end="kurmasana", part="first_half"),
    ],
)
def test_invalid_lengths(length: PracticeLength) -> None:
    with pytest.raises(InvalidLength):
        check_length(catalog(), length)


def test_static_presets_are_valid_against_the_seed() -> None:
    for _, length in STATIC_PRESETS:
        assert check_length(catalog(), length) == length


def test_stop_labels() -> None:
    stop = catalog().stop("primary", "janu-sirsasana-c")

    assert stop is not None
    assert stop.label("en") == "Janu Sirsasana C"
    assert stop.label("ru") == "Джану Ширшасана C"


def test_practice_rules() -> None:
    ok = check_practice(catalog(), Practice(PracticeContext.MYSORE, online=True, duration_min=90))
    assert ok.duration_min == 90
    with pytest.raises(InvalidPractice):
        check_practice(catalog(), Practice(PracticeContext.SELF, online=True))
    with pytest.raises(InvalidPractice):
        check_practice(catalog(), Practice(duration_min=0))
    with pytest.raises(InvalidPractice):
        check_practice(catalog(), Practice(duration_min=601))
    with pytest.raises(TimezoneUnknown):
        check_practice(catalog(), Practice(start_time=time(6, 30)))
    with pytest.raises(InvalidPractice):
        check_practice(catalog(), Practice(slot=2))


def _p(length: PracticeLength | None) -> Practice:
    return Practice(PracticeContext.MYSORE, length=length)


def test_presets_without_history() -> None:
    presets = derive_presets(catalog(), [])

    assert presets.last is None
    assert presets.presets == STATIC_PRESETS


def test_last_is_the_newest_non_led_practice() -> None:
    # Q27: "same as last time" skips a led class, as the reminder does. Newest first.
    led = Practice(PracticeContext.LED, length=FULL_PRIMARY)
    mysore = _p(HALF_PRIMARY)

    assert derive_presets(catalog(), [led, mysore, _p(FULL_PRIMARY)]).last == mysore
    assert derive_presets(catalog(), [mysore, led]).last == mysore


def test_last_falls_back_to_the_newest_when_every_practice_is_led() -> None:
    newest = Practice(PracticeContext.LED, length=FULL_PRIMARY, duration_min=90)
    older = Practice(PracticeContext.LED, length=FULL_PRIMARY)

    assert derive_presets(catalog(), [newest, older]).last == newest


def test_a_practice_without_a_context_counts_as_not_led() -> None:
    led = Practice(PracticeContext.LED, length=FULL_PRIMARY)
    plain = Practice(duration_min=60)

    assert derive_presets(catalog(), [led, plain]).last == plain


def test_last_day_is_the_day_of_the_practice_that_would_be_copied() -> None:
    # Q296: the "Last time" line can say which day when that practice is old.
    led = Practice(PracticeContext.LED, length=FULL_PRIMARY)
    fri, thu = date(2026, 10, 16), date(2026, 10, 15)

    assert derive_presets(catalog(), [led, _p(HALF_PRIMARY)], days=[fri, thu]).last_day == thu
    assert derive_presets(catalog(), [led], days=[fri]).last_day == fri
    assert derive_presets(catalog(), [led]).last_day is None  # the caller gave no days
    assert derive_presets(catalog(), [], days=[]).last_day is None


def test_recent_lengths_are_ranked_by_use_then_recency() -> None:
    usual = L("primary", "intermediate", end="pasasana")
    split = L("intermediate", end="karandavasana")
    rare = L("intermediate", "advanced-a", end="vasisthasana")
    # Newest first: Friday Primary, then the usual week, an older split, a stale key.
    history = [
        _p(FULL_PRIMARY),
        _p(usual),
        _p(usual),
        _p(rare),
        _p(split),
        _p(split),
        _p(usual),
        _p(L("primary", end="retired-asana")),
        _p(None),
        _p(HALF_PRIMARY),
    ]

    presets = derive_presets(catalog(), history)

    assert presets.last == history[0]
    assert presets.presets[3:] == (("recent", usual), ("recent", split), ("recent", rare))
