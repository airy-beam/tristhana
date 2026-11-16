"""Buttons under messages sent before UI-06 (spec §5, §8): a tap on any of them still gets a
screen, an edit or a message, never only the answer that stops the spinner.

One world serves every entry of the frozen list (`fixtures/pre_ui06_callbacks.py`), seeded
with the ids, codes and dates inside the strings: me (a platform admin, a teacher and a
student of the other person, on the staff of the shala), the shala with one class and one
student, a rest period, a directory request. The clock is fixed on the list's own day.
"""

import itertools
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.bots.fixtures import pre_ui06_callbacks as frozen
from tests.directory_listing_fakes import always
from tests.fakes import FixedClock, InMemoryStorage
from tests.moon_follow_fakes import person
from tests.shala_fakes import shala_storage
from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.directory_listing import Step, clean
from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.domain.rest_periods import RestPeriod
from tristhana.domain.shalas import ShalaRole
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
BOT = "tristhana_test_bot"
ME_TG = 42
NOW = datetime(2026, 11, 15, 0, 30, tzinfo=UTC)  # Sun Nov 15, 05:30 in Almaty: `frozen.DAY`
EVERY_DAY = frozenset({1, 2, 3, 4, 5, 6, 7})
SCREENS = {"editMessageText", "sendMessage", "sendPhoto", "sendDocument"}
_ids = itertools.count(270_000)


@dataclass
class World:
    client: TestClient
    storage: InMemoryStorage
    sent: list[str]
    me: UUID


def _fixed_ids(monkeypatch: pytest.MonkeyPatch, module: str, value: UUID) -> None:
    monkeypatch.setattr(f"{module}.uuid4", lambda: value)


@pytest.fixture
def w(monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    storage = shala_storage()
    storage.repo.clock.instant = NOW
    me = person(storage, str(ME_TG), "Ash", moon="almaty")
    owner = person(storage, "1002", "Dana")
    with monkeypatch.context() as ids:  # the ids inside the frozen strings
        _fixed_ids(ids, "tests.fakes", frozen.PERSON)
        anna = person(storage, "1001", "Anna", moon="almaty")
        _fixed_ids(ids, "tests.shala_fakes", frozen.SHALA)
        shala = storage.shalas.add_shala(owner.id, code=frozen.SHALA_CODE).id
        _fixed_ids(ids, "tests.schedule_fakes", frozen.CLASS)
        storage.schedule.add_class(
            shala, weekdays=EVERY_DAY, starts_on=date(2026, 10, 1), teacher_id=me.id
        )
    assert (anna.id, shala) == (frozen.PERSON, frozen.SHALA)
    storage.shalas.add_staff(shala, me.id, ShalaRole.ADMIN, ShalaRole.TEACHER)
    storage.shalas.add_student(shala, anna.id)
    storage.link_repo.add(me.id, anna.id)  # Anna is my teacher...
    storage.link_repo.add(anna.id, me.id)  # ... and my student
    storage.link_repo.codes[anna.id] = frozen.TEACHER_CODE
    storage.attendance  # noqa: B018  # attaches the fake to the schedule
    storage.moon_repo.days_by_location["almaty"] = [MoonDay(frozen.MOON_DAY, MoonDayKind.PURNIMA)]
    storage.day_repo.periods.rows[(me.id, frozen.PERIOD_START)] = RestPeriod(
        frozen.PERIOD_START, frozen.PERIOD_END, DayStatus.SICK
    )
    sent: list[str] = []

    async def record(self: AiohttpSession, bot: object, method: Any, **_: object) -> bool:
        sent.append(method.__api_method__)
        return True

    monkeypatch.setattr(AiohttpSession, "make_request", record)
    monkeypatch.setattr("tristhana.main.SystemClock", lambda: FixedClock(NOW))
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr(TOKEN),
        telegram_webhook_secret=SecretStr(SECRET),
        miniapp_url="https://tristhana.web.app",
        telegram_bot_username=BOT,  # pyright: ignore[reportCallIssue]
        platform_admin_ids=str(me.id),  # pyright: ignore[reportCallIssue]
        public_api_url="https://tristhana-api-test.a.run.app",  # pyright: ignore[reportCallIssue]  # SC-06
    )
    with TestClient(create_app(settings, storage)) as client:
        yield World(client, storage, sent, me.id)


def _tap(w: World, data: str) -> Any:
    chat = {"id": ME_TG, "type": "private"}
    message = {"message_id": 9, "date": 1_760_000_000, "chat": chat, "text": "…"}
    callback = {
        "id": f"cb{next(_ids)}",
        "from": {"id": ME_TG, "is_bot": False, "first_name": "Ash", "language_code": "en"},
        "chat_instance": "ci",
        "data": data,
        "message": message,
    }
    response = w.client.post(
        "/telegram/webhook",
        json={"update_id": next(_ids), "callback_query": callback},
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
    )
    assert response.status_code == 200
    return response.json() if response.content else None


async def _seed_for(w: World, data: str) -> None:
    """What a button needs to have been on screen at all: the day it sits under was logged,
    the request it decides exists."""
    prefix, letter = data.split(":")[:2]
    practiced = (frozen.DAY, DayLog(frozen.DAY, DayStatus.PRACTICED))
    if prefix in ("p1", "k1") or (prefix, letter) in (("r1", "y"), ("r1", "n"), ("g1", "n")):
        w.storage.day_repo.rows[(w.me, practiced[0])] = (practiced[1], None)
    if (prefix, letter) == ("a1", "k"):
        # "Keep the pause" sits under a 🧘 that cut a 🌸 pause short: 13-17 became 13-14.
        w.storage.day_repo.rows[(w.me, practiced[0])] = (practiced[1], None)
        w.storage.day_repo.periods.rows[(w.me, frozen.PERIOD_START)] = RestPeriod(
            frozen.PERIOD_START, date(2026, 11, 14), DayStatus.LADIES
        )
    if prefix == "l1":
        details = clean("Anna Petrova", "Kazakhstan", "certified", None)
        await w.storage.listings.save(frozen.PERSON, details, always(Step.SEND), NOW)


@pytest.mark.parametrize("data", frozen.PRE_UI06_CALLBACKS)
async def test_every_button_shipped_before_ui06_still_gets_a_screen(w: World, data: str) -> None:
    await _seed_for(w, data)

    body = _tap(w, data)

    reply = body.get("method") if body else None
    shown = ({reply} | set(w.sent)) & SCREENS
    assert shown, f"{data}: only {[reply, *w.sent]}"
    assert "answerCallbackQuery" in {reply, *w.sent}  # and the spinner stops


def test_a_w1_button_also_gets_a_screen(w: World) -> None:
    for data in ("w1:m", "w1:n", "w1:h", "w1:o", "w1:f", "w1:p", "w1:t", "w1:c", "w1:s:f"):
        body = _tap(w, data)
        assert body["method"] == "editMessageText", data


def test_the_world_is_on_the_lists_own_day(w: World) -> None:
    body = _tap(w, "w1:n")

    assert body["text"].startswith("🤒 Sick / injury through")  # the seeded pause covers it
    assert "Today, Sun, Nov 15" in body["text"]
    assert replace(w.storage.repo.accounts[w.me]).timezone == "Asia/Almaty"
