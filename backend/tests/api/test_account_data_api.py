"""My data endpoints (ST-09, spec §4): `POST /me/exports` sends the ZIP through the bot (the
fake notifier receives a real ZIP: data.json validates, the CSVs parse), 429 with
`Retry-After`, 409 when the bot can't write, 413 too large; `DELETE /me` needs the
confirmation (422), then 204 and the account is gone; a write racing the delete is 410; the
OpenAPI lists the new codes."""

import csv
import io
import json
import time
import zipfile
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import FakeNotifier, InMemoryStorage
from tristhana.api.initdata import sign
from tristhana.application.ports.export import AccountGone
from tristhana.application.ports.notifications import DeliveryResult, DeliveryStatus
from tristhana.domain import export as export_domain
from tristhana.main import create_app
from tristhana.settings import Settings

TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"


def _auth(user_id: int = 42, lang: str = "en") -> dict[str, str]:
    profile = {"id": user_id, "first_name": "Asha", "language_code": lang}
    fields = {"user": json.dumps(profile), "auth_date": str(int(time.time()) - 60)}
    return {"Authorization": f"tma {sign(fields, TOKEN)}"}


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def notifier() -> FakeNotifier:
    return FakeNotifier()


@pytest.fixture
def api(storage: InMemoryStorage, notifier: FakeNotifier) -> Iterator[TestClient]:
    settings = Settings(app_env="test", telegram_bot_token=SecretStr(TOKEN))
    with TestClient(create_app(settings, storage, notifier)) as client:
        yield client


def _export(api: TestClient, **kw: Any) -> Any:
    return api.post("/api/v1/me/exports", json={}, headers=_auth(**kw))


def _delete(api: TestClient, body: Any = None, **kw: Any) -> Any:
    return api.request("DELETE", "/api/v1/me", json=body, headers=_auth(**kw))


def test_endpoints_need_auth(api: TestClient) -> None:
    assert api.post("/api/v1/me/exports", json={}).status_code == 401
    assert (
        api.request("DELETE", "/api/v1/me", json={"confirm": "delete-everything"}).status_code
        == 401
    )


def test_export_sends_a_real_zip_to_the_callers_chat(
    api: TestClient, notifier: FakeNotifier
) -> None:
    response = _export(api)

    assert response.status_code == 200
    body = response.json()
    ((recipient, file),) = notifier.exports
    assert recipient.telegram_id == "42"
    assert body["file_name"] == file.name
    assert body["bytes"] == len(file.content)
    z = zipfile.ZipFile(io.BytesIO(file.content))
    data = json.loads(z.read("data.json"))
    assert data["schema"] == export_domain.SCHEMA
    assert data["identities"][0]["id"] == "42"
    for name in ("days", "rest_periods", "progression"):
        rows = list(csv.reader(io.StringIO(z.read(f"{name}.csv").decode("utf-8-sig"))))
        assert rows[0]  # a header row
    assert "Rest days are part of the practice." in z.read("README.txt").decode()


def test_second_export_is_429_with_retry_after(api: TestClient) -> None:
    assert _export(api).status_code == 200

    again = _export(api)

    assert again.status_code == 429
    assert again.json()["code"] == "export_too_soon"
    assert 1 <= again.json()["retry_after_s"] <= 600
    assert again.headers["Retry-After"] == str(again.json()["retry_after_s"])


def test_blocked_bot_is_409_and_frees_the_slot(api: TestClient, notifier: FakeNotifier) -> None:
    notifier.export_outcomes.append(DeliveryResult(DeliveryStatus.BLOCKED))

    response = _export(api)

    assert response.status_code == 409
    assert response.json() == {"code": "bot_unreachable"}
    assert _export(api).status_code == 200


def test_too_large_is_413_and_nothing_is_sent(
    api: TestClient, notifier: FakeNotifier, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("tristhana.application.export.MAX_BYTES", 10)

    response = _export(api)

    assert response.status_code == 413
    assert response.json()["code"] == "export_too_large"
    assert notifier.exports == []


@pytest.mark.parametrize("body", [None, {}, {"confirm": "yes"}])
def test_delete_needs_the_confirmation(
    api: TestClient, storage: InMemoryStorage, body: Any
) -> None:
    response = _delete(api, body)

    assert response.status_code == 422
    if body != {"confirm": "yes"}:  # a wrong literal is a plain validation error
        assert response.json()["code"] == "confirmation_required"
    assert storage.accounts.deleted == []


def test_delete_is_204_and_the_account_is_gone(api: TestClient, storage: InMemoryStorage) -> None:
    me = api.get("/api/v1/me", headers=_auth()).json()["id"]

    response = _delete(api, {"confirm": "delete-everything"})

    assert response.status_code == 204
    assert [str(a) for a in storage.accounts.deleted] == [me]
    fresh = api.get("/api/v1/me", headers=_auth()).json()["id"]
    assert fresh != me  # a later call starts fresh (and the Mini App stops calling)


def test_a_write_racing_the_delete_is_410(api: TestClient, storage: InMemoryStorage) -> None:
    async def gone(*_: object, **__: object) -> Any:
        raise AccountGone

    storage.day_repo.upsert = gone  # type: ignore[method-assign]

    response = api.put("/api/v1/me/days/2026-10-20", json={"status": "practiced"}, headers=_auth())

    assert response.status_code == 410
    assert response.json() == {"code": "account_deleted"}


def test_openapi_lists_the_codes(api: TestClient) -> None:
    spec = api.get("/openapi.json").json()
    codes = spec["components"]["schemas"]["ErrorCode"]["enum"]

    for code in (
        "export_too_soon",
        "bot_unreachable",
        "export_too_large",
        "confirmation_required",
        "account_deleted",
    ):
        assert code in codes
    assert set(spec["paths"]["/api/v1/me/exports"]["post"]["responses"]) >= {
        "200",
        "409",
        "413",
        "429",
    }
    assert "204" in spec["paths"]["/api/v1/me"]["delete"]["responses"]
