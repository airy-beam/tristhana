"""The directory listing through the real webhook (ID-05 spec §3, §6, §8; ADR-0042).

`/admin` is in no menu and, for anyone but a platform admin, answers exactly like any unknown
text; every `l1:` admin tap from a non-admin only answers. The teacher's status screen and
Remove; the review list, the card with the public directory as a URL button, Listed /
Not found (one confirm) / Still listed / No longer listed, a stale revision; the line on the
consent screen (never the level there) and on the teacher card (with the level and what the
line means); no name, region or note in any log line. Real use cases over in-memory ports."""

import itertools
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.directory_listing_fakes import always
from tests.fakes import InMemoryStorage
from tests.moon_follow_fakes import person
from tests.shala_fakes import shala_storage
from tristhana.bots.telegram import directory_listing_callbacks as cb
from tristhana.domain.directory_listing import (
    DIRECTORY_URL,
    ListingStatus,
    Outcome,
    Step,
    clean,
)
from tristhana.domain.locale import Locale
from tristhana.infrastructure.i18n.fluent import FluentTranslator
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
BOT = "tristhana_test_bot"
ADMIN_TG, ANNA_TG, STUDENT_TG = 42, 1001, 1003
NOW = datetime(2026, 11, 11, 4, 30, tzinfo=UTC)
CODE = "aB3dE6gH9jK2mN5p"
NAME, REGION, NOTE = "Anna Petrova-Listed", "Ruritania", "anna-site.example in the directory"
T = FluentTranslator()
_ids = itertools.count(480_000)


@dataclass
class Sent:
    name: str
    fields: dict[str, Any]


@dataclass
class Frozen:
    instant: datetime = NOW

    def now(self) -> datetime:
        return self.instant


@dataclass
class World:
    client: TestClient
    storage: InMemoryStorage
    sent: list[Sent]
    admin: UUID
    anna: UUID


def _build(monkeypatch: pytest.MonkeyPatch, *, with_admin: bool = True) -> Iterator[World]:
    import tristhana.main

    storage = shala_storage()
    storage.repo.clock.instant = NOW
    admin = person(storage, str(ADMIN_TG), "Ash").id
    anna = person(storage, str(ANNA_TG), "Anna").id
    sent: list[Sent] = []

    async def record(self: AiohttpSession, bot: object, method: Any, **options: Any) -> bool:
        sent.append(Sent(method.__api_method__, method.model_dump()))
        return True

    monkeypatch.setattr(AiohttpSession, "make_request", record)
    monkeypatch.setattr(tristhana.main, "SystemClock", Frozen)
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr(TOKEN),
        telegram_webhook_secret=SecretStr(SECRET),
        miniapp_url="https://tristhana.web.app",
        telegram_bot_username=BOT,  # pyright: ignore[reportCallIssue]
        platform_admin_ids=str(admin) if with_admin else "",  # pyright: ignore[reportCallIssue]
    )
    with TestClient(create_app(settings, storage)) as client:
        yield World(client, storage, sent, admin, anna)


@pytest.fixture
def w(monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    yield from _build(monkeypatch)


@pytest.fixture
def off(monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    yield from _build(monkeypatch, with_admin=False)


def _post(w: World, update: dict[str, Any]) -> Any:
    response = w.client.post(
        "/telegram/webhook", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}
    )
    assert response.status_code == 200
    return response.json() if response.content else None


def _user(tg: int, lang: str) -> dict[str, Any]:
    return {"id": tg, "is_bot": False, "first_name": "Ash", "language_code": lang}


def _text(w: World, text: str, tg: int = ADMIN_TG, lang: str = "en") -> Any:
    message: dict[str, Any] = {
        "message_id": next(_ids),
        "date": 1_760_000_000,
        "chat": {"id": tg, "type": "private"},
        "from": _user(tg, lang),
        "text": text,
    }
    if text.startswith("/"):
        length = len(text.split()[0])
        message["entities"] = [{"type": "bot_command", "offset": 0, "length": length}]
    return _post(w, {"update_id": next(_ids), "message": message})


def _tap(w: World, data: str, tg: int = ADMIN_TG, lang: str = "en") -> Any:
    message = {"message_id": 9, "date": 1_760_000_000, "chat": {"id": tg, "type": "private"}}
    callback = {
        "id": f"cb{next(_ids)}",
        "from": _user(tg, lang),
        "chat_instance": "ci",
        "data": data,
        "message": message | {"text": "…"},
    }
    return _post(w, {"update_id": next(_ids), "callback_query": callback})


def _buttons(body: Any) -> list[dict[str, Any]]:
    if not body:
        return []
    return [b for row in body.get("reply_markup", {}).get("inline_keyboard", []) for b in row]


def _data(body: Any) -> list[str]:
    return [b["callback_data"] for b in _buttons(body) if b.get("callback_data")]


async def _request(w: World, account: UUID | None = None, level: str | None = "certified") -> int:
    details = clean(NAME, REGION, level, NOTE)
    saved = await w.storage.listings.save(account or w.anna, details, always(Step.SEND), NOW)
    return saved.listing.revision


async def _listed(w: World, level: str | None = "certified") -> None:
    rev = await _request(w, level=level)
    await w.storage.listings.decide(w.anna, rev, Outcome.LISTED, date(2026, 11, 11), w.admin)


def _row(w: World) -> Any:
    return w.storage.listings.rows[w.anna]


# /admin and the gate


def test_admin_for_anyone_else_is_the_fallback_reply_byte_for_byte(w: World) -> None:
    probe = _text(w, "/admin", tg=ANNA_TG)
    other = _text(w, "what is this", tg=ANNA_TG)
    assert probe == other
    assert probe["text"] == T.t("en", "fallback-text")


def test_admin_with_no_admin_configured_is_the_fallback_too(off: World) -> None:
    assert _text(off, "/admin")["text"] == T.t("en", "fallback-text")


async def test_every_admin_tap_from_a_non_admin_only_answers(w: World) -> None:
    rev = await _request(w)
    before = _row(w)
    for data in (
        cb.admin_list(False, 0),
        cb.admin_list(True, 0),
        cb.admin_card(w.anna),
        cb.decide("y", w.anna, rev),
        cb.decide("n", w.anna, rev),
        cb.decide("ny", w.anna, rev),
    ):
        w.sent.clear()
        assert _tap(w, data, tg=ANNA_TG) is None
        assert [s.name for s in w.sent] == ["answerCallbackQuery"]
    assert _row(w) == before


@pytest.mark.parametrize(
    "data",
    [
        "l1:",
        "l1:zz",
        "l1:a:-1",
        "l1:a:99999",
        "l1:c:not-a-uuid",
        f"l1:y:{UUID(int=7)}:0",
        f"l1:y:{UUID(int=7)}:2147483648",
        f"l1:y:{UUID(int=7)}:12345678901",
        f"l1:y:{UUID(int=7)}",
        "l1:ny:ABCDEF00-0000-4000-8000-00000000000A:1",  # not the canonical lower case
    ],
)
def test_malformed_data_only_answers(w: World, data: str) -> None:
    assert cb.decode(data) is None
    assert _tap(w, data) is None
    assert [s.name for s in w.sent] == ["answerCallbackQuery"]


def test_a_forged_uuid_matches_no_row(w: World) -> None:
    body = _tap(w, cb.decide("y", uuid4(), 1))
    assert T.t("en", "admin-listing-stale") in body["text"]
    assert w.storage.listings.rows == {}


def test_every_callback_fits_telegrams_64_bytes() -> None:
    id_ = UUID("ffffffff-ffff-4fff-bfff-ffffffffffff")
    values = [
        cb.mine("wy"),
        cb.admin_list(True, 9999),
        cb.admin_card(id_),
        cb.decide("ny", id_, 2**31 - 1),  # the column's largest value
    ]
    assert max(len(v.encode()) for v in values) == 53
    for value in values:
        assert cb.decode(value) is not None


def test_admin_is_in_no_command_menu() -> None:
    from pathlib import Path

    tool = Path(__file__).resolve().parents[3] / "tools" / "telegram" / "set_webhook.py"
    assert '"admin"' not in tool.read_text(encoding="utf-8")


# The review


async def test_the_admin_sees_waiting_requests_and_opens_a_card(w: World) -> None:
    rev = await _request(w)
    home = _text(w, "/admin")
    assert home["method"] == "sendMessage"
    assert T.t("en", "admin-listing-title", waiting=1, listed=0) in home["text"]
    assert cb.admin_card(w.anna) in _data(home)
    assert cb.admin_list(True, 0) in _data(home)

    card = _tap(w, cb.admin_card(w.anna))
    assert card["method"] == "editMessageText"
    for value in ("Anna", NAME, REGION, NOTE, "Certified"):
        assert value in card["text"]
    assert card["link_preview_options"] == {"is_disabled": True}
    urls = [b["url"] for b in _buttons(card) if b.get("url")]
    assert urls == [DIRECTORY_URL]
    assert cb.decide("y", w.anna, rev) in _data(card)
    assert cb.decide("n", w.anna, rev) in _data(card)
    assert all("tg://" not in str(b) for b in _buttons(card))


async def test_listed_writes_the_date_and_tells_the_teacher_silently(w: World) -> None:
    rev = await _request(w)
    w.sent.clear()
    body = _tap(w, cb.decide("y", w.anna, rev))
    assert T.t("en", "admin-listing-done-listed", listed=NAME) in body["text"]
    row = _row(w)
    assert (row.status, row.checked_on, row.note) == (
        ListingStatus.LISTED,
        date(2026, 11, 11),  # 04:30 UTC is still the 11th in Almaty
        None,
    )
    notes = [s for s in w.sent if s.name == "sendMessage"]
    assert len(notes) == 1
    assert notes[0].fields["chat_id"] == ANNA_TG
    assert notes[0].fields["disable_notification"] is True
    assert notes[0].fields["text"] == T.t("en", "listing-note-listed", listed=NAME)
    assert [s.name for s in w.sent].count("answerCallbackQuery") == 1  # the tap is answered


async def test_not_found_asks_first_then_tells_the_teacher_gently(w: World) -> None:
    rev = await _request(w)
    ask = _tap(w, cb.decide("n", w.anna, rev))
    assert ask["text"] == T.t("en", "admin-listing-not-found-ask", listed=NAME)
    assert _row(w).status is ListingStatus.PENDING
    w.sent.clear()
    body = _tap(w, cb.decide("ny", w.anna, rev))
    assert T.t("en", "admin-listing-done-not-found", listed=NAME) in body["text"]
    assert (_row(w).status, _row(w).note) == (ListingStatus.NOT_FOUND, None)
    note = next(s for s in w.sent if s.name == "sendMessage")
    assert note.fields["text"] == T.t("en", "listing-note-not-found", listed=NAME)
    assert "couldn't find" not in note.fields["text"]  # never claims the name is absent


async def test_a_stale_revision_decides_nothing(w: World) -> None:
    rev = await _request(w)
    await w.storage.listings.save(
        w.anna, clean("Somebody Else", REGION, None, None), always(Step.EDIT), NOW
    )
    w.sent.clear()
    body = _tap(w, cb.decide("y", w.anna, rev))
    assert T.t("en", "admin-listing-stale") in body["text"]
    assert _row(w).status is ListingStatus.PENDING
    assert [s.name for s in w.sent] == ["answerCallbackQuery"]
    assert T.t("en", "admin-listing-stale") in _tap(w, cb.decide("n", w.anna, rev))["text"]


async def test_recheck_still_listed_tells_no_one_and_ended_tells_the_teacher(w: World) -> None:
    await _listed(w)
    listed = _tap(w, cb.admin_list(True, 0))
    assert T.t("en", "admin-listing-title", waiting=0, listed=1) in listed["text"]
    assert "November 2026" in listed["text"]  # the oldest check
    card = _tap(w, cb.admin_card(w.anna))
    labels = [b["text"] for b in _buttons(card)]
    assert T.t("en", "admin-listing-still-listed") in labels
    assert T.t("en", "admin-listing-ended") in labels

    w.sent.clear()
    _tap(w, cb.decide("y", w.anna, _row(w).revision))
    assert [s.name for s in w.sent] == ["answerCallbackQuery"]
    assert _row(w).status is ListingStatus.LISTED

    rev = _row(w).revision
    ask = _tap(w, cb.decide("n", w.anna, rev))
    assert ask["text"] == T.t("en", "admin-listing-ended-ask", listed=NAME)
    w.sent.clear()
    _tap(w, cb.decide("ny", w.anna, rev))
    assert _row(w).status is ListingStatus.NOT_FOUND
    notes = [s for s in w.sent if s.name == "sendMessage"]
    assert [n.fields["chat_id"] for n in notes] == [ANNA_TG]  # the teacher only
    assert notes[0].fields["text"] == T.t("en", "listing-note-ended", listed=NAME)


async def test_the_waiting_list_pages(w: World) -> None:
    for n in range(12):
        other = person(w.storage, str(2000 + n), f"T{n}").id
        await _request(w, other)
    first = _tap(w, cb.admin_list(False, 0))
    assert len([d for d in _data(first) if d.startswith("l1:c:")]) == 10
    assert cb.admin_list(False, 1) in _data(first)
    second = _tap(w, cb.admin_list(False, 1))
    assert len([d for d in _data(second) if d.startswith("l1:c:")]) == 2
    assert cb.admin_list(False, 0) in _data(second)


# The teacher's own screen


def test_my_status_with_no_request_points_to_the_form(w: World) -> None:
    body = _tap(w, cb.mine("o"), tg=ANNA_TG)
    assert T.t("en", "listing-intro") in body["text"]
    apps = [b["web_app"]["url"] for b in _buttons(body) if b.get("web_app")]
    assert apps == ["https://tristhana.web.app?open=listing"]
    assert cb.mine("w") not in _data(body)  # nothing to remove yet


async def test_my_status_waiting_then_remove(w: World) -> None:
    await _request(w)
    body = _tap(w, cb.mine("o"), tg=ANNA_TG, lang="ru")
    assert T.t("ru", "listing-pending", listed=NAME) in body["text"]
    assert cb.mine("w") in _data(body)
    ask = _tap(w, cb.mine("w"), tg=ANNA_TG, lang="ru")
    assert ask["text"] == T.t("ru", "listing-remove-ask")
    w.sent.clear()
    done = _tap(w, cb.mine("wy"), tg=ANNA_TG, lang="ru")
    assert T.t("ru", "listing-removed") in done["text"]
    row = _row(w)
    assert (row.status, row.name_as_listed, row.note) == (ListingStatus.WITHDRAWN, None, None)
    assert [s.name for s in w.sent] == ["answerCallbackQuery"]  # no one is told


async def test_my_status_listed_shows_the_line_and_the_level(w: World) -> None:
    await _listed(w)
    body = _tap(w, cb.mine("o"), tg=ANNA_TG)
    assert (
        "✔ Listed in the Sharath Yoga Centre teachers directory as "
        f"{NAME} (checked: November 2026)" in body["text"]
    )
    assert "Level (in the teacher's own words): Certified" in body["text"]


async def test_my_status_not_found_never_claims_the_name_is_absent(w: World) -> None:
    rev = await _request(w)
    await w.storage.listings.decide(w.anna, rev, Outcome.NOT_FOUND, date(2026, 11, 11), w.admin)
    body = _tap(w, cb.mine("o"), tg=ANNA_TG)
    assert T.t("en", "listing-not-found", listed=NAME) in body["text"]
    assert "couldn't confirm" in body["text"]


def test_the_invite_screen_has_the_quiet_row(w: World) -> None:
    labels = {b["text"]: b.get("callback_data") for b in _buttons(_tap(w, "t1:i", tg=ANNA_TG))}
    assert labels[T.t("en", "listing-open")] == cb.mine("o")


def test_no_entry_row_with_no_admin_configured(off: World) -> None:
    body = _tap(off, "t1:i", tg=ANNA_TG)
    assert T.t("en", "listing-open") not in [b["text"] for b in _buttons(body)]


async def test_my_line_can_still_be_removed_with_no_admin_configured(off: World) -> None:
    await _listed(off)
    body = _tap(off, cb.mine("o"), tg=ANNA_TG)
    assert NAME in body["text"]
    assert not [b for b in _buttons(body) if b.get("web_app")]  # no form while off
    assert cb.mine("w") in _data(body)
    _tap(off, cb.mine("wy"), tg=ANNA_TG)
    assert _row(off).status is ListingStatus.WITHDRAWN
    assert _tap(off, cb.admin_list(False, 0)) is None  # the review stays shut


# What a student sees


def _invite(w: World) -> None:
    w.storage.teacher_links.codes[w.anna] = CODE


@pytest.mark.parametrize(
    ("lang", "line"),
    [
        (
            "en",
            "✔ Listed in the Sharath Yoga Centre teachers directory as "
            f"{NAME} (checked: November 2026)",
        ),
        ("ru", f"✔ {NAME} — в списке учителей Sharath Yoga Centre (сверено: ноябрь 2026)"),
    ],
)
async def test_the_consent_screen_shows_the_line_on_its_own_and_never_the_level(
    w: World, lang: Locale, line: str
) -> None:
    await _listed(w)
    _invite(w)
    body = _text(w, f"/start t_{CODE}", tg=STUDENT_TG, lang=lang)
    paragraphs = body["text"].split("\n\n")
    assert paragraphs[1] == line  # its own paragraph, right under the ask
    assert "Certified" not in body["text"]
    assert T.t(lang, "invite-know-them") in body["text"]  # stays for everyone
    assert all("✔" not in b["text"] for b in _buttons(body))  # never on a button
    assert len(body["text"]) <= 4096


@pytest.mark.parametrize("status", ["none", "pending", "not_found"])
async def test_the_consent_screen_without_a_listing_has_no_line_and_no_gap(
    w: World, status: str
) -> None:
    if status != "none":
        rev = await _request(w)
        if status == "not_found":
            await w.storage.listings.decide(
                w.anna, rev, Outcome.NOT_FOUND, date(2026, 11, 11), w.admin
            )
    _invite(w)
    body = _text(w, f"/start t_{CODE}", tg=STUDENT_TG)
    assert "✔" not in body["text"]
    assert "directory" not in body["text"].lower()
    assert NAME not in body["text"]
    assert "\n\n\n" not in body["text"]


async def test_the_longest_names_fit_one_message_in_both_locales(w: World) -> None:
    long_name = "N" * 100
    saved = await w.storage.listings.save(
        w.anna, clean(long_name, REGION, "certified", None), always(Step.SEND), NOW
    )
    await w.storage.listings.decide(
        w.anna, saved.listing.revision, Outcome.LISTED, date(2026, 11, 11), w.admin
    )
    _invite(w)
    for lang in ("en", "ru"):
        body = _text(w, f"/start t_{CODE}", tg=STUDENT_TG, lang=lang)
        assert long_name in body["text"]
        assert len(body["text"]) <= 4096


async def test_the_teacher_card_shows_the_line_the_level_and_what_it_means(w: World) -> None:
    await _listed(w)
    student = person(w.storage, str(STUDENT_TG), "Clara").id
    boris = person(w.storage, "1002", "Boris").id
    w.storage.teacher_links.add(student, w.anna)
    w.storage.teacher_links.add(student, boris)

    listing = _tap(w, f"t1:c:{w.anna}", tg=STUDENT_TG)
    lines = listing["text"].split("\n")
    assert lines[0] == "Anna"
    assert lines[1].startswith("✔ Listed in the Sharath Yoga Centre teachers directory as ")
    assert lines[2] == "Level (in the teacher's own words): Certified"
    assert T.t("en", "listing-about") in listing["text"]

    plain = _tap(w, f"t1:c:{boris}", tg=STUDENT_TG)
    assert plain["text"].split("\n")[0] == "Boris"  # complete as it is
    assert "✔" not in plain["text"]
    assert "directory" not in plain["text"].lower()

    overview = _tap(w, "t1:o", tg=STUDENT_TG)
    assert all("✔" not in b["text"] for b in _buttons(overview))  # never on a list button
    assert "Certified" not in overview["text"]


async def test_a_listed_level_is_optional_on_the_card(w: World) -> None:
    await _listed(w, level=None)
    student = person(w.storage, str(STUDENT_TG), "Clara").id
    w.storage.teacher_links.add(student, w.anna)
    body = _tap(w, f"t1:c:{w.anna}", tg=STUDENT_TG)
    assert "Level" not in body["text"]


# Privacy


async def test_no_name_region_note_or_level_reaches_a_log(
    w: World, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    rev = await _request(w)
    _tap(w, cb.mine("o"), tg=ANNA_TG)
    _tap(w, cb.admin_card(w.anna))
    _tap(w, cb.decide("y", w.anna, rev))
    _tap(w, cb.decide("ny", w.anna, _row(w).revision))
    logged = "\n".join(r.getMessage() for r in caplog.records)
    for secret in (NAME, REGION, NOTE, "anna-site", "Certified", "certified"):
        assert secret not in logged
    assert str(w.anna) in logged  # the account id and the outcome are all that is logged


async def test_a_handler_error_logs_no_name_region_or_note(
    w: World, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    caplog.set_level(logging.DEBUG)
    rev = await _request(w)

    async def broken(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(w.storage.listings, "decide", broken)
    _tap(w, cb.decide("y", w.anna, rev))  # the webhook still answers 200 and logs the error
    assert any("boom" in str(r.exc_info or r.getMessage()) for r in caplog.records)
    logged = "\n".join(r.getMessage() + str(r.exc_info or "") for r in caplog.records)
    for secret in (NAME, REGION, NOTE, "anna-site"):
        assert secret not in logged
