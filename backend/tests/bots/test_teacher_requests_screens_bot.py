# ruff: noqa: RUF001
"""Teacher requests through the real webhook (ID-07 spec §2, §5, §8): the question after
joining in both languages and both forms, Details and back, a name → Today with one line and
the teacher's silent note, the card's waiting line and Withdraw; the teacher's Yes, "Not my
student" with Undo, the waiting list and Confirm all; every row of the stale-button table;
what each tap costs; data within 64 bytes; answered before the write. Real use cases over
the in-memory port, with the clock fixed."""

import itertools
import re
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.bots.statements import Statements
from tests.fakes import FixedClock, InMemoryStorage
from tests.moon_follow_fakes import person
from tests.shala_fakes import shala_storage
from tristhana.application.teacher_requests import AskTeacher
from tristhana.bots.telegram import shalas_callbacks as shala_cb
from tristhana.bots.telegram import teacher_links_callbacks as link_cb
from tristhana.bots.telegram.shalas_callbacks import short_id
from tristhana.domain.accounts import Account
from tristhana.domain.locale import Locale
from tristhana.domain.shalas import ShalaRole
from tristhana.domain.teacher_requests import RequestCaps, RequestConsent, RequestState
from tristhana.infrastructure.i18n.fluent import FluentTranslator
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
BOT = "tristhana_test_bot"
ME_TG = 42
ANNA_TG = 1001
JOIN = "J0inC0deJ0inC0de"
NOW = datetime(2026, 11, 17, 4, 0, tzinfo=UTC)  # Tue Nov 17, 09:00 in Almaty
ASKED_ON = date(2026, 11, 17)
REFUSAL = "отклон|отказ|declin|reject|refus|denied|turned down"
T = FluentTranslator()
_ids = itertools.count(410_000)


def _t(key: str, locale: Locale = "en", **args: str | int) -> str:
    return T.t(locale, key, **args)


@dataclass
class World:
    client: TestClient
    storage: InMemoryStorage
    out: list[Any]  # Bot API calls made directly (not as the webhook reply)
    clock: FixedClock
    lang: Locale
    timeouts: list[Any]  # of the direct calls, in order

    @property
    def me(self) -> Account:
        return next(a for a in self.storage.repo.accounts.values() if a.display_name == "Ash")

    def later(self, **delta: int) -> None:
        self.clock.instant = self.storage.repo.clock.instant = self.clock.instant + timedelta(
            **delta
        )

    def notes(self, chat: int = ANNA_TG) -> list[Any]:
        return [m for m in self.out if m.__api_method__ == "sendMessage" and m.chat_id == chat]

    @property
    def requests(self) -> Any:
        return self.storage.teacher_requests

    def state(self, student: UUID, teacher: UUID) -> RequestState | None:
        return self.requests.state_of(student, teacher)


def _world(monkeypatch: pytest.MonkeyPatch, lang: Locale) -> Iterator[World]:
    storage = shala_storage()
    storage.repo.clock.instant = NOW
    person(storage, str(ME_TG), "Ash", locale=lang, moon="almaty")
    out: list[Any] = []

    timeouts: list[Any] = []

    async def record(self: AiohttpSession, bot: object, method: Any, **options: Any) -> bool:
        out.append(method)
        timeouts.append(options.get("timeout"))
        storage.teacher_requests.writes.append(method.__api_method__)
        return True

    monkeypatch.setattr(AiohttpSession, "make_request", record)
    clock = FixedClock(NOW)
    monkeypatch.setattr("tristhana.main.SystemClock", lambda: clock)
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr(TOKEN),
        telegram_webhook_secret=SecretStr(SECRET),
        miniapp_url="https://tristhana.web.app",
        telegram_bot_username=BOT,  # pyright: ignore[reportCallIssue]
    )
    with TestClient(create_app(settings, storage)) as client:
        yield World(client, storage, out, clock, lang, timeouts)


@pytest.fixture
def w(monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    yield from _world(monkeypatch, "en")


@pytest.fixture
def ru(monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    yield from _world(monkeypatch, "ru")


def _tap(w: World, data: str) -> Any:
    chat = {"id": ME_TG, "type": "private"}
    message = {"message_id": 9, "date": 1_760_000_000, "chat": chat, "text": "…"}
    callback = {
        "id": f"cb{next(_ids)}",
        "from": {"id": ME_TG, "is_bot": False, "first_name": "Ash", "language_code": w.lang},
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


def _rows(body: Any) -> list[list[tuple[str, str | None]]]:
    return [
        [(b["text"], b.get("callback_data")) for b in row]
        for row in body["reply_markup"]["inline_keyboard"]
    ]


def _labels(body: Any) -> list[list[str]]:
    return [[text for text, _ in row] for row in _rows(body)]


def _datas(body: Any) -> list[str]:
    return [data for row in _rows(body) for _, data in row if data]


def _shala(
    w: World,
    *teachers: str,
    owner_roles: frozenset[ShalaRole] = frozenset(),
    name: str = "Ashtanga Almaty",
    code: str = JOIN,
    locale: Locale = "en",
) -> tuple[UUID, list[Account]]:
    """A shala owned by Dana (no Teacher role unless given), with these teachers. The first
    one, Anna by custom, has the chat `ANNA_TG`."""
    owner = _person(w, "Dana")
    shala = w.storage.shalas.add_shala(owner.id, name, "almaty", code=code, roles=owner_roles).id
    staff: list[Account] = []
    for teacher in teachers:
        account = _person(w, teacher, locale)
        w.storage.shalas.add_staff(shala, account.id, ShalaRole.TEACHER)
        staff.append(account)
    return shala, staff


_people = itertools.count(ANNA_TG + 1)


def _person(w: World, name: str, locale: Locale = "en") -> Account:
    found = next((a for a in w.storage.repo.accounts.values() if a.display_name == name), None)
    if found is not None:
        return found
    chat = ANNA_TG if name == "Anna" else next(_people)
    return person(w.storage, str(chat), name, locale=locale)


def _join(w: World, shala: UUID) -> None:
    w.storage.shalas.add_student(shala, w.me.id)


def _teach(w: World, name: str = "Ashtanga Almaty", code: str = JOIN) -> UUID:
    """A shala where I am a teacher (Dana owns it)."""
    shala, _ = _shala(w, name=name, code=code)
    w.storage.shalas.add_staff(shala, w.me.id, ShalaRole.TEACHER)
    return shala


def _asks(w: World, shala: UUID, name: str, state: RequestState = RequestState.WAITING) -> Account:
    """`name` joins `shala` and asks me."""
    student = _person(w, name)
    w.storage.shalas.add_student(shala, student.id)
    w.requests.add(student.id, w.me.id, shala, state=state, asked_on=ASKED_ON)
    return student


def _moment(w: World) -> int:
    """The clock's second: what a list drawn now carries in its "Confirm all"."""
    return int(w.clock.instant.timestamp())


def _on(action: str, shala: UUID) -> str:
    return shala_cb.on_shala(action, shala)  # type: ignore[arg-type]


def _member(action: str, shala: UUID, account: UUID) -> str:
    return shala_cb.on_member(action, shala, account)  # type: ignore[arg-type]


# The question after joining


def test_joining_a_shala_with_teachers_asks_who_my_teacher_is(
    w: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    shala, (anna, boris) = _shala(w, "Anna", "Boris")
    statements = Statements(monkeypatch, w.storage)

    body = _tap(w, f"h1:a:{JOIN}")

    assert body["method"] == "editMessageText"
    assert body["text"].split("\n\n") == [
        f"🏛 Ashtanga Almaty\n{_t('request-ask')}",
        _t("request-consent-short", me=" (Ash)"),
        _t("request-until-yes"),
        _t("request-know-them"),
    ]
    assert _rows(body) == [
        [("Anna", _member("ta", shala, anna.id))],
        [("Boris", _member("ta", shala, boris.id))],
        [("📄 Details", _on("td", shala)), ("Not now", _on("tn", shala))],
    ]
    assert w.storage.shalas.students_of(shala) == [w.me.id]
    assert w.requests.rows == {}  # joining alone asks no one
    assert w.notes() == []
    assert statements.count == 2, statements.names  # the join, the teachers to offer


def test_the_question_in_russian(ru: World) -> None:
    shala, (anna, boris) = _shala(ru, "Anna", "Boris")

    body = _tap(ru, f"h1:a:{JOIN}")

    assert body["text"].split("\n\n") == [
        f"🏛 Ashtanga Almaty\n{_t('request-ask', 'ru')}",
        _t("request-consent-short", "ru", me=" (Ash)"),
        _t("request-until-yes", "ru"),
        _t("request-know-them", "ru"),
    ]
    assert "Кто твой учитель" in body["text"]
    assert _labels(body) == [["Anna"], ["Boris"], ["📄 Подробнее", "Не сейчас"]]
    assert _datas(body)[:2] == [_member("ta", shala, anna.id), _member("ta", shala, boris.id)]


@pytest.mark.parametrize("world", ["w", "ru"])
def test_with_one_teacher_the_question_names_them(
    world: str, request: pytest.FixtureRequest
) -> None:
    w: World = request.getfixturevalue(world)
    shala, (anna,) = _shala(w, "Anna")

    body = _tap(w, f"h1:a:{JOIN}")

    head = body["text"].split("\n\n")[0]
    assert head == f"🏛 Ashtanga Almaty\n{_t('request-ask-one', w.lang, name='Anna')}"
    assert _rows(body)[0] == [(_t("request-yes", w.lang), _member("ta", shala, anna.id))]
    assert len(_rows(body)) == 2  # Yes, then Details and Not now


def test_with_nobody_to_ask_joining_ends_on_the_card_as_before(w: World) -> None:
    shala, _ = _shala(w)  # the owner holds no Teacher role

    body = _tap(w, f"h1:a:{JOIN}")

    assert body["text"].splitlines()[0] == "🏛 Ashtanga Almaty"
    assert _t("request-ask") not in body["text"]
    assert f"h1:k:{short_id(shala)}" in _datas(body)  # the card: Leave…
    assert _on("t", shala) not in _datas(body)


def test_only_the_teacher_role_is_offered(w: World) -> None:
    shala, (anna,) = _shala(w, "Anna")
    for name, role in (("Olga", ShalaRole.ASSISTANT), ("Max", ShalaRole.ADMIN)):
        w.storage.shalas.add_staff(shala, _person(w, name).id, role)
    w.storage.shalas.add_staff(shala, _person(w, "Front").id, ShalaRole.OFFICE)

    body = _tap(w, f"h1:a:{JOIN}")

    assert _rows(body)[0] == [(_t("request-yes"), _member("ta", shala, anna.id))]
    assert "Dana" not in str(_rows(body))  # an owner counts only with the role


def test_a_linked_teacher_and_one_already_asked_are_not_offered(w: World) -> None:
    shala, (anna, boris, vera) = _shala(w, "Anna", "Boris", "Vera")
    _join(w, shala)
    w.storage.teacher_links.add(w.me.id, anna.id)
    w.requests.add(w.me.id, boris.id, shala)

    body = _tap(w, _on("t", shala))

    assert _rows(body)[0] == [(_t("request-yes"), _member("ta", shala, vera.id))]
    assert _t("request-ask-one", name="Vera") in body["text"]


def test_a_moved_moon_city_is_said_under_the_question(w: World) -> None:
    """Joining can move a never-chose member's moon city: the line the card would show."""
    w.storage.repo.accounts[w.me.id] = replace(w.me, moon_location=None)
    _shala(w, "Anna")

    body = _tap(w, f"h1:a:{JOIN}")

    assert _t("request-ask-one", name="Anna") in body["text"]
    assert body["text"].split("\n\n")[-1].startswith("🌙")


# Details and back


@pytest.mark.parametrize("world", ["w", "ru"])
def test_details_show_the_full_consent_with_the_same_names_and_lead_back(
    world: str, request: pytest.FixtureRequest
) -> None:
    w: World = request.getfixturevalue(world)
    shala, _ = _shala(w, "Anna", "Boris")
    short = _tap(w, f"h1:a:{JOIN}")

    details = _tap(w, _on("td", shala))
    again = _tap(w, _on("t", shala))

    assert details["method"] == "editMessageText"
    assert details["text"].split("\n\n") == [
        f"🏛 Ashtanga Almaty\n{_t('request-ask', w.lang)}",
        _t("request-consent", w.lang, me=" (Ash)"),
        _t("request-know-them", w.lang),
    ]
    assert _rows(details)[:2] == _rows(short)[:2]  # the same taps: one consent, two layers
    assert _rows(details)[2] == [
        (_t("consent-short-back", w.lang), _on("t", shala)),
        (_t("invite-decline", w.lang), _on("tn", shala)),
    ]
    assert (again["text"], _rows(again)) == (short["text"], _rows(short))
    assert w.requests.rows == {}


def test_details_and_back_cost_one_statement_each(
    w: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    shala, _ = _shala(w, "Anna")
    _join(w, shala)
    statements = Statements(monkeypatch, w.storage)

    for data in (_on("td", shala), _on("t", shala)):
        statements.clear()
        _tap(w, data)
        assert statements.count == 1, (data, statements.names)


def test_not_now_opens_the_card_and_asks_no_one(w: World) -> None:
    shala, _ = _shala(w, "Anna")
    _tap(w, f"h1:a:{JOIN}")

    body = _tap(w, _on("tn", shala))

    assert body["text"].splitlines()[0] == "🏛 Ashtanga Almaty"
    assert _rows(body)[-1] == [(_t("log-back"), "t1:o")]
    assert (_t("request-open"), _on("t", shala)) in [b for row in _rows(body) for b in row]
    assert w.requests.rows == {}
    assert w.notes() == []


# The consent tap


def test_a_name_sends_the_request_and_shows_today(
    w: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    shala, (anna, _) = _shala(w, "Anna", "Boris")
    _join(w, shala)
    statements = Statements(monkeypatch, w.storage)

    body = _tap(w, _member("ta", shala, anna.id))

    assert body["method"] == "editMessageText"
    assert body["text"].split("\n\n")[0] == _t("request-asked", name="Anna")
    assert _datas(body)[-1] == "w1:m"  # Today, with its Menu row
    row = w.requests.rows[(w.me.id, anna.id)]
    assert (row.state, row.shala_id, row.asked_on) == (RequestState.WAITING, shala, ASKED_ON)
    assert row.quiet_note_agreed is True  # both layers of the consent name the quiet note
    assert w.storage.teacher_links.rows == {}  # a request is not a link
    assert statements.count == 2, statements.names  # the ask, Today's read


def test_the_consent_tap_names_the_request_consent_the_app_names_too(
    w: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-0049: `h1:ta` sends `request-1`, never a flag; the domain grants the note."""
    shala, (anna,) = _shala(w, "Anna")
    _join(w, shala)
    named: list[object] = []
    original = AskTeacher.execute

    async def spy(self: AskTeacher, *args: Any, **kwargs: Any) -> Any:
        named.append(kwargs.get("consent"))
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(AskTeacher, "execute", spy)

    _tap(w, _member("ta", shala, anna.id))

    assert named == [RequestConsent.FIRST]
    assert w.requests.rows[(w.me.id, anna.id)].quiet_note_agreed is True


def test_the_teacher_gets_one_silent_note_in_their_language(w: World) -> None:
    shala, (anna,) = _shala(w, "Anna", locale="ru")
    _join(w, shala)

    _tap(w, _member("ta", shala, anna.id))

    [note] = w.notes()
    assert note.text == _t("request-note", "ru", student="Ash", shala="Ashtanga Almaty")
    assert note.disable_notification is True
    assert note.parse_mode is None  # the names are people's own text, never markup
    rows = [[(b.text, b.callback_data) for b in row] for row in note.reply_markup.inline_keyboard]
    assert rows == [
        [
            (_t("request-yes-mine", "ru"), f"t1:ra:{w.me.id}"),
            (_t("request-not-mine", "ru"), f"t1:rn:{w.me.id}"),
        ]
    ]
    assert w.timeouts[w.out.index(note)] == 3  # the student's tap is waiting


def test_see_all_is_on_the_note_only_from_the_second_waiting_request(w: World) -> None:
    shala, (anna,) = _shala(w, "Anna")
    _join(w, shala)
    other = _person(w, "Zoe")
    w.storage.shalas.add_student(shala, other.id)
    w.requests.add(other.id, anna.id, shala)

    _tap(w, _member("ta", shala, anna.id))

    [note] = w.notes()
    last = note.reply_markup.inline_keyboard[-1]
    assert [(b.text, b.callback_data) for b in last] == [
        (_t("request-see-all", count=2), "t1:rl:0")
    ]


def test_the_tap_is_answered_before_the_request_is_written(w: World) -> None:
    shala, (anna,) = _shala(w, "Anna")
    _join(w, shala)

    _tap(w, _member("ta", shala, anna.id))

    order = w.requests.writes
    assert order.index("answerCallbackQuery") < order.index("ask") < order.index("sendMessage")


def test_a_blocked_teacher_fails_nothing(w: World, monkeypatch: pytest.MonkeyPatch) -> None:
    from aiogram.exceptions import TelegramForbiddenError
    from aiogram.methods import GetMe

    shala, (anna,) = _shala(w, "Anna")
    _join(w, shala)

    async def blocked(self: AiohttpSession, bot: object, method: Any, **_: object) -> bool:
        if method.__api_method__ == "sendMessage":
            raise TelegramForbiddenError(method=GetMe(), message="bot was blocked by the user")
        return True

    monkeypatch.setattr(AiohttpSession, "make_request", blocked)

    body = _tap(w, _member("ta", shala, anna.id))

    assert body["text"].split("\n\n")[0] == _t("request-asked", name="Anna")
    assert w.state(w.me.id, anna.id) is RequestState.WAITING  # the list is the record


@pytest.mark.parametrize("world", ["w", "ru"])
@pytest.mark.parametrize(
    ("case", "key"),
    [
        ("linked", "invite-already"),
        ("waiting", "request-waiting"),
        ("quiet no", "request-waiting"),
        ("recent", "request-recent"),
        ("too many", "request-too-many"),
        ("full", "request-full"),
    ],
)
def test_every_other_outcome_is_one_line_above_today_and_never_a_no(
    world: str, case: str, key: str, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    w: World = request.getfixturevalue(world)
    shala, (anna, *others) = _shala(w, "Anna", "Boris", "Vera", "Gleb")
    _join(w, shala)
    match case:
        case "linked":
            w.storage.teacher_links.add(w.me.id, anna.id)
        case "waiting":
            w.requests.add(w.me.id, anna.id, shala)
        case "quiet no":
            w.requests.add(w.me.id, anna.id, shala, state=RequestState.DECLINED)
        case "recent":
            w.requests.add(w.me.id, anna.id, shala, state=RequestState.WITHDRAWN)
        case "too many":
            for other in others:
                w.requests.add(w.me.id, other.id, shala)
        case _:
            caps = RequestCaps(waiting=0)
            monkeypatch.setattr("tristhana.application.teacher_requests.CAPS", caps)
    before = dict(w.requests.rows)

    body = _tap(w, _member("ta", shala, anna.id))

    lead = body["text"].split("\n\n")[0]
    assert lead == _t(key, w.lang, name="Anna")
    assert not re.search(REFUSAL, lead.lower())
    assert _datas(body)[-1] == "w1:m"
    assert w.requests.rows == before  # nothing written
    assert w.notes() == []  # and the teacher hears nothing more


def test_full_says_only_not_right_now(w: World) -> None:
    for locale in ("en", "ru"):
        text = _t("request-full", locale, name="Anna")
        assert "Anna" not in text  # nothing about the teacher or their list
        assert re.search("right now|сейчас", text.lower())
        assert not re.search("full|полон|заполн|list|спис|limit|лимит|many|мног", text.lower())


def test_a_name_tapped_after_leaving_the_shala_opens_my_teachers(w: World) -> None:
    shala, (anna,) = _shala(w, "Anna")

    body = _tap(w, _member("ta", shala, anna.id))  # never joined, or left since

    assert body["text"].split("\n\n")[0] == _t("menu-teacher")
    assert _datas(body)[-1] == "w1:m"
    assert w.requests.rows == {}
    assert w.notes() == []


def test_a_name_that_is_no_longer_a_teacher_redraws_the_question(w: World) -> None:
    shala, (anna, _) = _shala(w, "Anna", "Boris")
    _join(w, shala)
    staff = w.storage.shalas.staff
    staff[(shala, anna.id)] = replace(
        staff[(shala, anna.id)], roles=frozenset({ShalaRole.ASSISTANT})
    )

    body = _tap(w, _member("ta", shala, anna.id))

    assert _t("request-ask-one", name="Boris") in body["text"]
    assert _member("ta", shala, anna.id) not in _datas(body)
    assert w.requests.rows == {}


def test_a_forged_teacher_id_asks_no_one(w: World) -> None:
    shala, _ = _shala(w, "Anna")
    _join(w, shala)
    stranger = _person(w, "Stranger")  # in no shala of mine

    for target in (stranger.id, uuid4(), w.me.id):
        body = _tap(w, _member("ta", shala, target))
        assert body["method"] == "editMessageText"

    assert w.requests.rows == {}
    assert [m for m in w.out if m.__api_method__ == "sendMessage"] == []


# The shala's card, student side


def test_the_card_shows_who_i_wait_for_with_withdraw_and_the_way_to_ask(
    w: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    shala, (anna, _) = _shala(w, "Anna", "Boris")
    _join(w, shala)
    w.requests.add(w.me.id, anna.id, shala)
    statements = Statements(monkeypatch, w.storage)

    body = _tap(w, _on("c", shala))

    assert _t("request-waiting-line", name="Anna") in body["text"].split("\n\n")
    flat = [b for row in _rows(body) for b in row]
    assert (_t("request-open"), _on("t", shala)) in flat  # Boris can still be asked
    assert (_t("request-withdraw", name="Anna"), _member("tw", shala, anna.id)) in flat
    assert _t("request-no-teachers-hint") not in body["text"]
    names = [n for n in statements.names if "TeacherRequests" in n]
    assert names == ["InMemoryTeacherRequests.card"]  # one more read, beside the card's own


def test_the_card_has_no_ask_row_once_everyone_is_asked_or_linked(w: World) -> None:
    shala, (anna,) = _shala(w, "Anna")
    _join(w, shala)
    w.storage.teacher_links.add(w.me.id, anna.id)

    body = _tap(w, _on("c", shala))

    assert _on("t", shala) not in _datas(body)
    assert "⏳" not in body["text"]


def test_a_quiet_no_looks_exactly_like_waiting_on_every_student_screen(w: World) -> None:
    """ADR-0046: the decline is stored and projected away."""
    shala, (anna, _) = _shala(w, "Anna", "Boris")
    _join(w, shala)
    row = w.requests.add(w.me.id, anna.id, shala)
    taps = [_on("c", shala), _on("t", shala), _on("td", shala), _member("tw", shala, anna.id)]
    waiting = [_tap(w, data) for data in taps]

    row.state = RequestState.DECLINED
    declined = [_tap(w, data) for data in taps]

    assert declined == waiting


def test_an_old_question_or_pick_another_with_nobody_left_opens_the_card_saying_so(
    w: World,
) -> None:
    shala, (anna,) = _shala(w, "Anna")
    _join(w, shala)
    w.requests.add(w.me.id, anna.id, shala)

    for data in (_on("t", shala), _on("td", shala)):
        body = _tap(w, data)

        assert body["text"].split("\n\n")[-1] == _t("request-nobody")
        assert f"h1:k:{short_id(shala)}" in _datas(body)


def test_the_question_for_someone_on_the_staff_is_the_card(w: World) -> None:
    shala = _teach(w)

    body = _tap(w, _on("t", shala))

    assert body["text"].splitlines()[0] == "🏛 Ashtanga Almaty"
    assert _t("request-nobody") not in body["text"]


def test_the_question_of_a_shala_i_am_not_in_opens_my_teachers(w: World) -> None:
    shala, _ = _shala(w, "Anna")

    for data in (_on("t", shala), _on("td", shala), _on("tn", shala), _on("t", uuid4())):
        body = _tap(w, data)
        assert body["text"].split("\n\n")[0] == _t("menu-teacher")


# Withdraw


@pytest.mark.parametrize("world", ["w", "ru"])
def test_withdraw_is_ask_then_withdraw_and_tells_no_one(
    world: str, request: pytest.FixtureRequest
) -> None:
    w: World = request.getfixturevalue(world)
    shala, (anna,) = _shala(w, "Anna")
    _join(w, shala)
    w.requests.add(w.me.id, anna.id, shala)

    ask = _tap(w, _member("tw", shala, anna.id))

    assert ask["text"] == _t("request-withdraw-ask", w.lang, name="Anna")
    assert _rows(ask) == [
        [(_t("request-withdraw-yes", w.lang), _member("tx", shala, anna.id))],
        [(_t("log-back", w.lang), _on("c", shala))],
    ]
    assert w.state(w.me.id, anna.id) is RequestState.WAITING  # nothing yet

    done = _tap(w, _member("tx", shala, anna.id))

    assert done["text"].split("\n\n")[-1] == _t("request-withdrawn", w.lang)
    assert done["text"].splitlines()[0] == "🏛 Ashtanga Almaty"
    assert "⏳" not in done["text"]
    assert _on("t", shala) not in _datas(done)  # not again for a while (Q317)
    assert w.state(w.me.id, anna.id) is RequestState.WITHDRAWN
    assert w.notes() == []


def test_withdraw_costs_one_statement_to_ask(w: World, monkeypatch: pytest.MonkeyPatch) -> None:
    shala, (anna,) = _shala(w, "Anna")
    _join(w, shala)
    w.requests.add(w.me.id, anna.id, shala)
    statements = Statements(monkeypatch, w.storage)

    _tap(w, _member("tw", shala, anna.id))

    assert statements.count == 1, statements.names


def test_withdraw_after_the_teacher_confirmed_opens_their_card(w: World) -> None:
    """Stale table: "Withdraw, confirmed meanwhile" → `invite-already`; Remove is there."""
    shala, (anna,) = _shala(w, "Anna")
    _join(w, shala)
    w.requests.add(w.me.id, anna.id, shala, state=RequestState.APPROVED)
    w.storage.teacher_links.add(w.me.id, anna.id)

    body = _tap(w, _member("tx", shala, anna.id))

    assert body["text"].split("\n\n")[0] == _t("invite-already", name="Anna")
    assert f"t1:u:{anna.id}" in _datas(body)  # Remove… is on this card
    assert (w.me.id, anna.id) in w.storage.teacher_links.rows  # the tap removed nothing
    assert w.state(w.me.id, anna.id) is RequestState.APPROVED


def test_an_old_withdraw_with_nothing_waiting_opens_the_card(w: World) -> None:
    shala, (anna,) = _shala(w, "Anna")
    _join(w, shala)

    for data in (_member("tw", shala, anna.id), _member("tx", shala, anna.id)):
        body = _tap(w, data)

        assert body["text"].splitlines()[0] == "🏛 Ashtanga Almaty"
        assert _t("request-withdrawn") not in body["text"]
    assert w.requests.rows == {}


# The owner's hint


def test_an_owner_or_manager_is_told_when_nobody_holds_the_teacher_role(w: World) -> None:
    mine = w.storage.shalas.add_shala(w.me.id, "Mine", "almaty", code=JOIN, roles=frozenset()).id
    managed, _ = _shala(w, name="Managed", code="M4nagedC0deM4nag")
    w.storage.shalas.add_staff(managed, w.me.id, ShalaRole.ADMIN)
    office, _ = _shala(w, name="Office", code="0fficeC0de0ffice")
    w.storage.shalas.add_staff(office, w.me.id, ShalaRole.OFFICE)

    hint = _t("request-no-teachers-hint")
    assert hint in _tap(w, _on("c", mine))["text"]
    assert hint in _tap(w, _on("c", managed))["text"]
    assert hint not in _tap(w, _on("c", office))["text"]

    w.storage.shalas.add_staff(mine, _person(w, "Anna").id, ShalaRole.TEACHER)

    assert hint not in _tap(w, _on("c", mine))["text"]


# The teacher's side: one request


def test_yes_makes_the_link_and_sends_nothing(w: World, monkeypatch: pytest.MonkeyPatch) -> None:
    shala = _teach(w)
    zoe = _asks(w, shala, "Zoe")
    statements = Statements(monkeypatch, w.storage)

    body = _tap(w, f"t1:ra:{zoe.id}")

    assert body["method"] == "editMessageText"
    assert body["text"] == _t("link-student-joined", name="Zoe")
    assert _rows(body) == [[(_t("link-students-open"), "t1:s:0")]]
    link = w.storage.teacher_links.rows[(zoe.id, w.me.id)]
    assert link.linked_on == ASKED_ON  # history starts at the ask
    assert w.state(zoe.id, w.me.id) is RequestState.APPROVED
    assert w.notes(chat=int(_chat(w, zoe))) == []  # the student's note is the tick's
    assert [m.__api_method__ for m in w.out] == ["answerCallbackQuery"]
    assert statements.count == 1, statements.names


def _chat(w: World, account: Account) -> str:
    return next(
        key.provider_user_id
        for key, owner in w.storage.repo.identities.items()
        if owner == account.id
    )


def test_after_an_answer_the_rest_of_the_list_is_one_tap_away(w: World) -> None:
    shala = _teach(w)
    zoe, yan, xena = (_asks(w, shala, name) for name in ("Zoe", "Yan", "Xena"))

    yes = _tap(w, f"t1:ra:{zoe.id}")
    no = _tap(w, f"t1:rn:{yan.id}")

    assert _rows(yes) == [
        [(_t("link-students-open"), "t1:s:0")],
        [(_t("request-see-all", count=2), "t1:rl:0")],
    ]
    assert _rows(no) == [
        [(_t("request-undo"), f"t1:ru:{yan.id}")],
        [(_t("request-see-all", count=1), "t1:rl:0")],
        [(_t("link-students-open"), "t1:s:0")],
    ]
    assert w.state(xena.id, w.me.id) is RequestState.WAITING


@pytest.mark.parametrize("world", ["w", "ru"])
def test_not_my_student_tells_no_one_and_undo_brings_the_request_back(
    world: str, request: pytest.FixtureRequest
) -> None:
    w: World = request.getfixturevalue(world)
    shala = _teach(w)
    zoe = _asks(w, shala, "Zoe")

    no = _tap(w, f"t1:rn:{zoe.id}")

    assert no["text"] == _t("request-declined", w.lang, name="Zoe")
    assert _rows(no)[0] == [(_t("request-undo", w.lang), f"t1:ru:{zoe.id}")]
    assert w.state(zoe.id, w.me.id) is RequestState.DECLINED
    assert [m.__api_method__ for m in w.out] == ["answerCallbackQuery"]

    undo = _tap(w, f"t1:ru:{zoe.id}")

    assert undo["text"] == _t("request-note", w.lang, student="Zoe", shala="Ashtanga Almaty")
    assert _rows(undo) == [
        [
            (_t("request-yes-mine", w.lang), f"t1:ra:{zoe.id}"),
            (_t("request-not-mine", w.lang), f"t1:rn:{zoe.id}"),
        ],
        [(_t("log-back", w.lang), "t1:rl:0")],
    ]
    assert w.state(zoe.id, w.me.id) is RequestState.WAITING
    assert w.storage.teacher_links.rows == {}
    assert all(m.__api_method__ == "answerCallbackQuery" for m in w.out)


def test_a_double_tap_on_not_my_student_changes_nothing_more(w: World) -> None:
    shala = _teach(w)
    zoe = _asks(w, shala, "Zoe")

    first = _tap(w, f"t1:rn:{zoe.id}")
    second = _tap(w, f"t1:rn:{zoe.id}")

    assert second == first
    assert w.state(zoe.id, w.me.id) is RequestState.DECLINED


def test_a_request_opened_from_the_list_is_the_notes_screen(w: World) -> None:
    shala = _teach(w)
    zoe, _ = (_asks(w, shala, name) for name in ("Zoe", "Yan"))

    body = _tap(w, f"t1:rv:{zoe.id}")

    assert body["text"] == _t("request-note", student="Zoe", shala="Ashtanga Almaty")
    assert _rows(body) == [
        [
            (_t("request-yes-mine"), f"t1:ra:{zoe.id}"),
            (_t("request-not-mine"), f"t1:rn:{zoe.id}"),
        ],
        [(_t("request-see-all", count=2), "t1:rl:0")],
    ]


@pytest.mark.parametrize(("letter", "write"), [("ra", "approve"), ("rcy", "approve_all")])
def test_the_teachers_tap_is_answered_before_the_write(w: World, letter: str, write: str) -> None:
    """The two writes whose fake models the round trip; every `t1:` tap goes through the
    same `answered(...)`."""
    shala = _teach(w)
    zoe = _asks(w, shala, "Zoe")
    w.later(minutes=1)
    target = int(w.clock.instant.timestamp()) if letter == "rcy" else zoe.id

    _tap(w, f"t1:{letter}:{target}")

    order = w.requests.writes
    assert order.index("answerCallbackQuery") < order.index(write)


# The stale-button table (spec §5): a note stays in the chat for good


def test_yes_on_a_request_i_answered_no_still_makes_the_link_inside_the_week(w: World) -> None:
    shala = _teach(w)
    zoe = _asks(w, shala, "Zoe", RequestState.DECLINED)
    w.later(days=6)

    body = _tap(w, f"t1:ra:{zoe.id}")

    assert body["text"] == _t("link-student-joined", name="Zoe")
    assert (zoe.id, w.me.id) in w.storage.teacher_links.rows


@pytest.mark.parametrize("letter", ["ra", "rn", "ru"])
@pytest.mark.parametrize("how", ["personal link", "double tap"])
def test_a_tap_on_someone_already_linked_says_so_and_never_removes_the_link(
    w: World, letter: str, how: str
) -> None:
    shala = _teach(w)
    zoe = _asks(w, shala, "Zoe")
    if how == "personal link":
        w.storage.teacher_links.add(zoe.id, w.me.id)
    else:
        _tap(w, f"t1:ra:{zoe.id}")

    body = _tap(w, f"t1:{letter}:{zoe.id}")

    assert body["text"] == _t("request-already-student")
    assert _rows(body) == [[(_t("link-students-open"), "t1:s:0")]]
    assert (zoe.id, w.me.id) in w.storage.teacher_links.rows


GONE = (
    *("expired", "withdrawn", "student left", "role gone", "i left", "shala deleted"),
    *("account deleted", "pruned", "forged"),
)


def _make_gone(w: World, shala: UUID, zoe: Account, reason: str) -> UUID:
    """The request to me stops counting, for one of the reasons the teacher never learns."""
    shalas = w.storage.shalas
    match reason:
        case "expired":
            w.later(days=7, seconds=1)
        case "withdrawn":
            w.requests.rows[(zoe.id, w.me.id)].state = RequestState.WITHDRAWN
        case "student left":
            del shalas.students_rows[(shala, zoe.id)]
        case "role gone":
            mine = shalas.staff[(shala, w.me.id)]
            shalas.staff[(shala, w.me.id)] = replace(mine, roles=frozenset({ShalaRole.ASSISTANT}))
        case "i left":
            del shalas.staff[(shala, w.me.id)]
        case "shala deleted":
            del shalas.shalas[shala]
        case "account deleted":
            del w.storage.repo.accounts[zoe.id]
        case "pruned":
            del w.requests.rows[(zoe.id, w.me.id)]
        case _:
            return uuid4()
    return zoe.id


@pytest.mark.parametrize("reason", GONE)
@pytest.mark.parametrize("letter", ["ra", "rn", "ru", "rv"])
def test_a_request_that_is_gone_gets_one_line_whatever_the_reason(
    w: World, letter: str, reason: str
) -> None:
    shala = _teach(w)
    zoe = _asks(w, shala, "Zoe", RequestState.DECLINED if letter == "ru" else RequestState.WAITING)
    target = _make_gone(w, shala, zoe, reason)
    links = dict(w.storage.teacher_links.rows)
    writes = list(w.requests.writes)

    body = _tap(w, f"t1:{letter}:{target}")

    assert body["method"] == "editMessageText"
    assert body["text"] == _t("request-gone")  # byte for byte, the same for every reason
    still = reason == "forged" and letter != "ru"  # Zoe's own request is untouched
    rest = [[(_t("request-see-all", count=1), "t1:rl:0")]] if still else []
    assert _rows(body) == [[(_t("links-invite"), "t1:i")], *rest]  # the way out: my own link
    assert "Zoe" not in str(body)
    assert w.storage.teacher_links.rows == links
    assert [x for x in w.requests.writes if x != "answerCallbackQuery"] == writes


def test_yes_at_a_cap_says_so_and_the_request_stays(
    w: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    shala = _teach(w)
    zoe = _asks(w, shala, "Zoe")
    monkeypatch.setattr("tristhana.application.teacher_requests.CAPS", RequestCaps(students=0))

    body = _tap(w, f"t1:ra:{zoe.id}")

    assert body["text"] == _t("request-list-full")
    assert _rows(body) == [
        [(_t("link-students-open"), "t1:s:0")],
        [(_t("request-see-all", count=1), "t1:rl:0")],
    ]
    assert w.state(zoe.id, w.me.id) is RequestState.WAITING
    assert w.storage.teacher_links.rows == {}


# The waiting list and Confirm all


def test_the_waiting_list_names_each_person_and_their_shala(
    w: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    almaty = _teach(w)
    astana = _teach(w, "Ashtanga Astana", "Ast4naC0deAst4na")
    zoe = _asks(w, almaty, "Zoe")
    yan = _asks(w, astana, "Yan")
    _asks(w, almaty, "Quiet", RequestState.DECLINED)  # answered: not on the list
    statements = Statements(monkeypatch, w.storage)

    body = _tap(w, "t1:rl:0")

    assert body["text"] == "\n".join([_t("request-list-title", count=2), _t("request-list-hint")])
    assert _rows(body) == [
        [("Zoe · Ashtanga Almaty", f"t1:rv:{zoe.id}")],
        [("Yan · Ashtanga Astana", f"t1:rv:{yan.id}")],
        [(_t("request-all", count=2), f"t1:rc:{_moment(w)}")],  # the moment it was drawn
        [(_t("log-back"), "t1:s:0")],
    ]
    assert statements.count == 1, statements.names


def test_the_waiting_list_pages_by_ten(w: World) -> None:
    shala = _teach(w)
    people = [_asks(w, shala, f"S{i:02}") for i in range(23)]

    first = _tap(w, "t1:rl:0")
    last = _tap(w, "t1:rl:2")
    beyond = _tap(w, "t1:rl:7")

    assert [text for text, _ in _rows(first)[9]] == ["S09 · Ashtanga Almaty"]
    assert _rows(first)[10] == [(_t("page-next"), "t1:rl:1")]
    assert _rows(first)[11] == [(_t("request-all", count=23), f"t1:rc:{_moment(w)}")]
    assert _rows(last)[:3] == [
        [(f"S{i} · Ashtanga Almaty", f"t1:rv:{people[i].id}")] for i in (20, 21, 22)
    ]
    assert _rows(last)[3] == [(_t("page-prev"), "t1:rl:1")]
    assert (beyond["text"], _rows(beyond)) == (first["text"], _rows(first))


@pytest.mark.parametrize(
    "data", ["t1:rl:0", "t1:rl:3", "t1:rc", "t1:rc:1795000000", "t1:rcy:1795000000"]
)
def test_with_nobody_waiting_the_list_says_so_and_leads_back(w: World, data: str) -> None:
    body = _tap(w, data)

    assert body["text"] == _t("request-list-empty")
    assert _rows(body) == [[(_t("log-back"), "t1:s:0")]]


@pytest.mark.parametrize("world", ["w", "ru"])
def test_confirm_all_names_how_many_then_confirms_them(
    world: str, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    w: World = request.getfixturevalue(world)
    shala = _teach(w)
    people = [_asks(w, shala, name) for name in ("Zoe", "Yan", "Xena")]
    w.later(minutes=5)
    moment = _moment(w)
    listed = _tap(w, "t1:rl:0")
    assert _rows(listed)[3] == [(_t("request-all", w.lang, count=3), f"t1:rc:{moment}")]
    w.later(seconds=40)  # the teacher reads the names
    statements = Statements(monkeypatch, w.storage)

    ask = _tap(w, f"t1:rc:{moment}")

    assert ask["text"] == _t("request-all-ask", w.lang, count=3)
    assert _rows(ask) == [
        [(_t("request-all-yes", w.lang), f"t1:rcy:{moment}")],  # the list's moment, not this one
        [(_t("log-back", w.lang), "t1:rl:0")],
    ]
    assert w.storage.teacher_links.rows == {}  # nothing yet
    assert statements.count == 1, statements.names
    statements.names.clear()

    done = _tap(w, f"t1:rcy:{moment}")

    assert done["text"] == _t("request-all-done", w.lang, count=3)
    assert _rows(done) == [[(_t("link-students-open", w.lang), "t1:s:0")]]
    assert set(w.storage.teacher_links.rows) == {(p.id, w.me.id) for p in people}
    assert all(m.__api_method__ == "answerCallbackQuery" for m in w.out)  # no note from here
    assert statements.count == 1, statements.names


def _confirm_all(listed: Any) -> str:
    """The list's "Confirm all" button, as it was drawn."""
    return next(data for data in _datas(listed) if data.startswith("t1:rc:"))


def test_someone_who_asks_between_the_list_and_the_confirm_all_tap_stays_waiting(
    w: World,
) -> None:
    """The teacher confirms who they saw: the list is drawn with three names, a stranger
    asks ten seconds later, and "Confirm all" is tapped twenty seconds after that."""
    shala = _teach(w)
    seen = [_asks(w, shala, name) for name in ("Zoe", "Yan", "Xena")]
    w.later(minutes=5)
    listed = _tap(w, "t1:rl:0")
    w.later(seconds=10)
    stranger = _asks(w, shala, "Stranger")
    w.later(seconds=20)

    ask = _tap(w, _confirm_all(listed))

    assert ask["text"] == _t("request-all-ask", count=3)  # the three on the list, not four
    assert _datas(ask)[0] == _confirm_all(listed).replace("t1:rc:", "t1:rcy:")
    w.later(seconds=5)

    done = _tap(w, _datas(ask)[0])

    assert done["text"] == _t("request-all-done", count=3)
    assert _rows(done) == [
        [(_t("link-students-open"), "t1:s:0")],
        [(_t("request-see-all", count=1), "t1:rl:0")],
    ]
    assert set(w.storage.teacher_links.rows) == {(p.id, w.me.id) for p in seen}
    assert w.state(stranger.id, w.me.id) is RequestState.WAITING


def test_a_request_in_the_lists_own_second_is_left_waiting_on_either_side_of_it(
    w: World,
) -> None:
    """The moment is whole seconds, rounded down, and the comparison is strict. Rounding up
    (or `<=`) would confirm someone who asked after the list in its own second, unseen. So
    the one who asked just before the list in that second waits too: not confirmed, not
    lost, and on the next list."""
    shala = _teach(w)
    zoe = _asks(w, shala, "Zoe")
    w.later(seconds=2)
    seen = _asks(w, shala, "Seen")  # in the list's second, before it: on the list
    listed = _tap(w, "t1:rl:0")
    unseen = _asks(w, shala, "Unseen")  # in the same second, after it: not on the list
    assert [text for row in _rows(listed)[:2] for text, _ in row] == [
        "Zoe · Ashtanga Almaty",
        "Seen · Ashtanga Almaty",
    ]
    assert _confirm_all(listed) == f"t1:rc:{_moment(w)}"
    w.later(seconds=30)

    ask = _tap(w, _confirm_all(listed))
    done = _tap(w, _datas(ask)[0])

    assert ask["text"] == _t("request-all-ask", count=1)  # the count it will confirm
    assert done["text"] == _t("request-all-done", count=1)
    assert set(w.storage.teacher_links.rows) == {(zoe.id, w.me.id)}
    assert w.state(unseen.id, w.me.id) is RequestState.WAITING  # never confirmed unseen
    assert w.state(seen.id, w.me.id) is RequestState.WAITING  # and not lost:
    assert _rows(done)[1] == [(_t("request-see-all", count=2), "t1:rl:0")]
    again = _tap(w, "t1:rl:0")  # the next list carries a later moment and takes both
    assert _tap(w, _datas(_tap(w, _confirm_all(again)))[0])["text"] == _t(
        "request-all-done", count=2
    )


def test_a_list_with_only_its_own_seconds_requests_is_drawn_again(w: World) -> None:
    """Nobody to confirm for that moment: no confirm step with a wrong count, the list."""
    shala = _teach(w)
    zoe = _asks(w, shala, "Zoe")
    listed = _tap(w, "t1:rl:0")
    w.later(seconds=3)

    body = _tap(w, _confirm_all(listed))

    assert body["text"].splitlines()[0] == _t("request-list-title", count=1)
    assert _confirm_all(body) == f"t1:rc:{_moment(w)}"
    assert w.state(zoe.id, w.me.id) is RequestState.WAITING


def test_confirm_all_without_a_moment_only_draws_the_list(w: World) -> None:
    """`t1:rc` was never on a button; it must confirm nobody."""
    shala = _teach(w)
    zoe = _asks(w, shala, "Zoe")
    w.later(minutes=5)

    body = _tap(w, "t1:rc")

    assert (body["text"], _rows(body)) == (lambda b: (b["text"], _rows(b)))(_tap(w, "t1:rl:0"))
    assert w.state(zoe.id, w.me.id) is RequestState.WAITING


def test_confirm_all_leaves_a_late_arrival_and_a_declined_one(w: World) -> None:
    """Spec §2: it approves only requests made before the moment the list was drawn, and
    never a declined one; the reply carries the count."""
    shala = _teach(w)
    zoe = _asks(w, shala, "Zoe")
    quiet = _asks(w, shala, "Quiet", RequestState.DECLINED)
    w.later(minutes=5)
    ask = _tap(w, _confirm_all(_tap(w, "t1:rl:0")))
    assert ask["text"] == _t("request-all-ask", count=1)
    w.later(seconds=1)
    late = _asks(w, shala, "Late")  # asks a second after the screen was drawn
    w.later(minutes=1)

    done = _tap(w, _datas(ask)[0])

    assert done["text"] == _t("request-all-done", count=1)
    assert _rows(done) == [
        [(_t("link-students-open"), "t1:s:0")],
        [(_t("request-see-all", count=1), "t1:rl:0")],
    ]
    assert set(w.storage.teacher_links.rows) == {(zoe.id, w.me.id)}
    assert w.state(late.id, w.me.id) is RequestState.WAITING
    assert w.state(quiet.id, w.me.id) is RequestState.DECLINED


def test_an_old_confirm_all_confirms_only_who_is_still_waiting(w: World) -> None:
    """Stale table: the list changed since."""
    shala = _teach(w)
    zoe, yan = (_asks(w, shala, name) for name in ("Zoe", "Yan"))
    w.later(minutes=5)
    ask = _tap(w, _confirm_all(_tap(w, "t1:rl:0")))
    w.requests.rows[(yan.id, w.me.id)].state = RequestState.WITHDRAWN

    done = _tap(w, _datas(ask)[0])
    again = _tap(w, _datas(ask)[0])

    assert done["text"] == _t("request-all-done", count=1)
    assert set(w.storage.teacher_links.rows) == {(zoe.id, w.me.id)}
    assert again["text"] == _t("request-list-empty")  # a second tap: the list as it is now


def test_an_old_confirm_all_with_only_newer_requests_shows_the_list(w: World) -> None:
    shala = _teach(w)
    w.later(minutes=5)
    old = f"t1:rcy:{int(w.clock.instant.timestamp())}"
    w.later(minutes=5)
    zoe = _asks(w, shala, "Zoe")

    body = _tap(w, old)

    assert body["text"].splitlines()[0] == _t("request-list-title", count=1)
    assert w.state(zoe.id, w.me.id) is RequestState.WAITING


# Where the count shows


@pytest.mark.parametrize("students", [0, 2])
def test_my_students_shows_how_many_wait_even_when_the_list_is_empty(
    w: World, students: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    shala = _teach(w)
    for i in range(students):
        w.storage.teacher_links.add(_person(w, f"Linked{i}").id, w.me.id)
    before = _tap(w, "t1:s:0")
    _asks(w, shala, "Zoe")
    _asks(w, shala, "Yan")
    statements = Statements(monkeypatch, w.storage)

    body = _tap(w, "t1:s:0")

    assert _rows(body) == [[(_t("request-waiting-open", count=2), "t1:rl:0")], *_rows(before)]
    assert body["text"] == before["text"]
    assert _datas(body)[-1] == "w1:m"
    assert statements.names.count("InMemoryTeacherRequests.mine") == 1
    assert statements.count == 2, statements.names  # the list, and the count beside it


def test_a_teachers_shala_card_shows_how_many_wait(
    w: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    shala = _teach(w)
    zoe = _person(w, "Zoe")
    w.storage.shalas.add_student(shala, zoe.id)
    before = _tap(w, _on("c", shala))
    w.requests.add(zoe.id, w.me.id, shala)
    statements = Statements(monkeypatch, w.storage)

    body = _tap(w, _on("c", shala))

    assert _rows(body) == [[(_t("request-waiting-open", count=1), "t1:rl:0")], *_rows(before)]
    assert "Zoe" not in body["text"]
    # Spec §7: +1, in parallel. Not `choices` (nothing for staff) and then the count.
    assert [n for n in statements.names if "TeacherRequests" in n] == [
        "InMemoryTeacherRequests.card"
    ]


def test_the_shala_card_costs_the_same_for_a_teacher_a_student_and_other_staff(
    w: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The card, its pin and one read of requests, side by side, whoever opens it."""
    taught = _teach(w)
    joined, _ = _shala(w, "Anna", name="Ashtanga Astana", code="Ast4naC0deAst4na")
    _join(w, joined)
    desk, _ = _shala(w, "Boris", name="Ashtanga Aktau", code="Akt4uC0deAkt4uC0")
    w.storage.shalas.add_staff(desk, w.me.id, ShalaRole.OFFICE)
    _asks(w, taught, "Zoe")
    statements = Statements(monkeypatch, w.storage)
    cost: dict[str, list[str]] = {}

    for name, shala in {"teacher": taught, "student": joined, "front desk": desk}.items():
        statements.clear()
        body = _tap(w, _on("c", shala))
        cost[name] = sorted(statements.names)
        # People wait for me as a teacher, in a shala where I teach: shown only there.
        assert ("t1:rl:0" in _datas(body)) is (name == "teacher"), name

    assert cost["teacher"] == cost["student"] == cost["front desk"]
    assert cost["teacher"].count("InMemoryTeacherRequests.card") == 1
    assert len(cost["teacher"]) == len(set(cost["teacher"]))  # no read twice
    assert not [n for n in cost["teacher"] if "choices" in n or "mine" in n]


def test_nobody_else_sees_that_someone_is_waiting(w: World) -> None:
    """Q322: not the owner, a manager or other staff."""
    shala, (anna,) = _shala(w, "Anna")
    w.storage.shalas.add_staff(shala, w.me.id, ShalaRole.ADMIN)
    zoe = _person(w, "Zoe")
    w.storage.shalas.add_student(shala, zoe.id)
    w.requests.add(zoe.id, anna.id, shala)

    for data in (_on("c", shala), "t1:s:0", "t1:rl:0", f"t1:rv:{zoe.id}"):
        body = _tap(w, data)
        assert "t1:rl:0" not in _datas(body) or body["text"] == _t("request-list-empty")
        assert "⏳" not in str(body)

    for letter in ("ra", "rn"):  # and an id is no capability
        assert _tap(w, f"t1:{letter}:{zoe.id}")["text"] == _t("request-gone")
    assert w.state(zoe.id, anna.id) is RequestState.WAITING
    assert w.storage.teacher_links.rows == {}


# Sizes and the callback data


def test_every_request_screen_keeps_its_data_within_64_bytes_and_fits_long_names(
    ru: World,
) -> None:
    w = ru
    long = "Я" * 64
    owner = person(w.storage, "2001", long)
    shala = w.storage.shalas.add_shala(owner.id, long, "almaty", code=JOIN).id
    for i in range(4):
        w.storage.shalas.add_staff(
            shala, person(w.storage, f"30{i}", long[:-1] + str(i)).id, ShalaRole.TEACHER
        )
    w.storage.repo.accounts[w.me.id] = replace(w.me, display_name=long)
    me = next(a for a in w.storage.repo.accounts.values() if a.locale == "ru")
    w.storage.shalas.add_student(shala, me.id)
    bodies = [_tap(w, _on("t", shala)), _tap(w, _on("td", shala))]
    w.requests.add(me.id, owner.id, shala)
    bodies += [_tap(w, _on("c", shala)), _tap(w, _member("tw", shala, owner.id))]
    mine = w.storage.shalas.add_shala(me.id, long, "almaty", code="M1neC0deM1neC0de").id
    for i in range(12):
        student = person(w.storage, f"40{i:02}", long[:-2] + f"{i:02}")
        w.storage.shalas.add_student(mine, student.id)
        w.requests.add(student.id, me.id, mine)
    w.later(minutes=5)
    bodies += [_tap(w, "t1:rl:0"), _tap(w, "t1:rl:1"), _tap(w, "t1:rc"), _tap(w, "t1:s:0")]
    bodies.append(_tap(w, _confirm_all(bodies[-4])))
    assert bodies[-1]["text"] == _t("request-all-ask", "ru", count=12)
    first = next(iter(w.requests.rows.values())).student_id
    bodies += [_tap(w, f"t1:rv:{first}"), _tap(w, f"t1:rn:{first}"), _tap(w, f"t1:ru:{first}")]
    bodies += [_tap(w, f"t1:ra:{first}"), _tap(w, f"t1:ra:{uuid4()}")]

    for body in bodies:
        assert body["method"] == "editMessageText"
        assert len(body["text"]) <= 4096
        for data in _datas(body):
            assert len(data.encode()) <= 64, data


def test_the_longest_data_is_the_consent_tap() -> None:
    longest = shala_cb.on_member("ta", uuid4(), uuid4())

    assert len(longest.encode()) == 51
    assert len(f"t1:ra:{uuid4()}".encode()) == 42
    assert len(link_cb.confirm_all(9_999_999_999).encode()) <= 64
    assert len(link_cb.ask_all(9_999_999_999).encode()) <= 64


@pytest.mark.parametrize(
    "data",
    [
        "h1:t",
        "h1:t:short",
        f"h1:ta:{short_id(uuid4())}",
        f"h1:tw:{short_id(uuid4())}:nope",
        f"h1:tz:{short_id(uuid4())}",
        "t1:ra",
        "t1:ra:not-a-uuid",
        f"t1:rz:{uuid4()}",
        "t1:rl",
        "t1:rl:-1",
        "t1:rl:12345",
        "t1:rc:1",
        "t1:rc:0123456789",
        "t1:rc:1795000000:1",
        "t1:rcy",
        "t1:rcy:12",
        "t1:rcy:99999999999",
        "t1:rcy:0123456789",
        "t1:rcy:１２３４５６７８９０",
    ],
)
def test_malformed_request_data_decodes_to_nothing_and_is_only_answered(
    w: World, data: str
) -> None:
    decode = shala_cb.decode if data.startswith("h1") else link_cb.decode

    assert decode(data) is None
    assert _tap(w, data) is None
    assert [m.__api_method__ for m in w.out] == ["answerCallbackQuery"]


def test_the_new_data_round_trips() -> None:
    shala, account = uuid4(), uuid4()

    for action in ("t", "td", "tn"):
        assert shala_cb.decode(_on(action, shala)) == shala_cb.Shala(action, shala)  # type: ignore[arg-type]
    for action in ("ta", "tw", "tx"):
        found = shala_cb.decode(_member(action, shala, account))
        assert found == shala_cb.Member(action, shala, account)  # type: ignore[arg-type]
    for action in ("ra", "rn", "ru", "rv"):
        assert link_cb.decode(f"t1:{action}:{account}") == link_cb.OnPerson(action, account)  # type: ignore[arg-type]
    assert link_cb.decode(link_cb.waiting(3)) == link_cb.Waiting(3)
    assert link_cb.decode("t1:rc") == link_cb.Tap("rc")
    assert link_cb.decode(link_cb.ask_all(1795000000)) == link_cb.AskAll(1795000000)
    assert link_cb.decode(link_cb.confirm_all(1795000000)) == link_cb.ConfirmAll(1795000000)
