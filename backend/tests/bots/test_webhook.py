"""The Telegram webhook route end to end (no network: replies go back in the HTTP response)."""

import itertools
import subprocess
import sys
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import InMemoryStorage
from tristhana.infrastructure.i18n.fluent import FluentTranslator
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
_ids = itertools.count(1000)


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": "test",
        "telegram_bot_token": SecretStr(TOKEN),
        "telegram_webhook_secret": SecretStr(SECRET),
    }
    return Settings(**(values | overrides))


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def bot_client(storage: InMemoryStorage) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(), storage)) as client:
        yield client


def _update(
    text: str, *, language_code: str | None = "en", chat_type: str = "private", update_id: int = 0
) -> dict[str, Any]:
    user: dict[str, Any] = {"id": 42, "is_bot": False, "first_name": "Ash"}
    if language_code is not None:
        user["language_code"] = language_code
    entities = (
        [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
        if text.startswith("/")
        else None
    )
    message: dict[str, Any] = {
        "message_id": 7,
        "date": 1_760_000_000,
        "chat": {"id": 42 if chat_type == "private" else -100, "type": chat_type},
        "from": user,
        "text": text,
    }
    if entities:
        message["entities"] = entities
    return {"update_id": update_id or next(_ids), "message": message}


def _post(client: TestClient, body: Any, secret: str | None = SECRET) -> Any:
    headers = {"X-Telegram-Bot-Api-Secret-Token": secret} if secret is not None else {}
    return client.post("/telegram/webhook", json=body, headers=headers)


@pytest.mark.parametrize("secret", [None, "wrong", ""])
def test_rejects_missing_or_wrong_secret(bot_client: TestClient, secret: str | None) -> None:
    assert _post(bot_client, _update("/start"), secret=secret).status_code == 401


@pytest.mark.parametrize(
    ("language_code", "greeting"),
    [("en", "Namaste 🙏"), ("ru-RU", "Намасте 🙏"), ("kk", "Намасте 🙏"), (None, "Namaste 🙏")],
)
def test_start_replies_in_the_webhook_response(
    bot_client: TestClient, language_code: str | None, greeting: str
) -> None:
    response = _post(bot_client, _update("/start", language_code=language_code))

    assert response.status_code == 200
    body = response.json()
    assert body["method"] == "sendMessage"
    assert body["chat_id"] == 42
    assert body["text"].startswith(greeting)


def test_help_and_fallback(bot_client: TestClient) -> None:
    help_text = _post(bot_client, _update("/help", language_code="ru")).json()["text"]
    other = _post(bot_client, _update("hello", language_code="en")).json()["text"]

    assert "/log" in help_text
    assert other.startswith("I can't answer messages yet")


def test_ignores_group_chats(bot_client: TestClient) -> None:
    response = _post(bot_client, _update("/start", chat_type="group"))

    assert response.status_code == 200
    assert response.content == b""


def test_malformed_update_is_acknowledged(bot_client: TestClient) -> None:
    response = bot_client.post(
        "/telegram/webhook",
        content=b"{not json",
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET, "Content-Type": "application/json"},
    )

    assert response.status_code == 200


def test_duplicate_update_is_handled_once(bot_client: TestClient) -> None:
    update = _update("/start", update_id=999_001)

    first = _post(bot_client, update)
    second = _post(bot_client, update)

    assert first.json()["method"] == "sendMessage"
    assert second.status_code == 200
    assert second.content == b""


def test_handler_error_is_acknowledged(monkeypatch: pytest.MonkeyPatch) -> None:
    from tristhana.application.accounts import EnsureAccount

    async def boom(self: EnsureAccount, profile: object) -> object:
        raise RuntimeError("bug")

    monkeypatch.setattr(EnsureAccount, "execute", boom)
    with TestClient(create_app(_settings(), InMemoryStorage())) as client:
        assert _post(client, _update("/start")).status_code == 200


def test_route_absent_without_secrets() -> None:
    settings = _settings(telegram_webhook_secret=None)
    with TestClient(create_app(settings, InMemoryStorage())) as client:
        assert _post(client, _update("/start")).status_code == 404


def test_webhook_is_not_in_openapi(bot_client: TestClient) -> None:
    assert "/telegram/webhook" not in bot_client.get("/openapi.json").json()["paths"]


def test_importing_the_app_does_not_load_aiogram_fluent_or_sqlalchemy() -> None:
    code = (
        "import sys, tristhana.main; "
        "print(sorted(m for m in ('aiogram', 'fluent.runtime', 'sqlalchemy') if m in sys.modules))"
    )
    out = subprocess.run(  # noqa: S603 - fixed interpreter and code
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip().splitlines()[-1] == "[]"


def test_runtime_is_preloaded_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    import tristhana.main

    built: list[str] = []
    real = tristhana.main.build_runtime

    def recording(*args: Any) -> Any:
        built.append("runtime")
        return real(*args)

    monkeypatch.setattr(tristhana.main, "build_runtime", recording)
    app = create_app(_settings(), InMemoryStorage())
    assert built == []

    with TestClient(app):
        assert built == ["runtime"]  # before any request


def test_polling_failure_is_logged_and_shutdown_is_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    import logging

    import tristhana.bots.telegram.polling as polling
    import tristhana.main

    async def broken(runtime: object) -> None:
        raise RuntimeError("Unauthorized")

    messages: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            messages.append(record.getMessage())

    monkeypatch.setattr(polling, "run_polling", broken)
    app = create_app(
        _settings(telegram_mode="polling", telegram_webhook_secret=None), InMemoryStorage()
    )
    logging.getLogger(tristhana.main.__name__).addHandler(handler := Capture())
    try:
        with TestClient(app) as client:
            client.get("/api/v1/health")  # let the polling task run and fail
    finally:
        logging.getLogger(tristhana.main.__name__).removeHandler(handler)

    assert "telegram polling stopped: RuntimeError" in messages


def test_start_offers_the_mini_app_when_configured() -> None:
    settings = _settings(miniapp_url="https://tristhana.web.app")
    with TestClient(create_app(settings, InMemoryStorage())) as client:
        body = _post(client, _update("/start", language_code="ru")).json()

    [language, app] = body["reply_markup"]["inline_keyboard"][-1]
    assert language == {"text": "🗣 English", "callback_data": "o1:l:en"}
    assert app["web_app"] == {"url": "https://tristhana.web.app"}
    assert app["text"] == "Открыть приложение"


def test_start_without_a_mini_app_url_has_only_the_language_button(
    bot_client: TestClient,
) -> None:
    body = _post(bot_client, _update("/start")).json()

    assert body["reply_markup"]["inline_keyboard"][-1] == [
        {"text": "🗣 Русский", "callback_data": "o1:l:ru"}
    ]


def test_first_message_creates_the_account(
    bot_client: TestClient, storage: InMemoryStorage
) -> None:
    _post(bot_client, _update("/start", language_code="ru"))

    [account] = storage.repo.accounts.values()
    assert (account.display_name, account.locale) == ("Ash", "ru")


def test_language_change_in_telegram_updates_the_account(
    bot_client: TestClient, storage: InMemoryStorage
) -> None:
    _post(bot_client, _update("/start", language_code="ru"))

    body = _post(bot_client, _update("/help", language_code="en")).json()

    [account] = storage.repo.accounts.values()
    assert account.locale == "en"
    assert body["text"].startswith("I'm Tristhana")


def test_database_down_gets_a_gentle_retry(
    bot_client: TestClient, storage: InMemoryStorage
) -> None:
    storage.repo.down = True

    body = _post(bot_client, _update("/start", language_code="ru")).json()

    assert body["method"] == "sendMessage"
    assert body["text"] == FluentTranslator().t("ru", "error-temporary")


def test_group_chats_create_no_account(bot_client: TestClient, storage: InMemoryStorage) -> None:
    _post(bot_client, _update("/start", chat_type="group"))

    assert storage.repo.accounts == {}


def test_works_without_a_database_configured() -> None:
    # No DATABASE_URL (container smoke test): the bot still answers, with the retry message.
    with TestClient(create_app(_settings())) as client:
        body = _post(client, _update("/start")).json()

    assert "try again in a minute" in body["text"]


def _callback(user_is_bot: bool = False) -> dict[str, Any]:
    user = {"id": 42, "is_bot": user_is_bot, "first_name": "Ash", "language_code": "en"}
    message = {"message_id": 7, "date": 1_760_000_000, "chat": {"id": 42, "type": "private"}}
    callback = {"id": "cb1", "from": user, "chat_instance": "ci", "data": "x", "message": message}
    return {"update_id": next(_ids), "callback_query": callback}


def test_callback_with_database_down_gets_a_toast(
    bot_client: TestClient, storage: InMemoryStorage
) -> None:
    from aiogram import Router

    import tristhana.bots.telegram.router as router_module

    storage.repo.down = True
    real = router_module.build_router

    def with_callback_handler(*args: Any) -> Router:
        router = real(*args)
        router.callback_query.register(lambda *_: None)  # pyright: ignore[reportUnknownLambdaType]
        return router

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(router_module, "build_router", with_callback_handler)
        with TestClient(create_app(_settings(), storage)) as client:
            body = _post(client, _callback()).json()

    assert body["method"] == "answerCallbackQuery"
    assert body["callback_query_id"] == "cb1"
    assert "try again" in body["text"]


def test_bot_senders_get_no_reply_and_no_account(
    bot_client: TestClient, storage: InMemoryStorage
) -> None:
    update = _update("/start")
    update["message"]["from"]["is_bot"] = True

    response = _post(bot_client, update)

    assert response.content == b""
    assert storage.repo.accounts == {}
