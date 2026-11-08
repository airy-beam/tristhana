# ruff: noqa: RUF001
"""Teacher marks through the real webhook (PR-08 Phase 3, spec §6, §8, ADR-0037): the card's
button (only with targets) and the unset line; picker → confirm → mark, edited in place, Back
keeping the page; range buttons and copy; the stale card; unlinked → the list; the answer first;
the student's one silent message (single, range, back; both languages; Undo, My asanas, the
moved-on line); G with "Marked by …" and Undo; a teacher's reply that is the same whatever the
student's history or the delivery; the `t1:g*` values within 64 bytes, forged ones harmless.
Real use cases over the in-memory ports, with a frozen clock."""

import asyncio
import itertools
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramForbiddenError
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import FixedClock, InMemoryStorage
from tests.teacher_link_fakes import add_person
from tests.teacher_mark_fakes import MarkingProgression, marking
from tristhana.domain.accounts import Account
from tristhana.domain.locale import Locale
from tristhana.domain.progression import Change, EventKind, Position, Progression
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
BOT = "tristhana_test_bot"
ME_TG = 42
NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
TODAY = date(2026, 11, 8)
LINKED = date(2026, 6, 1)
UNSET_EN = "No last asana set yet. Once they set it in My asanas, you can mark new ones here."
UNSET_RU = (
    "Последняя асана пока не указана. Когда она будет указана в разделе „Мои асаны“, "
    "здесь можно будет "
    "отмечать новые."
)
KAPOTASANA_B = Position("intermediate", "kapotasana-b")
SUPTA_VAJRASANA = Position("intermediate", "supta-vajrasana")
BAKASANA_B = Position("intermediate", "bakasana-b")
BHARADVAJASANA = Position("intermediate", "bharadvajasana")
URDHVA_MUKHA = Position("primary", "urdhva-mukha-paschimottanasana")
ITEMS = frozenset({"drop-backs"})
UUID_RE = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
STALE = "This card was out of date, so nothing was marked. Here it is now."
# The single-sentence hint (owner, 2026-11-08), as pinned in test_i18n_teacher_marks.py.
HINT_EN = "If this doesn't match your practice, you can undo it."
HINT_RU = "Если это не совпадает с твоей практикой, отметку можно отменить."
_ids = itertools.count(260_000)
_people = itertools.count(6_000)


@dataclass
class Sent:
    name: str
    fields: dict[str, Any]


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def repo(storage: InMemoryStorage) -> MarkingProgression:
    return marking(storage)


@pytest.fixture
def order() -> list[str]:
    return []


@pytest.fixture
def blocked() -> set[int]:
    """Chats whose sendMessage fails as if the bot were blocked."""
    return set()


@pytest.fixture
def outbound(monkeypatch: pytest.MonkeyPatch, order: list[str], blocked: set[int]) -> list[Sent]:
    sent: list[Sent] = []

    async def record(self: AiohttpSession, bot: object, method: Any, **_: object) -> Any:
        fields = method.model_dump()
        sent.append(Sent(method.__api_method__, fields))
        order.append(method.__api_method__)
        if method.__api_method__ == "sendMessage" and fields.get("chat_id") in blocked:
            raise TelegramForbiddenError(method, "bot was blocked by the user")
        return True

    monkeypatch.setattr(AiohttpSession, "make_request", record)
    return sent


@pytest.fixture
def client(
    storage: InMemoryStorage,
    repo: MarkingProgression,
    outbound: list[Sent],
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    fixed = FixedClock(NOW)
    monkeypatch.setattr("tristhana.main.SystemClock", lambda: fixed)
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr(TOKEN),
        telegram_webhook_secret=SecretStr(SECRET),
        telegram_bot_username=BOT,  # pyright: ignore[reportCallIssue]
    )
    with TestClient(create_app(settings, storage)) as c:
        yield c


def _post(client: TestClient, update: dict[str, Any]) -> Any:
    response = client.post(
        "/telegram/webhook", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}
    )
    assert response.status_code == 200
    return response.json() if response.content else None


def _user(lang: str, user_id: int = ME_TG, name: str = "Ash") -> dict[str, Any]:
    return {"id": user_id, "is_bot": False, "first_name": name, "language_code": lang}


def _command(client: TestClient, text: str, lang: str = "en", user_id: int = ME_TG) -> Any:
    message = {
        "message_id": next(_ids),
        "date": 1_760_000_000,
        "chat": {"id": user_id, "type": "private"},
        "from": _user(lang, user_id),
        "text": text,
        "entities": [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}],
    }
    return _post(client, {"update_id": next(_ids), "message": message})


def _tap(client: TestClient, data: str, lang: str = "en", user_id: int = ME_TG) -> Any:
    message = {"message_id": 9, "date": 1_760_000_000, "chat": {"id": user_id, "type": "private"}}
    callback = {
        "id": f"cb{next(_ids)}",
        "from": _user(lang, user_id),
        "chat_instance": "ci",
        "data": data,
        "message": message | {"text": "…"},
    }
    return _post(client, {"update_id": next(_ids), "callback_query": callback})


def _buttons(body: Any) -> list[dict[str, Any]]:
    return [b for row in body["reply_markup"]["inline_keyboard"] for b in row]


def _texts(body: Any) -> list[str]:
    return [b["text"] for b in _buttons(body)]


def _data(body: Any, text: str) -> str:
    return next(b["callback_data"] for b in _buttons(body) if b["text"] == text)


def _lines(body: Any) -> list[str]:
    return [line for line in body["text"].split("\n") if line.strip()]


def _me(client: TestClient, storage: InMemoryStorage, lang: str = "en") -> Account:
    _command(client, "/start", lang)
    return next(a for a in storage.repo.accounts.values() if a.display_name == "Ash")


def _student(
    storage: InMemoryStorage,
    repo: MarkingProgression,
    me: Account,
    position: Position | None = KAPOTASANA_B,
    locale: Locale = "en",
    name: str | None = "Anna",
    earlier: tuple[Position, ...] = (),
) -> Account:
    """A linked student; `earlier`: positions changed to and back from (held before)."""
    student = add_person(storage.repo, str(next(_people)), name, locale, "UTC")
    storage.teacher_links.add(student.id, me.id, linked_on=LINKED)
    if position is not None:
        asyncio.run(_history(repo, student.id, position, earlier))
    return student


async def _history(
    repo: MarkingProgression, who: UUID, position: Position, earlier: tuple[Position, ...]
) -> None:
    start = Change(EventKind.START, TODAY, Progression(position), after=position)
    last = await repo.apply(who, start, None, who)
    assert last is not None
    for p in earlier:
        for before, after in ((position, p), (p, position)):
            change = Change(EventKind.CHANGED, TODAY, Progression(after), before, after)
            last = await repo.apply(who, change, last.id, who)
            assert last is not None
    item = Change(EventKind.ITEM_GIVEN, TODAY, Progression(position, ITEMS), item="drop-backs")
    assert await repo.apply(who, item, last.id, who) is not None


def _tg(who: Account, storage: InMemoryStorage) -> int:
    return int(next(k.provider_user_id for k, v in storage.repo.identities.items() if v == who.id))


def _card(client: TestClient, who: Account, page: int = 0, lang: str = "en") -> Any:
    return _tap(client, f"t1:v:{who.id}:{page}", lang)


def _notes(outbound: list[Sent], chat_id: int) -> list[Sent]:
    return [s for s in outbound if s.name == "sendMessage" and s.fields["chat_id"] == chat_id]


def _note_buttons(note: Sent) -> list[dict[str, Any]]:
    return [b for row in note.fields["reply_markup"]["inline_keyboard"] for b in row]


def _flow(
    client: TestClient, who: Account, option: str, page: int = 0, lang: str = "en"
) -> tuple[Any, Any, Any]:
    """Card → picker → confirm; returns the three screens."""
    card = _card(client, who, page, lang)
    picker = _tap(client, _data(card, card_button(lang)), lang)
    confirm = _tap(client, _data(picker, option), lang)
    return card, picker, confirm


def card_button(lang: str) -> str:
    return "🎉 Mark new asana" if lang == "en" else "🎉 Отметить новую асану"


def _yes(lang: str = "en") -> str:
    return "🎉 Yes, mark" if lang == "en" else "🎉 Да, отметить"


def _mark(
    client: TestClient, who: Account, option: str = "Supta Vajrasana", lang: str = "en"
) -> Any:
    _, _, confirm = _flow(client, who, option, lang=lang)
    return _tap(client, _data(confirm, _yes(lang)), lang)


# The card


def test_the_card_has_the_button_above_remove(
    client: TestClient, storage: InMemoryStorage, repo: MarkingProgression
) -> None:
    me = _me(client, storage)
    student = _student(storage, repo, me)

    body = _card(client, student)

    assert _texts(body) == ["🎉 Mark new asana", "Remove…", "‹ Back"]
    assert re.fullmatch(rf"t1:g:{UUID_RE}:0", _data(body, "🎉 Mark new asana"))


def test_an_unset_card_has_the_neutral_line_and_no_button(
    client: TestClient, storage: InMemoryStorage, repo: MarkingProgression
) -> None:
    me = _me(client, storage)
    student = _student(storage, repo, me, None)

    body = _card(client, student)

    assert _lines(body)[:2] == ["Anna", UNSET_EN]
    assert _texts(body) == ["Remove…", "‹ Back"]


def test_the_unset_line_in_russian(
    client: TestClient, storage: InMemoryStorage, repo: MarkingProgression
) -> None:
    me = _me(client, storage, "ru")
    student = _student(storage, repo, me, None)

    body = _card(client, student, lang="ru")

    assert _lines(body)[1] == UNSET_RU


def test_at_the_end_of_the_confirmed_series_there_is_no_button(
    client: TestClient, storage: InMemoryStorage, repo: MarkingProgression
) -> None:
    me = _me(client, storage)
    student = _student(storage, repo, me, Position("advanced-b", "omkarasana"))

    assert "🎉 Mark new asana" not in _texts(_card(client, student))


# Picker → confirm → mark


def test_the_picker_lists_the_next_three_with_ranges_and_back(
    client: TestClient, storage: InMemoryStorage, repo: MarkingProgression
) -> None:
    me = _me(client, storage)
    student = _student(storage, repo, me)
    card = _card(client, student, page=3)

    picker = _tap(client, _data(card, "🎉 Mark new asana"))

    assert picker["method"] == "editMessageText"
    assert picker["text"] == "Anna: which new asana? Anna gets one message, even for a few."
    assert _texts(picker) == [
        "Supta Vajrasana",
        "→ Bakasana B",
        "→ Bharadvajasana",
        "‹ Back",
    ]
    assert _data(picker, "‹ Back") == f"t1:v:{student.id}:3"
    picks = [b["callback_data"] for b in _buttons(picker)[:3]]
    assert all(re.fullmatch(rf"t1:gp:{UUID_RE}:\d:\d{{1,2}}:[123]:3", d) for d in picks)
    assert [d.split(":")[5] for d in picks] == ["1", "2", "3"]


def test_the_confirm_names_the_student_and_the_asana(
    client: TestClient, storage: InMemoryStorage, repo: MarkingProgression
) -> None:
    me = _me(client, storage)
    student = _student(storage, repo, me)

    _, picker, confirm = _flow(client, student, "Supta Vajrasana")

    assert confirm["method"] == "editMessageText"
    assert " ".join(confirm["text"].split()) == (
        "Anna: the next asana is Supta Vajrasana (Intermediate). Mark it as new? Anna gets a "
        "message from the bot and can undo it."
    )
    assert _texts(confirm) == ["🎉 Yes, mark", "‹ Back"]
    assert _data(confirm, "‹ Back") == _data(_card(client, student), "🎉 Mark new asana")
    assert re.fullmatch(rf"t1:gy:{UUID_RE}:\d:\d{{1,2}}:1:0", _data(confirm, "🎉 Yes, mark"))
    assert picker is not None


def test_the_range_confirm_names_both_ends(
    client: TestClient, storage: InMemoryStorage, repo: MarkingProgression
) -> None:
    me = _me(client, storage)
    student = _student(storage, repo, me)

    _, _, confirm = _flow(client, student, "→ Bharadvajasana")

    assert " ".join(confirm["text"].split()) == (
        "Anna: new asanas Supta Vajrasana → Bharadvajasana (Intermediate). Mark them? Anna gets "
        "one message from the bot and can undo it."
    )


def test_the_confirm_in_russian(
    client: TestClient, storage: InMemoryStorage, repo: MarkingProgression
) -> None:
    me = _me(client, storage, "ru")
    student = _student(storage, repo, me)

    _, picker, confirm = _flow(client, student, "Супта Ваджрасана", lang="ru")

    assert picker["text"] == (
        "Anna: какая новая асана? Anna получит одно сообщение, даже если асан несколько."
    )
    assert " ".join(confirm["text"].split()) == (
        "Anna: следующая асана — Супта Ваджрасана (вторая серия). Отметить как новую? Anna "
        "получит сообщение от бота и сможет отменить отметку."
    )
    assert _texts(confirm) == ["🎉 Да, отметить", "‹ Назад"]


def test_yes_marks_and_shows_the_refreshed_card_with_the_line_on_top(
    client: TestClient, storage: InMemoryStorage, repo: MarkingProgression
) -> None:
    me = _me(client, storage)
    student = _student(storage, repo, me)

    body = _mark(client, student)

    assert body["method"] == "editMessageText"
    assert _lines(body)[:3] == [
        "✅ Marked: Supta Vajrasana.",
        "Anna",
        "Last asana, as marked in their log: Supta Vajrasana (Intermediate)",
    ]
    assert _texts(body) == ["🎉 Mark new asana", "Remove…", "‹ Back"]
    assert storage.day_repo.progression_rows[student.id].position == SUPTA_VAJRASANA
    assert storage.day_repo.progression_rows[student.id].items == ITEMS


def test_a_range_mark_says_both_ends(
    client: TestClient, storage: InMemoryStorage, repo: MarkingProgression
) -> None:
    me = _me(client, storage)
    student = _student(storage, repo, me)

    body = _mark(client, student, "→ Bharadvajasana")

    assert _lines(body)[0] == "✅ Marked: Supta Vajrasana → Bharadvajasana."
    assert storage.day_repo.progression_rows[student.id].position == BHARADVAJASANA
    _, event = storage.day_repo.progression_events[-1]
    assert (event.kind, event.before) == (EventKind.GIVEN, KAPOTASANA_B)  # one event


def test_the_answer_comes_before_any_work(
    client: TestClient,
    storage: InMemoryStorage,
    repo: MarkingProgression,
    order: list[str],
) -> None:
    me = _me(client, storage)
    student = _student(storage, repo, me)
    _, _, confirm = _flow(client, student, "Supta Vajrasana")
    repo.calls = order
    order.clear()

    _tap(client, _data(confirm, "🎉 Yes, mark"))

    assert order.index("answerCallbackQuery") < order.index("for_teacher")
    assert order.index("for_teacher") < order.index("apply") < order.index("sendMessage")


def test_a_changed_position_gives_the_stale_card_and_no_message(
    client: TestClient, storage: InMemoryStorage, repo: MarkingProgression, outbound: list[Sent]
) -> None:
    me = _me(client, storage)
    student = _student(storage, repo, me)
    _, _, confirm = _flow(client, student, "Supta Vajrasana")
    state = storage.day_repo.progression_rows[student.id]
    own = Change(EventKind.GIVEN, TODAY, Progression(BAKASANA_B, ITEMS), KAPOTASANA_B, BAKASANA_B)
    assert asyncio.run(repo.apply(student.id, own, state.last_event_id, student.id))

    body = _tap(client, _data(confirm, "🎉 Yes, mark"))

    assert _lines(body)[:3] == [
        STALE,
        "Anna",
        "Last asana, as marked in their log: Bakasana B (Intermediate)",
    ]
    assert _notes(outbound, _tg(student, storage)) == []
    assert storage.day_repo.progression_rows[student.id].position == BAKASANA_B


def test_a_position_that_no_longer_resolves_gives_the_stale_card(
    client: TestClient, storage: InMemoryStorage, repo: MarkingProgression, outbound: list[Sent]
) -> None:
    """The longest possible value, n = 6, i = 99: no such stop in today's catalog."""
    me = _me(client, storage)
    student = _student(storage, repo, me)
    data = f"t1:gy:{student.id}:6:99:3:9999"

    body = _tap(client, data)

    assert len(data.encode()) == 54
    assert _lines(body)[0] == STALE
    assert _notes(outbound, _tg(student, storage)) == []
    assert storage.day_repo.progression_rows[student.id].position == KAPOTASANA_B


def test_unlinked_meanwhile_goes_back_to_the_list(
    client: TestClient, storage: InMemoryStorage, repo: MarkingProgression, outbound: list[Sent]
) -> None:
    me = _me(client, storage)
    student = _student(storage, repo, me)
    _, _, confirm = _flow(client, student, "Supta Vajrasana")
    storage.teacher_links.rows.pop((student.id, me.id))

    body = _tap(client, _data(confirm, "🎉 Yes, mark"))

    assert body["text"] == "No students on your list."
    assert _notes(outbound, _tg(student, storage)) == []
    assert storage.day_repo.progression_rows[student.id].position == KAPOTASANA_B


def test_the_teachers_reply_is_the_same_whatever_the_history_or_delivery(
    client: TestClient,
    storage: InMemoryStorage,
    repo: MarkingProgression,
    blocked: set[int],
) -> None:
    me = _me(client, storage)
    fresh = _student(storage, repo, me)
    held = _student(storage, repo, me, earlier=(BHARADVAJASANA,))  # changed back: no 🎉
    gone = _student(storage, repo, me)
    blocked.add(_tg(gone, storage))

    replies = {re.sub(UUID_RE, "<id>", str(_mark(client, who))) for who in (fresh, held, gone)}

    assert len(replies) == 1


# The student's message


def test_the_student_gets_one_silent_message_with_undo_and_my_asanas(
    client: TestClient, storage: InMemoryStorage, repo: MarkingProgression, outbound: list[Sent]
) -> None:
    me = _me(client, storage)
    student = _student(storage, repo, me)

    _mark(client, student)

    [note] = _notes(outbound, _tg(student, storage))
    assert note.fields["disable_notification"] is True
    assert _lines({"text": note.fields["text"]}) == [
        "🎉 New asana: Supta Vajrasana. Enjoy it! Marked by Ash.",
        HINT_EN,
    ]
    mark_id = storage.day_repo.progression_rows[student.id].last_event_id
    assert [(b["text"], b["callback_data"]) for b in _note_buttons(note)] == [
        ("↩︎ Undo", f"g1:u:{mark_id}"),
        ("🧘 My asanas", "g1:o"),
    ]
    assert len(_notes(outbound, ME_TG)) == 0  # nothing extra to the teacher


def test_a_range_message_names_both_ends(
    client: TestClient, storage: InMemoryStorage, repo: MarkingProgression, outbound: list[Sent]
) -> None:
    me = _me(client, storage)
    student = _student(storage, repo, me)

    _mark(client, student, "→ Bharadvajasana")

    [note] = _notes(outbound, _tg(student, storage))
    assert note.fields["text"].split("\n")[0] == (
        "🎉 New asanas: Supta Vajrasana → Bharadvajasana. Enjoy them! Marked by Ash."
    )


def test_a_range_into_intermediate_adds_the_series_lines(
    client: TestClient, storage: InMemoryStorage, repo: MarkingProgression, outbound: list[Sent]
) -> None:
    me = _me(client, storage)
    student = _student(storage, repo, me, URDHVA_MUKHA)

    _mark(client, student, "→ Krounchasana")

    [note] = _notes(outbound, _tg(student, storage))
    assert _lines({"text": note.fields["text"]}) == [
        "🎉 New asanas: Setu Bandhasana → Krounchasana. Enjoy them! Marked by Ash.",
        "🎉 Full Primary: Yoga Chikitsa.",
        "🎉 Intermediate begins: Nadi Shodhana.",
        HINT_EN,
    ]


def test_a_mark_held_before_gets_the_quiet_line(
    client: TestClient, storage: InMemoryStorage, repo: MarkingProgression, outbound: list[Sent]
) -> None:
    me = _me(client, storage)
    student = _student(storage, repo, me, earlier=(BHARADVAJASANA,))

    _mark(client, student, "→ Bakasana B")

    [note] = _notes(outbound, _tg(student, storage))
    assert _lines({"text": note.fields["text"]}) == [
        "Bakasana B is in your practice. Marked by Ash.",
        HINT_EN,
    ]
    assert "🎉" not in note.fields["text"]


@pytest.mark.parametrize(
    ("option", "first"),
    [
        (
            "Supta Vajrasana",
            "🎉 Новая асана: Супта Ваджрасана. Приятного знакомства! Отметка: Ash.",
        ),
        (
            "→ Bharadvajasana",
            "🎉 Новые асаны: Супта Ваджрасана → Бхарадваджасана. Приятного знакомства! "
            "Отметка: Ash.",
        ),
    ],
    ids=["single", "range"],
)
def test_the_message_is_in_the_students_language_not_the_teachers(
    client: TestClient,
    storage: InMemoryStorage,
    repo: MarkingProgression,
    outbound: list[Sent],
    option: str,
    first: str,
) -> None:
    me = _me(client, storage, "en")
    student = _student(storage, repo, me, locale="ru")

    _mark(client, student, option)

    [note] = _notes(outbound, _tg(student, storage))
    assert _lines({"text": note.fields["text"]}) == [first, HINT_RU]
    assert [b["text"] for b in _note_buttons(note)] == ["↩︎ Отменить", "🧘 Мои асаны"]


def test_the_back_line_in_russian(
    client: TestClient, storage: InMemoryStorage, repo: MarkingProgression, outbound: list[Sent]
) -> None:
    me = _me(client, storage)
    student = _student(storage, repo, me, locale="ru", earlier=(BHARADVAJASANA,))

    _mark(client, student, "→ Bakasana B")

    [note] = _notes(outbound, _tg(student, storage))
    assert note.fields["text"].split("\n")[0] == "Бакасана B — в твоей практике. Отметка: Ash."


def test_undo_on_the_message_puts_it_back_and_says_undone(
    client: TestClient, storage: InMemoryStorage, repo: MarkingProgression, outbound: list[Sent]
) -> None:
    me = _me(client, storage)
    student = _student(storage, repo, me)
    _mark(client, student, "→ Bharadvajasana")
    [note] = _notes(outbound, _tg(student, storage))
    undo = _note_buttons(note)[0]["callback_data"]
    _tap(client, "g1:i:standing-up:1", user_id=_tg(student, storage))  # a later item is fine

    body = _tap(client, undo, user_id=_tg(student, storage))

    assert body["method"] == "editMessageText"
    assert "Undone." in body["text"]
    state = storage.day_repo.progression_rows[student.id]
    assert state.position == KAPOTASANA_B
    assert state.items == ITEMS | {"standing-up"}


def test_undo_after_the_practice_moved_on_says_so(
    client: TestClient, storage: InMemoryStorage, repo: MarkingProgression, outbound: list[Sent]
) -> None:
    me = _me(client, storage)
    student = _student(storage, repo, me)
    _mark(client, student)
    [note] = _notes(outbound, _tg(student, storage))
    undo = _note_buttons(note)[0]["callback_data"]
    _tap(client, "g1:g:2:bakasana-b", user_id=_tg(student, storage))  # their own next give

    body = _tap(client, undo, user_id=_tg(student, storage))

    assert (
        "Your practice has changed since this mark, so nothing was undone. To set where it ends "
        "now, use ✏️ Change." in body["text"]
    )
    assert storage.day_repo.progression_rows[student.id].position == BAKASANA_B


def test_my_asanas_shows_who_marked_it_with_undo(
    client: TestClient, storage: InMemoryStorage, repo: MarkingProgression
) -> None:
    me = _me(client, storage)
    student = _student(storage, repo, me)
    _mark(client, student)
    mark_id = storage.day_repo.progression_rows[student.id].last_event_id
    _tap(client, "g1:i:standing-up:1", user_id=_tg(student, storage))

    body = _command(client, "/asanas", user_id=_tg(student, storage))

    lines = _lines(body)
    current = next(i for i, line in enumerate(lines) if line.startswith("Your practice:"))
    assert "Marked by Ash" in lines[current + 1]
    assert [b["callback_data"] for b in _buttons(body) if b["text"] == "↩︎ Undo the mark"] == [
        f"g1:u:{mark_id}"
    ]
    assert "↩︎ Undo" not in _texts(body)  # no item was just ticked on this screen


def test_after_an_item_tick_the_two_undos_read_differently(
    client: TestClient, storage: InMemoryStorage, repo: MarkingProgression
) -> None:
    """The item's own Undo and the teacher's mark's Undo are never two identical buttons."""
    me = _me(client, storage)
    student = _student(storage, repo, me)
    _mark(client, student)
    mark_id = storage.day_repo.progression_rows[student.id].last_event_id

    body = _tap(client, "g1:i:standing-up:1", user_id=_tg(student, storage))

    item_id = storage.day_repo.progression_rows[student.id].last_event_id
    undos = {b["text"]: b["callback_data"] for b in _buttons(body) if "↩︎" in b["text"]}
    assert undos == {"↩︎ Undo": f"g1:u:{item_id}", "↩︎ Undo the mark": f"g1:u:{mark_id}"}


def test_the_mark_undo_in_russian(
    client: TestClient, storage: InMemoryStorage, repo: MarkingProgression
) -> None:
    me = _me(client, storage)
    student = _student(storage, repo, me, locale="ru")
    _mark(client, student)

    body = _command(client, "/asanas", "ru", user_id=_tg(student, storage))

    assert "↩︎ Отменить отметку" in _texts(body)


def test_my_asanas_after_an_unlink_says_a_teacher(
    client: TestClient, storage: InMemoryStorage, repo: MarkingProgression
) -> None:
    me = _me(client, storage)
    student = _student(storage, repo, me)
    _mark(client, student)
    storage.teacher_links.rows.pop((student.id, me.id))

    body = _command(client, "/asanas", user_id=_tg(student, storage))

    assert "Marked by a teacher" in body["text"]
    assert "Ash" not in body["text"]


def test_my_asanas_has_no_marked_line_once_moved_on(
    client: TestClient, storage: InMemoryStorage, repo: MarkingProgression
) -> None:
    me = _me(client, storage)
    student = _student(storage, repo, me)
    _mark(client, student)
    _tap(client, "g1:g:2:bakasana-b", user_id=_tg(student, storage))

    body = _command(client, "/asanas", user_id=_tg(student, storage))

    assert "Marked by" not in body["text"]


# Callback data


def test_the_longest_values_fit_well_within_64_bytes() -> None:
    uuid = "ffffffff-ffff-ffff-ffff-ffffffffffff"
    longest = {
        "t1:g": f"t1:g:{uuid}:9999",
        "t1:gp": f"t1:gp:{uuid}:6:99:3:9999",
        "t1:gy": f"t1:gy:{uuid}:6:99:3:9999",
    }

    assert {k: len(v.encode()) for k, v in longest.items()} == {
        "t1:g": 46,
        "t1:gp": 54,
        "t1:gy": 54,
    }
    assert max(len(v.encode()) for v in longest.values()) <= 64


def test_every_rendered_mark_button_fits_and_keeps_the_page(
    client: TestClient, storage: InMemoryStorage, repo: MarkingProgression
) -> None:
    me = _me(client, storage)
    student = _student(storage, repo, me)

    card, picker, confirm = _flow(client, student, "→ Bharadvajasana", page=49)

    data = [b["callback_data"] for s in (card, picker, confirm) for b in _buttons(s)]
    assert max(len(d.encode()) for d in data) <= 54
    assert all(d.endswith(":49") for d in data if d.startswith(("t1:g", "t1:v")))


@pytest.mark.parametrize(
    "tail",
    [
        "2:9:0:0",  # k = 0
        "2:9:4:0",  # k = 4
        "2:9:x:0",
        "7:0:1:0",  # no series 7
        "2:-1:1:0",
        "2:9:1:99999",  # page too long
        "2:9:1",  # no page
        "2:9:1:0:extra",
        "0:1:1:0",  # standing only is 0:0
    ],
)
@pytest.mark.parametrize("action", ["gp", "gy"])
def test_malformed_values_mark_nothing(
    client: TestClient,
    storage: InMemoryStorage,
    repo: MarkingProgression,
    outbound: list[Sent],
    action: str,
    tail: str,
) -> None:
    me = _me(client, storage)
    student = _student(storage, repo, me)

    _tap(client, f"t1:{action}:{student.id}:{tail}")

    assert storage.day_repo.progression_rows[student.id].position == KAPOTASANA_B
    assert _notes(outbound, _tg(student, storage)) == []


def test_a_forged_student_id_marks_nothing(
    client: TestClient, storage: InMemoryStorage, repo: MarkingProgression, outbound: list[Sent]
) -> None:
    """Someone else's student: the write is keyed on the caller, so it can only fail."""
    me = _me(client, storage)
    other_teacher = add_person(storage.repo, "9999", "Boris")
    theirs = _student(storage, repo, other_teacher)
    _, _, confirm = _flow(client, _student(storage, repo, me), "Supta Vajrasana")
    forged = re.sub(UUID_RE, str(theirs.id), _data(confirm, "🎉 Yes, mark"))

    body = _tap(client, forged)

    assert body["text"].startswith("👥 My students")
    assert storage.day_repo.progression_rows[theirs.id].position == KAPOTASANA_B
    assert _notes(outbound, _tg(theirs, storage)) == []


# Positions at a series' first stop (index 0), and ranges across a series boundary


@pytest.mark.parametrize(
    ("position", "option", "first_line"),
    [
        (
            Position("intermediate", "pasasana"),
            "Krounchasana",
            "✅ Marked: Krounchasana.",
        ),
        (
            Position("primary", "utthita-hasta-padangusthasana"),
            "→ Utkatasana",
            "✅ Marked: Ardha Baddha Padmottanasana → Utkatasana.",
        ),
    ],
    ids=["pasasana-2:0", "uhp-1:0"],
)
def test_a_first_stop_of_a_series_runs_the_whole_flow(
    client: TestClient,
    storage: InMemoryStorage,
    repo: MarkingProgression,
    outbound: list[Sent],
    position: Position,
    option: str,
    first_line: str,
) -> None:
    """`<n>:0` is a real stop (Pasasana is `2:0`, UHP `1:0`), not a malformed value."""
    me = _me(client, storage)
    student = _student(storage, repo, me, position)

    _, _, confirm = _flow(client, student, option)
    assert ":0:" in _data(confirm, "🎉 Yes, mark").split(str(student.id))[1]
    body = _tap(client, _data(confirm, "🎉 Yes, mark"))

    assert _lines(body)[0] == first_line
    assert storage.day_repo.progression_rows[student.id].position != position
    assert len(_notes(outbound, _tg(student, storage))) == 1


@pytest.mark.parametrize(
    ("position", "option", "text"),
    [
        (
            URDHVA_MUKHA,
            "→ Krounchasana",
            "Anna: new asanas Setu Bandhasana (Primary) → Krounchasana (Intermediate). Mark them? "
            "Anna gets one message from the bot and can undo it.",
        ),
        (
            Position("intermediate", "mukta-hasta-sirsasana-c"),
            "→ Visvamitrasana",
            "Anna: new asanas Baddha Hasta Sirsasana D (Intermediate) → Visvamitrasana "
            "(Advanced A). Mark them? Anna gets one message from the bot and can undo it.",
        ),
    ],
    ids=["primary-to-intermediate", "intermediate-to-advanced-a"],
)
def test_a_range_across_a_series_boundary_names_both_series(
    client: TestClient,
    storage: InMemoryStorage,
    repo: MarkingProgression,
    position: Position,
    option: str,
    text: str,
) -> None:
    me = _me(client, storage)
    student = _student(storage, repo, me, position)

    _, _, confirm = _flow(client, student, option)

    assert " ".join(confirm["text"].split()) == text


def test_a_range_within_one_series_names_it_once(
    client: TestClient, storage: InMemoryStorage, repo: MarkingProgression
) -> None:
    """From Baddha Hasta Sirsasana D (Intermediate's last stop) every next stop is Advanced A,
    so the plain range line names the series once."""
    me = _me(client, storage)
    student = _student(storage, repo, me, Position("intermediate", "baddha-hasta-sirsasana-d"))

    _, _, confirm = _flow(client, student, "→ Visvamitrasana")

    assert " ".join(confirm["text"].split()) == (
        "Anna: new asanas Vasisthasana → Visvamitrasana (Advanced A). Mark them? Anna gets one "
        "message from the bot and can undo it."
    )
