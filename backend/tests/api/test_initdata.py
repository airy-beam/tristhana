import json
from datetime import UTC, datetime, timedelta

import pytest
from aiogram.utils.web_app import check_webapp_signature  # test-only cross-check

from tristhana.api.initdata import InvalidInitData, TelegramUser, sign, verify

TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
NOW = datetime(2026, 10, 18, 6, 0, tzinfo=UTC)


def _fields(age: timedelta = timedelta(minutes=5), **user: object) -> dict[str, str]:
    profile = {"id": 42, "first_name": "Аня", "language_code": "ru"} | user
    return {
        "user": json.dumps(profile, ensure_ascii=False),
        "auth_date": str(int((NOW - age).timestamp())),
        "query_id": "AAH",
        "signature": "ed25519-not-checked-here",
    }


def test_valid_init_data() -> None:
    assert verify(sign(_fields(), TOKEN), TOKEN, NOW) == TelegramUser(42, "Аня", "ru")


def test_signature_matches_aiogram() -> None:
    raw = sign(_fields(), TOKEN)

    assert check_webapp_signature(TOKEN, raw)


def test_tampered_field_is_invalid() -> None:
    raw = sign(_fields(), TOKEN).replace("%D0%90%D0%BD%D1%8F", "Eve")

    with pytest.raises(InvalidInitData) as e:
        verify(raw, TOKEN, NOW)
    assert e.value.code == "auth_invalid"


@pytest.mark.parametrize(
    "raw",
    [
        sign(_fields(), "654321:another-bot-token_xxxxxxxxxxxxxxxxxxxxx"),
        "user=%7B%22id%22%3A42%7D&auth_date=1",  # no hash
        "",
        "not a query string",
        sign({"auth_date": str(int(NOW.timestamp()))}, TOKEN),  # no user
        sign(_fields(id="x"), TOKEN),
        sign(_fields(is_bot=True), TOKEN),
    ],
)
def test_invalid_init_data(raw: str) -> None:
    with pytest.raises(InvalidInitData) as e:
        verify(raw, TOKEN, NOW)
    assert e.value.code == "auth_invalid"


@pytest.mark.parametrize("age", [timedelta(hours=25), timedelta(minutes=-5)])
def test_too_old_or_from_the_future_is_expired(age: timedelta) -> None:
    with pytest.raises(InvalidInitData) as e:
        verify(sign(_fields(age), TOKEN), TOKEN, NOW)
    assert e.value.code == "auth_expired"


def test_optional_user_fields() -> None:
    raw = sign({"user": json.dumps({"id": 7}), "auth_date": str(int(NOW.timestamp()))}, TOKEN)

    assert verify(raw, TOKEN, NOW) == TelegramUser(7, None, None)
