"""PATCH /me and PATCH /me/notification-settings (ID-06, ADR-0021)."""

import json
import time as clock
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import InMemoryStorage
from tristhana.api.initdata import sign
from tristhana.main import create_app
from tristhana.settings import Settings

TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"


def _auth(first_name: str = "Аня", lang: str = "ru") -> dict[str, str]:
    profile = {"id": 42, "first_name": first_name, "language_code": lang}
    fields = {"user": json.dumps(profile), "auth_date": str(int(clock.time()) - 60)}
    return {"Authorization": f"tma {sign(fields, TOKEN)}"}


@pytest.fixture
def api() -> Iterator[TestClient]:
    settings = Settings(app_env="test", telegram_bot_token=SecretStr(TOKEN))
    with TestClient(create_app(settings, InMemoryStorage())) as client:
        yield client


def _patch_me(api: TestClient, body: dict[str, Any], **auth: str) -> Any:
    return api.patch("/api/v1/me", json=body, headers=_auth(**auth))


def test_name_and_language_stick_until_reset(api: TestClient) -> None:
    chosen = _patch_me(api, {"display_name": "Anna 🧘", "locale": "en"}).json()
    after_contact = api.get("/api/v1/me", headers=_auth("Аня", "ru")).json()
    reset = _patch_me(api, {"display_name": None, "locale": None}).json()

    assert (chosen["display_name"], chosen["locale"]) == ("Anna 🧘", "en")
    assert (chosen["name_from_telegram"], chosen["locale_from_telegram"]) == (False, False)
    assert (after_contact["display_name"], after_contact["locale"]) == ("Anna 🧘", "en")
    assert (reset["display_name"], reset["locale"], reset["name_from_telegram"]) == (
        "Аня",
        "ru",
        True,
    )


def test_timezone_is_explicit_and_validated(api: TestClient) -> None:
    utc = _patch_me(api, {"timezone": "UTC"})
    almaty = _patch_me(api, {"timezone": "Asia/Almaty"})
    fixed = _patch_me(api, {"timezone": "Etc/GMT+5"})
    long_name = _patch_me(api, {"display_name": "x" * 65})
    untouched = _patch_me(api, {}).json()

    assert utc.json()["timezone"] == "UTC"
    assert almaty.json()["timezone"] == "Asia/Almaty"
    assert (fixed.status_code, fixed.json()) == (422, {"code": "invalid_timezone"})
    assert (long_name.status_code, long_name.json()) == (422, {"code": "invalid_display_name"})
    assert untouched["timezone"] == "Asia/Almaty"


def test_notification_settings_patch_changes_only_what_was_sent(api: TestClient) -> None:
    url = "/api/v1/me/notification-settings"
    _ = api.patch(url, json={"practice": {"on": True, "at": "20:00:00"}}, headers=_auth())

    moon = api.patch(url, json={"moon": {"offsets": [7, 3]}}, headers=_auth()).json()
    quiet = api.patch(
        url, json={"quiet": {"start": "23:00:00", "end": "06:00:00"}}, headers=_auth()
    )
    conflict = api.patch(
        url, json={"quiet": {"start": "19:30:00", "end": "07:00:00"}}, headers=_auth()
    )
    default = api.patch(
        url, json={"moon": {"offsets": None}, "daily_cap": None}, headers=_auth()
    ).json()

    assert moon["moon"]["offsets"] == [3, 7]
    assert moon["practice"] == {
        "on": True,
        "at": "20:00:00",
        "days": [1, 2, 3, 4, 5, 7],
        "paused_start": None,  # WH-01 part 2
        "paused_until": None,
    }
    assert quiet.json()["quiet"] == {"start": "23:00:00", "end": "06:00:00"}
    # 19:30 to 07:00 would swallow the 20:00 practice and the 19:00 moon reminders.
    assert (conflict.status_code, conflict.json()) == (422, {"code": "invalid_settings"})
    assert default["moon"]["offsets"] == [1, 7]
    assert default["daily_cap"] == 3


def test_put_is_deprecated_but_still_works(api: TestClient) -> None:
    schema = api.get("/openapi.json").json()["paths"]["/api/v1/me/notification-settings"]

    assert schema["put"]["deprecated"] is True
    assert "patch" in schema


def test_a_whole_group_cannot_be_nulled(api: TestClient) -> None:
    url = "/api/v1/me/notification-settings"

    moon = api.patch(url, json={"moon": None}, headers=_auth())
    practice = api.patch(url, json={"practice": None}, headers=_auth())

    assert (moon.status_code, practice.status_code) == (422, 422)
