import json
import time
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


def _auth(age_s: int = 60, **user: object) -> dict[str, str]:
    profile = {"id": 42, "first_name": "Аня", "language_code": "ru"} | user
    fields = {"user": json.dumps(profile), "auth_date": str(int(time.time()) - age_s)}
    return {"Authorization": f"tma {sign(fields, TOKEN)}"}


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def api(storage: InMemoryStorage) -> Iterator[TestClient]:
    settings = Settings(app_env="test", telegram_bot_token=SecretStr(TOKEN))
    with TestClient(create_app(settings, storage)) as client:
        yield client


def test_me_creates_the_account_on_first_open(api: TestClient, storage: InMemoryStorage) -> None:
    response = api.get("/api/v1/me", headers=_auth())

    assert response.status_code == 200
    body = response.json()
    assert body | {"id": None} == {
        "id": None,
        "display_name": "Аня",
        "locale": "ru",
        "timezone": None,
        "name_from_telegram": True,
        "locale_from_telegram": True,
    }
    assert len(storage.repo.accounts) == 1


def test_me_is_stable_across_requests(api: TestClient) -> None:
    first = api.get("/api/v1/me", headers=_auth()).json()
    second = api.get("/api/v1/me", headers=_auth()).json()

    assert first["id"] == second["id"]


@pytest.mark.parametrize(
    ("headers", "code"),
    [
        ({}, "auth_missing"),
        ({"Authorization": "Bearer abc"}, "auth_missing"),
        ({"Authorization": "tma "}, "auth_missing"),
        ({"Authorization": "tma user=1&auth_date=1&hash=00"}, "auth_invalid"),
        (_auth(age_s=25 * 3600), "auth_expired"),
    ],
)
def test_me_rejects_bad_auth(api: TestClient, headers: dict[str, str], code: str) -> None:
    response = api.get("/api/v1/me", headers=headers)

    assert response.status_code == 401
    assert response.json() == {"code": code}


def test_database_down_is_503(api: TestClient, storage: InMemoryStorage) -> None:
    storage.repo.down = True

    response = api.get("/api/v1/me", headers=_auth())

    assert response.status_code == 503
    assert response.json() == {"code": "unavailable"}


def test_device_timezone_is_set_once(api: TestClient) -> None:
    first = api.post(
        "/api/v1/me/device-timezone", json={"timezone": "Asia/Almaty"}, headers=_auth()
    )
    second = api.post(
        "/api/v1/me/device-timezone", json={"timezone": "Europe/Moscow"}, headers=_auth()
    )

    assert first.status_code == second.status_code == 200
    assert first.json()["timezone"] == second.json()["timezone"] == "Asia/Almaty"


@pytest.mark.parametrize("zone", ["Etc/GMT-5", "+05:00", "Mars/Base"])
def test_device_timezone_rejects_offsets(api: TestClient, zone: str) -> None:
    response = api.post("/api/v1/me/device-timezone", json={"timezone": zone}, headers=_auth())

    assert response.status_code == 422
    assert response.json() == {"code": "invalid_timezone"}


def test_device_timezone_needs_auth(api: TestClient) -> None:
    response = api.post("/api/v1/me/device-timezone", json={"timezone": "Asia/Almaty"})

    assert response.status_code == 401


def test_health_db(api: TestClient, storage: InMemoryStorage) -> None:
    assert api.get("/api/v1/health/db").json() == {"status": "ok"}
    storage.repo.down = True
    assert api.get("/api/v1/health/db").status_code == 503


def test_health_never_touches_the_database(api: TestClient, storage: InMemoryStorage) -> None:
    storage.repo.down = True

    assert api.get("/api/v1/health").status_code == 200


def test_openapi_documents_auth_and_hides_internal_routes(api: TestClient) -> None:
    schema: dict[str, Any] = api.get("/openapi.json").json()

    assert "TelegramInitData" in schema["components"]["securitySchemes"]
    assert schema["paths"]["/api/v1/me"]["get"]["security"] == [{"TelegramInitData": []}]
    assert "/api/v1/health/db" not in schema["paths"]
    assert not any(path.startswith("/dev") for path in schema["paths"])


def test_dev_init_data_only_in_dev(storage: InMemoryStorage) -> None:
    dev = Settings(app_env="dev", dev_init_data=True, telegram_bot_token=SecretStr(TOKEN))
    with TestClient(create_app(dev, storage)) as client:
        raw = client.get("/dev/telegram-init-data", params={"lang": "ru"}).json()["init_data"]
        me = client.get("/api/v1/me", headers={"Authorization": f"tma {raw}"}).json()
    assert (me["display_name"], me["locale"]) == ("Dev", "ru")

    # APP_ENV=dev is the default, so the endpoint needs the explicit flag too.
    default = Settings(telegram_bot_token=SecretStr(TOKEN))
    with TestClient(create_app(default, storage)) as client:
        assert client.get("/dev/telegram-init-data").status_code == 404
