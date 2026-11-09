"""GM-02 `GetBadges` on a fake (spec §4, §8, §9): the caller's own facts only, the moon city via
`moon_follow_of` (own, follow-teacher, the Mysuru default), `today` in the account zone
(Kiritimati vs Honolulu; provisional allowed), `joined` and the day off passed to the rules,
and the output in file order."""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from functools import cache
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from tests.domain.test_practice import catalog
from tests.fakes import FixedClock, cities
from tristhana.application.badges import GetBadges
from tristhana.application.policies import Principal
from tristhana.domain.accounts import Account
from tristhana.domain.badges import BadgeDef, BadgeFacts
from tristhana.domain.days import DayStatus
from tristhana.domain.moon import FOLLOW_TEACHER, TeacherMoon
from tristhana.domain.progression import Track
from tristhana.domain.rest_days import DayOff
from tristhana.infrastructure.seed.badges_yaml import load_badges

SEED = Path(__file__).resolve().parents[3] / "data" / "seed" / "badges.yaml"
# 10:30 UTC on 9 Nov: already 10 Nov in Kiritimati (UTC+14), still 9 Nov in Honolulu (UTC-10).
NOW = datetime(2026, 11, 9, 10, 30, tzinfo=UTC)


@cache
def track() -> Track:
    return Track(catalog())


@cache
def defs() -> tuple[BadgeDef, ...]:
    return load_badges(SEED, track())


@dataclass
class SpyFacts:
    facts_by: dict[UUID, BadgeFacts] = field(default_factory=dict[UUID, BadgeFacts])
    calls: list[tuple[UUID, str, date]] = field(default_factory=list[tuple[UUID, str, date]])

    async def facts(self, account_id: UUID, moon_location: str, today: date) -> BadgeFacts:
        self.calls.append((account_id, moon_location, today))
        return self.facts_by.get(account_id, BadgeFacts(logged={}))


def account(**changes: object) -> Account:
    base = {
        "id": uuid4(),
        "display_name": "A",
        "locale": "en",
        "timezone": "Asia/Almaty",
        "last_seen_at": NOW,
        "created_at": datetime(2020, 1, 1, tzinfo=UTC),
    }
    return Account(**(base | changes))  # type: ignore[arg-type]


def run(repo: SpyFacts, who: Account) -> list[str]:
    use_case = GetBadges(repo, defs(), track(), cities(), FixedClock(NOW))
    view = asyncio.run(use_case.execute(Principal(who)))
    return [e.key for e in view.earned]


def test_reads_only_the_callers_own_facts() -> None:
    repo, me = SpyFacts(), account()

    assert run(repo, me) == []
    assert [c[0] for c in repo.calls] == [me.id]


@pytest.mark.parametrize(
    ("changes", "city"),
    [
        ({"moon_location": "almaty"}, "almaty"),
        (
            {
                "moon_location": FOLLOW_TEACHER,
                "main_teacher": TeacherMoon(uuid4(), "T", "moscow"),
            },
            "moscow",
        ),
        ({}, "mysuru"),  # never chose, no teacher, no shala
    ],
)
def test_the_moon_city_is_the_effective_one(changes: dict[str, object], city: str) -> None:
    repo = SpyFacts()

    run(repo, account(**changes))

    assert repo.calls[0][1] == city


@pytest.mark.parametrize(
    ("zone", "today"),
    [
        ("Pacific/Kiritimati", date(2026, 11, 10)),
        ("Pacific/Honolulu", date(2026, 11, 9)),
        (None, date(2026, 11, 9)),  # provisional (en: UTC)
    ],
)
def test_today_is_local_to_the_account(zone: str | None, today: date) -> None:
    repo = SpyFacts()

    run(repo, account(timezone=zone))

    assert repo.calls[0][2] == today


def test_joined_and_the_day_off_reach_the_rules() -> None:
    """40 practices around unlogged Sundays: a Mandala only when every Sunday is the day off
    in effect after joining."""
    start = date(2026, 6, 1)  # a Monday
    logged = {
        start + timedelta(days=i): DayStatus.PRACTICED
        for i in range(50)
        if (start + timedelta(days=i)).isoweekday() != 7
    }
    sunday = DayOff(frozenset({7}), date(2020, 1, 1))
    joined_late = datetime(2026, 7, 1, tzinfo=UTC)

    def with_mandala(who: Account) -> bool:
        repo = SpyFacts({who.id: BadgeFacts(logged=logged)})
        return "mandala" in run(repo, who)

    assert with_mandala(account(day_off=sunday))
    assert not with_mandala(account())  # no day off: an unlogged Sunday ends it
    assert not with_mandala(account(day_off=sunday, created_at=joined_late))


def test_output_follows_the_file_order() -> None:
    me = account()
    logged = {date(2026, 1, 1) + timedelta(days=i): DayStatus.PRACTICED for i in range(120)}
    repo = SpyFacts({me.id: BadgeFacts(logged=logged, kept_counts=frozenset({1000}))})

    assert run(repo, me) == ["ekam", "nava", "shatam", "count-108", "sahasra", "mandala"]
