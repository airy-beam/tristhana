"""ST-05 `GetCheckInTrends` on a fake (spec §4, §8): the caller's own facts only, the window
and `today` from the account zone (Kiritimati vs Honolulu; provisional allowed), the moon city
via `moon_follow_of`, and one repository call."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from tests.check_in_trends_fakes import InMemoryCheckInTrends
from tests.fakes import FixedClock, cities
from tristhana.application.check_in_trends import GetCheckInTrends
from tristhana.application.policies import Principal
from tristhana.domain.accounts import Account
from tristhana.domain.check_in_trends import MIN_TOTAL, ScaleDay, TrendFacts
from tristhana.domain.moon import FOLLOW_TEACHER, ShalaMoon, TeacherMoon

# 10:30 UTC on 30 Nov: already 1 Dec in Kiritimati (UTC+14), still 30 Nov in Honolulu (UTC-10).
NOW = datetime(2026, 11, 30, 10, 30, tzinfo=UTC)


def _account(**over: object) -> Account:
    base: dict[str, object] = {
        "id": uuid4(),
        "display_name": "Anna",
        "locale": "en",
        "timezone": "Asia/Almaty",
        "created_at": NOW - timedelta(days=400),
        "last_seen_at": NOW,
    }
    return Account(**(base | over))  # type: ignore[arg-type]


def _run(repo: InMemoryCheckInTrends, account: Account):
    use_case = GetCheckInTrends(repo, cities(), FixedClock(NOW))
    return asyncio.run(use_case.execute(Principal(account)))


@pytest.mark.parametrize(
    ("zone", "start", "end"),
    [
        ("Pacific/Kiritimati", date(2026, 1, 1), date(2026, 12, 1)),
        ("Pacific/Honolulu", date(2025, 12, 1), date(2026, 11, 30)),
    ],
)
def test_the_window_follows_the_account_zone(zone: str, start: date, end: date) -> None:
    repo = InMemoryCheckInTrends()
    me = _account(timezone=zone)

    view = _run(repo, me)

    assert repo.calls == [(me.id, "mysuru", start, end)]
    assert (view.trends.start, view.trends.end) == (start, end)


def test_a_provisional_zone_is_enough() -> None:
    repo = InMemoryCheckInTrends()

    view = _run(repo, _account(timezone=None, locale="ru"))  # ru -> Europe/Moscow

    assert view.trends.end == date(2026, 11, 30)


def test_only_the_callers_own_facts_are_read() -> None:
    me, other = _account(), _account()
    days = tuple(ScaleDay(date(2026, 11, d), 3, 3, 3) for d in range(1, MIN_TOTAL + 1))
    repo = InMemoryCheckInTrends(by_account={other.id: TrendFacts(days, ())})

    assert _run(repo, me).trends.total == 0
    assert _run(repo, other).trends.total == MIN_TOTAL
    assert [call[0] for call in repo.calls] == [me.id, other.id]


@pytest.mark.parametrize(
    ("over", "slug"),
    [
        ({}, "mysuru"),
        ({"moon_location": "almaty"}, "almaty"),
        (
            {
                "moon_location": FOLLOW_TEACHER,
                "main_teacher": TeacherMoon(uuid4(), "Maya", "moscow"),
            },
            "moscow",
        ),
        (
            {"shala": ShalaMoon(uuid4(), "Shala", "almaty", staff=True, teacher_on_staff=False)},
            "almaty",
        ),
    ],
)
def test_the_moon_calendar_is_the_one_followed_today(over: dict[str, object], slug: str) -> None:
    repo = InMemoryCheckInTrends()

    view = _run(repo, _account(**over))

    assert repo.calls[0][1] == slug
    assert view.city.slug == slug
