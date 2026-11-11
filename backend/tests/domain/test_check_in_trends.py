"""ST-05 (spec §3, §8): the window, the averages and their minimums, and the weekday and moon
buckets. Under a minimum the answer is None, so no small-sample average can leave the domain."""

from datetime import date, timedelta

import pytest

from tristhana.domain.check_in_trends import (
    MIN_BUCKET,
    MIN_TOTAL,
    Average,
    MoonBucket,
    Scale,
    ScaleDay,
    TrendFacts,
    average,
    moon_bucket,
    trends,
    window,
)
from tristhana.domain.moon import MoonDay, MoonDayKind

TODAY = date(2026, 11, 11)
FULL = date(2026, 10, 26)  # a Monday
NEW = date(2026, 11, 9)  # a Monday
MOON = (MoonDay(FULL, MoonDayKind.PURNIMA), MoonDay(NEW, MoonDayKind.AMAVASYA))


def _day(
    on: date, mood: int | None = 3, energy: int | None = 3, effort: int | None = 3
) -> ScaleDay:
    return ScaleDay(on, mood, energy, effort)


def _run(start: date, n: int, step: int = 1, **scales: int | None) -> list[ScaleDay]:
    return [_day(start + timedelta(days=i * step), **scales) for i in range(n)]


@pytest.mark.parametrize(
    ("today", "start"),
    [
        (date(2026, 11, 11), date(2025, 12, 1)),
        (date(2026, 1, 1), date(2025, 2, 1)),
        (date(2024, 2, 29), date(2023, 3, 1)),
        (date(2026, 12, 31), date(2026, 1, 1)),
    ],
)
def test_the_window_is_twelve_calendar_months_ending_today(today: date, start: date) -> None:
    assert window(today) == (start, today)


def test_the_minimums_fit_the_copy() -> None:
    # The RU copy uses the genitive plural after the number: right for 5-20 (spec §2).
    assert 5 <= MIN_BUCKET <= 20
    assert 5 <= MIN_TOTAL <= 20


@pytest.mark.parametrize(("n", "shown"), [(4, False), (5, True), (6, True)])
def test_an_average_needs_the_minimum(n: int, shown: bool) -> None:
    assert (average([3] * n) is not None) is shown


@pytest.mark.parametrize(
    ("values", "tenths"),
    [
        ([3, 3, 3, 4], 33),  # 3.25 -> 3.3
        ([3] * 13 + [4] * 7, 34),  # 3.35 -> 3.4
        ([1, 2, 3, 4, 5], 30),
        ([5, 5, 5, 5, 4], 48),
    ],
)
def test_an_average_is_rounded_half_up_to_tenths(values: list[int], tenths: int) -> None:
    assert average(values, minimum=1) == Average(tenths, len(values))


@pytest.mark.parametrize(
    ("offset", "full", "new"),
    [
        (-2, MoonBucket.OTHER, MoonBucket.OTHER),
        (-1, MoonBucket.FULL, MoonBucket.NEW),
        (0, MoonBucket.FULL, MoonBucket.NEW),
        (1, MoonBucket.FULL, MoonBucket.NEW),
        (2, MoonBucket.OTHER, MoonBucket.OTHER),
    ],
)
def test_near_a_moon_is_the_day_and_one_either_side(
    offset: int, full: MoonBucket, new: MoonBucket
) -> None:
    step = timedelta(days=offset)
    assert moon_bucket(FULL + step, MOON) is full
    assert moon_bucket(NEW + step, MOON) is new


def test_kshaya_days_count_with_their_phase() -> None:
    moon = (
        MoonDay(FULL, MoonDayKind.KSHAYA_PURNIMA),
        MoonDay(NEW, MoonDayKind.KSHAYA_AMAVASYA),
    )
    assert moon_bucket(FULL, moon) is MoonBucket.FULL
    assert moon_bucket(NEW, moon) is MoonBucket.NEW


def test_a_day_with_no_calendar_is_another_day() -> None:
    assert moon_bucket(FULL, ()) is MoonBucket.OTHER


def test_nothing_logged_gives_nothing() -> None:
    found = trends(TrendFacts((), MOON), TODAY)

    assert (found.total, found.enough) == (0, False)
    assert (found.months, found.weekdays, found.moon) == ((), None, None)
    assert (found.start, found.end) == (date(2025, 12, 1), TODAY)


@pytest.mark.parametrize(("n", "enough"), [(MIN_TOTAL - 1, False), (MIN_TOTAL, True)])
def test_nothing_is_shown_under_the_total_minimum(n: int, enough: bool) -> None:
    found = trends(TrendFacts(tuple(_run(date(2026, 10, 1), n)), ()), TODAY)

    assert (found.total, found.enough) == (n, enough)
    assert (len(found.months) == 12) is enough


def test_a_row_with_no_scale_counts_nowhere() -> None:
    days = [*_run(date(2026, 10, 1), MIN_TOTAL - 1), _day(date(2026, 10, 20), None, None, None)]

    found = trends(TrendFacts(tuple(days), ()), TODAY)

    assert (found.total, found.enough) == (MIN_TOTAL - 1, False)


def test_each_scale_is_counted_on_its_own() -> None:
    days = [
        *_run(date(2026, 10, 1), 6, mood=None, energy=4, effort=None),
        *_run(date(2026, 10, 10), 4, mood=None, energy=None, effort=2),
    ]

    october = dict(trends(TrendFacts(tuple(days), ()), TODAY).months)[date(2026, 10, 1)]

    assert october[Scale.ENERGY] == Average(40, 6)
    assert october[Scale.EFFORT] is None
    assert october[Scale.MOOD] is None


def test_months_come_oldest_first_and_a_thin_month_is_blank() -> None:
    days = [*_run(date(2026, 9, 1), 4, energy=5), *_run(date(2026, 10, 1), 10, energy=2)]

    months = trends(TrendFacts(tuple(days), ()), TODAY).months

    assert [m for m, _ in months] == [
        date(2025, 12, 1),
        *(date(2026, m, 1) for m in range(1, 12)),
    ]
    by_month = dict(months)
    assert by_month[date(2026, 9, 1)][Scale.ENERGY] is None
    assert by_month[date(2026, 10, 1)][Scale.ENERGY] == Average(20, 10)
    assert by_month[date(2026, 1, 1)] == {Scale.MOOD: None, Scale.ENERGY: None, Scale.EFFORT: None}


def test_weekdays_are_iso_days_monday_first() -> None:
    mondays = _run(date(2026, 8, 3), 6, step=7, energy=2)  # 3 Aug 2026 is a Monday
    thursdays = _run(date(2026, 8, 6), 5, step=7, energy=5)

    weekdays = trends(TrendFacts(tuple(mondays + thursdays), ()), TODAY).weekdays

    assert weekdays is not None
    assert len(weekdays) == 7
    assert weekdays[0][Scale.ENERGY] == Average(20, 6)
    assert weekdays[3][Scale.ENERGY] == Average(50, 5)
    assert weekdays[5][Scale.ENERGY] is None


def test_one_weekday_alone_is_not_a_weekday_view() -> None:
    mondays = _run(date(2026, 8, 3), MIN_TOTAL, step=7)

    assert trends(TrendFacts(tuple(mondays), ()), TODAY).weekdays is None


def _near_and_far() -> list[ScaleDay]:
    near_full = [_day(FULL + timedelta(days=d), energy=5) for d in (-1, 0, 1)]
    near_full += [_day(date(2026, 9, 26) + timedelta(days=d), energy=4) for d in (-1, 1)]
    return near_full + _run(date(2026, 10, 1), 10, energy=2)  # 1-10 Oct: far from both


def test_the_moon_view_sets_days_near_a_moon_beside_the_others() -> None:
    moon = (*MOON, MoonDay(date(2026, 9, 26), MoonDayKind.PURNIMA))

    found = trends(TrendFacts(tuple(_near_and_far()), moon), TODAY).moon

    assert found is not None
    assert found[MoonBucket.FULL][Scale.ENERGY] == Average(46, 5)
    assert found[MoonBucket.OTHER][Scale.ENERGY] == Average(20, 10)
    assert found[MoonBucket.NEW][Scale.ENERGY] is None


def test_no_moon_view_without_a_calendar() -> None:
    assert trends(TrendFacts(tuple(_near_and_far()), ()), TODAY).moon is None


def test_no_moon_view_when_no_near_bucket_has_an_average() -> None:
    days = _near_and_far()[1:]  # four near the full moon: under the minimum
    moon = (*MOON, MoonDay(date(2026, 9, 26), MoonDayKind.PURNIMA))

    assert trends(TrendFacts(tuple(days), moon), TODAY).moon is None


def test_no_moon_view_when_the_other_days_have_no_average() -> None:
    near = [_day(FULL + timedelta(days=d)) for d in (-1, 0, 1)]
    near += [_day(NEW + timedelta(days=d)) for d in (-1, 0, 1)]
    near += [_day(date(2026, 9, 26) + timedelta(days=d)) for d in (-1, 0, 1)]
    moon = (*MOON, MoonDay(date(2026, 9, 26), MoonDayKind.PURNIMA))
    days = [*near, *_run(date(2026, 10, 1), 2)]

    found = trends(TrendFacts(tuple(days), moon), TODAY)

    assert found.enough
    assert found.moon is None


def test_two_weekdays_with_different_scales_are_not_a_weekday_view() -> None:
    mondays = _run(date(2026, 8, 3), 6, step=7, mood=None, energy=2, effort=None)
    thursdays = _run(date(2026, 8, 6), 6, step=7, mood=4, energy=None, effort=None)

    found = trends(TrendFacts(tuple(mondays + thursdays), ()), TODAY)

    assert found.enough
    assert found.weekdays is None


def test_no_moon_view_when_the_two_sides_share_no_scale() -> None:
    moon = (*MOON, MoonDay(date(2026, 9, 26), MoonDayKind.PURNIMA))
    near = [_day(FULL + timedelta(days=d), None, 5, None) for d in (-1, 0, 1)]
    near += [_day(date(2026, 9, 26) + timedelta(days=d), None, 4, None) for d in (-1, 1)]
    far = _run(date(2026, 10, 1), 10, mood=3, energy=None, effort=None)

    found = trends(TrendFacts(tuple(near + far), moon), TODAY)

    assert found.enough
    assert found.moon is None


def test_days_outside_the_window_are_ignored() -> None:
    before = _run(date(2025, 11, 1), MIN_TOTAL)  # the window starts on 1 December 2025
    after = _run(TODAY + timedelta(days=1), MIN_TOTAL)

    found = trends(TrendFacts(tuple(before + after), ()), TODAY)

    assert (found.total, found.enough) == (0, False)
