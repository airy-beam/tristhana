"""CreateShareCard / GetShareCardImage / SendShareCard on fakes (ST-07, ADR-0040): each
subject, the two-tone projection before rendering (Q209), moon rings from the effective
calendar (MD-02), periods, emptiness, ownership, the rate limit, expiry and the one send."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from functools import cache
from pathlib import Path
from uuid import uuid4

import pytest

from tests.fakes import (
    FakeNotifier,
    FixedClock,
    InMemoryAccounts,
    InMemoryDays,
    InMemoryMoon,
    InMemoryProgression,
)
from tests.share_card_fakes import CountingTokens, InMemoryShareCards, SpyRenderer
from tristhana.application.policies import Principal
from tristhana.application.ports.notifications import DeliveryResult, DeliveryStatus
from tristhana.application.share_cards import (
    DAILY_LIMIT,
    AlreadySent,
    AsanaSubject,
    BotUnreachable,
    CardNotFound,
    CountSubject,
    CreateShareCard,
    GetShareCardImage,
    InvalidPeriod,
    MonthSubject,
    NothingToShare,
    RateLimited,
    SendFailed,
    SendShareCard,
    YearSubject,
    card_token_hash,
)
from tristhana.application.stats import GetYearStats
from tristhana.domain.accounts import IdentityKey, IdentityProvider, NewAccount
from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.moon import FOLLOW_TEACHER, MoonDay, MoonDayKind, TeacherMoon
from tristhana.domain.progression import EventKind, Position, ProgressionEvent, Track
from tristhana.domain.share_cards import (
    AsanaVariant,
    CardFormat,
    CardTone,
    CountCard,
    MonthCard,
    YearCard,
)
from tristhana.infrastructure.seed.cities_yaml import load_cities
from tristhana.infrastructure.seed.practice_catalog import load_practice_catalog

SEED = Path(__file__).resolve().parents[3] / "data" / "seed"
CITIES = load_cities(SEED / "cities.yaml")
NOW = datetime(2026, 11, 9, 5, tzinfo=UTC)  # Almaty: Mon Nov 9, 10:00
P, N = CardTone.PRACTICE, CardTone.NO_PRACTICE


@cache
def track() -> Track:
    return Track(load_practice_catalog(SEED).catalog)


class Env:
    def __init__(self, now: datetime = NOW) -> None:
        self.accounts, self.days, self.moon = InMemoryAccounts(), InMemoryDays(), InMemoryMoon()
        self.progression = InMemoryProgression(self.days)
        self.cards = InMemoryShareCards(now)
        self.renderer, self.notifier = SpyRenderer(), FakeNotifier()
        self.clock = FixedClock(now)
        stats = GetYearStats(self.days, self.moon, CITIES, track().catalog, self.clock)
        self.create = CreateShareCard(
            stats,
            self.progression,
            self.cards,
            self.renderer,
            CountingTokens(),
            track(),
            self.clock,
        )
        self.image = GetShareCardImage(self.cards, self.clock)
        self.send = SendShareCard(self.cards, self.notifier, self.clock)

    async def me(self, **changes: object) -> Principal:
        tid = str(42 + len(self.cards.telegram))
        a = await self.accounts.create_with_identity(
            IdentityKey(IdentityProvider.TELEGRAM, tid), NewAccount(display_name="A", locale="ru")
        )
        a = await self.accounts.set_timezone_if_unset(a.id, "Asia/Almaty")
        self.cards.telegram[a.id] = tid
        return Principal(replace(a, **changes))  # type: ignore[arg-type]

    def log(self, me: Principal, day: date, status: DayStatus) -> None:
        self.days.rows[(me.account.id, day)] = (DayLog(day, status), None)

    def rendered(self) -> object:
        return self.renderer.calls[-1][0]


async def test_month_card_projects_every_day_to_two_tones_before_rendering() -> None:
    env = Env()
    me = await env.me()
    env.log(me, date(2026, 10, 1), DayStatus.PRACTICED)
    env.log(me, date(2026, 10, 2), DayStatus.LADIES)
    env.log(me, date(2026, 10, 3), DayStatus.SICK)
    env.log(me, date(2026, 10, 5), DayStatus.SKIPPED)
    created = await env.create.execute(me, MonthSubject(2026, 10), CardFormat.STORY)
    card = env.rendered()
    assert isinstance(card, MonthCard)
    assert len(card.tones) == 31
    assert set(card.tones) <= {P, N}
    assert card.tones[:5] == (P, N, N, N, N)
    assert card.practiced == 1
    assert env.renderer.calls[-1][1:] == (CardFormat.STORY, "ru")
    assert (created.width, created.height) == (1080, 1920)
    assert created.file_name == "tristhana-2026-10-story.png"
    assert created.expires_at == NOW + timedelta(hours=24)
    assert await env.image.execute(created.token) is not None


async def test_a_ladies_holiday_month_and_a_rest_month_render_the_same_tones() -> None:
    a, b = Env(), Env()
    me_a, me_b = await a.me(), await b.me()
    for env, me, status in ((a, me_a, DayStatus.LADIES), (b, me_b, DayStatus.REST)):
        env.log(me, date(2026, 10, 1), DayStatus.PRACTICED)
        for d in (13, 14, 15):
            env.log(me, date(2026, 10, d), status)
        await env.create.execute(me, MonthSubject(2026, 10), CardFormat.SQUARE)
    assert a.rendered() == b.rendered()


async def test_current_month_stops_at_today() -> None:
    env = Env()
    me = await env.me()
    env.log(me, date(2026, 11, 2), DayStatus.PRACTICED)
    await env.create.execute(me, MonthSubject(2026, 11), CardFormat.STORY)
    card = env.rendered()
    assert isinstance(card, MonthCard)
    assert len(card.tones) == 9
    assert card.current


async def test_year_card_counts_practices_with_moon_rings_from_my_city() -> None:
    env = Env()
    me = await env.me(moon_location="almaty")
    env.log(me, date(2026, 3, 1), DayStatus.PRACTICED)
    env.log(me, date(2026, 3, 2), DayStatus.PRACTICED)
    env.moon.days_by_location["almaty"] = [MoonDay(date(2026, 3, 3), MoonDayKind.PURNIMA)]
    env.moon.days_by_location["mysuru"] = [MoonDay(date(2026, 3, 4), MoonDayKind.PURNIMA)]
    created = await env.create.execute(me, YearSubject(2026), CardFormat.SQUARE)
    card = env.rendered()
    assert isinstance(card, YearCard)
    assert (card.practiced, card.finished) == (2, False)
    assert card.moon_days == frozenset({date(2026, 3, 3)})
    assert created.file_name == "tristhana-2026-square.png"


async def test_moon_rings_follow_the_main_teacher() -> None:
    env = Env()
    teacher = TeacherMoon(uuid4(), "T", "almaty")
    me = await env.me(moon_location=FOLLOW_TEACHER, main_teacher=teacher)
    env.log(me, date(2026, 3, 1), DayStatus.PRACTICED)
    env.moon.days_by_location["almaty"] = [MoonDay(date(2026, 3, 3), MoonDayKind.PURNIMA)]
    env.moon.days_by_location["mysuru"] = [MoonDay(date(2026, 3, 4), MoonDayKind.PURNIMA)]
    await env.create.execute(me, YearSubject(2026), CardFormat.SQUARE)
    card = env.rendered()
    assert isinstance(card, YearCard)
    assert card.moon_days == frozenset({date(2026, 3, 3)})


@pytest.mark.parametrize(
    "subject",
    [
        MonthSubject(2026, 12),
        MonthSubject(2026, 13),
        MonthSubject(2026, 0),
        YearSubject(2027),
        YearSubject(1999),
    ],
)
async def test_future_or_invalid_periods(subject: MonthSubject | YearSubject) -> None:
    env = Env()
    me = await env.me()
    with pytest.raises(InvalidPeriod):
        await env.create.execute(me, subject, CardFormat.STORY)


async def test_nothing_to_share_without_practice() -> None:
    env = Env()
    me = await env.me()
    env.log(me, date(2026, 10, 2), DayStatus.REST)
    with pytest.raises(NothingToShare):
        await env.create.execute(me, MonthSubject(2026, 10), CardFormat.STORY)
    assert env.renderer.calls == []
    assert env.cards.rows == {}


def _given(me: Principal, env: Env, event_id: int, before: str, after: str) -> None:
    env.days.progression_events.append(
        (
            me.account.id,
            ProgressionEvent(
                event_id,
                EventKind.GIVEN,
                date(2026, 10, 27),
                Position("primary", before),
                Position("primary", after),
            ),
        )
    )


async def test_asana_card_from_my_event_only() -> None:
    env = Env()
    me, other = await env.me(), await env.me()
    _given(me, env, 7, "navasana", "bhujapidasana")
    await env.create.execute(me, AsanaSubject(7), CardFormat.STORY)
    card = env.rendered()
    assert getattr(card, "variant", None) is AsanaVariant.NEW_ASANA
    with pytest.raises(CardNotFound):
        await env.create.execute(other, AsanaSubject(7), CardFormat.STORY)
    with pytest.raises(CardNotFound):
        await env.create.execute(me, AsanaSubject(99), CardFormat.STORY)


async def test_count_card_needs_my_ledger_row() -> None:
    env = Env()
    me = await env.me()
    with pytest.raises(CardNotFound):
        await env.create.execute(me, CountSubject(100), CardFormat.STORY)
    env.cards.milestones.add((me.account.id, 100))
    created = await env.create.execute(me, CountSubject(100), CardFormat.SQUARE)
    assert env.rendered() == CountCard(100)
    assert created.file_name == "tristhana-100-square.png"


async def test_rate_limit() -> None:
    env = Env()
    me = await env.me()
    env.cards.milestones.add((me.account.id, 100))
    for _ in range(DAILY_LIMIT):
        await env.create.execute(me, CountSubject(100), CardFormat.STORY)
    with pytest.raises(RateLimited):
        await env.create.execute(me, CountSubject(100), CardFormat.STORY)


async def test_image_is_gone_after_a_day_and_malformed_tokens_are_not_read() -> None:
    env = Env()
    me = await env.me()
    env.cards.milestones.add((me.account.id, 100))
    created = await env.create.execute(me, CountSubject(100), CardFormat.STORY)
    later = GetShareCardImage(env.cards, FixedClock(NOW + timedelta(hours=24)))
    assert await later.execute(created.token) is None
    assert await env.image.execute("../../etc/passwd") is None


async def _card(env: Env, me: Principal) -> str:
    env.cards.milestones.add((me.account.id, 100))
    return (await env.create.execute(me, CountSubject(100), CardFormat.STORY)).token


async def test_send_to_my_chat_once() -> None:
    env = Env()
    me = await env.me()
    token = await _card(env, me)
    await env.send.execute(me, token)
    assert [(r.telegram_id, r.locale) for r, _ in env.notifier.cards] == [("42", "ru")]
    with pytest.raises(AlreadySent):
        await env.send.execute(me, token)


async def test_send_someone_elses_card_is_not_found() -> None:
    env = Env()
    me, other = await env.me(), await env.me()
    token = await _card(env, me)
    with pytest.raises(CardNotFound):
        await env.send.execute(other, token)
    with pytest.raises(CardNotFound):
        await env.send.execute(me, "short")


async def test_blocked_bot_gives_the_send_back() -> None:
    env = Env()
    me = await env.me()
    token = await _card(env, me)
    env.notifier.card_outcomes.append(DeliveryResult(DeliveryStatus.BLOCKED))
    with pytest.raises(BotUnreachable):
        await env.send.execute(me, token)
    env.notifier.card_outcomes.append(DeliveryResult(DeliveryStatus.FAILED))
    with pytest.raises(SendFailed):
        await env.send.execute(me, token)
    await env.send.execute(me, token)  # a retry works
    assert len(env.notifier.cards) == 3


async def test_no_telegram_identity_is_unreachable() -> None:
    env = Env()
    me = await env.me()
    token = await _card(env, me)
    del env.cards.telegram[me.account.id]
    with pytest.raises(BotUnreachable):
        await env.send.execute(me, token)
    assert env.cards.released == [card_token_hash(token)]


@pytest.mark.parametrize(
    ("zone", "outcome"),
    [("Pacific/Kiritimati", NothingToShare), ("Pacific/Honolulu", InvalidPeriod)],
)
async def test_this_year_is_the_local_year(zone: str, outcome: type[Exception]) -> None:
    # 31 Dec 2026, 12:00 UTC: already 1 Jan 2027 in Kiritimati (UTC+14), still 2026 in Honolulu.
    env = Env(datetime(2026, 12, 31, 12, tzinfo=UTC))
    me = await env.me(timezone=zone)
    with pytest.raises(outcome):
        await env.create.execute(me, YearSubject(2027), CardFormat.STORY)


async def test_no_moon_city_chosen_gets_mysuru_rings_like_the_stats_screen() -> None:
    env = Env()
    me = await env.me()  # never chose a moon city: MD-02 falls back to Mysuru
    env.log(me, date(2026, 3, 1), DayStatus.PRACTICED)
    env.moon.days_by_location["mysuru"] = [MoonDay(date(2026, 3, 4), MoonDayKind.PURNIMA)]
    await env.create.execute(me, YearSubject(2026), CardFormat.SQUARE)
    card = env.rendered()
    assert isinstance(card, YearCard)
    assert card.moon_days == frozenset({date(2026, 3, 4)})


async def test_the_rate_limit_is_checked_before_rendering() -> None:
    env = Env()
    me = await env.me()
    env.cards.milestones.add((me.account.id, 100))
    for _ in range(DAILY_LIMIT):
        await env.create.execute(me, CountSubject(100), CardFormat.STORY)
    rendered = len(env.renderer.calls)
    with pytest.raises(RateLimited):
        await env.create.execute(me, CountSubject(100), CardFormat.STORY)
    assert len(env.renderer.calls) == rendered
