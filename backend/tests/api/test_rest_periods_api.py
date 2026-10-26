"""WH-01 part 2 over the API (ADR-0023): the pause offer on PUT /me/days, rest periods
(start, keep, end), covered days on /me/days and /me/stats, the paused line in the
notification settings, and `hide_ladies` on /me."""

import json
import time as clock
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import InMemoryStorage
from tristhana.api.initdata import sign
from tristhana.main import create_app
from tristhana.settings import Settings

TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
PERIODS = "/api/v1/me/rest-periods"


def _auth(user_id: int = 42) -> dict[str, str]:
    profile = {"id": user_id, "first_name": "Аня", "language_code": "ru"}
    fields = {"user": json.dumps(profile), "auth_date": str(int(clock.time()) - 60)}
    return {"Authorization": f"tma {sign(fields, TOKEN)}"}


def _today() -> date:
    return (datetime.now(UTC) + timedelta(hours=5)).date()  # Asia/Almaty, no DST


def _d(offset: int) -> str:
    return (_today() + timedelta(days=offset)).isoformat()


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def api(storage: InMemoryStorage) -> Iterator[TestClient]:
    settings = Settings(app_env="test", telegram_bot_token=SecretStr(TOKEN))
    with TestClient(create_app(settings, storage)) as client:
        client.post("/api/v1/me/device-timezone", json={"timezone": "Asia/Almaty"}, headers=_auth())
        yield client


def _put_day(api: TestClient, offset: int, status: str) -> Any:
    response = api.put(f"/api/v1/me/days/{_d(offset)}", json={"status": status}, headers=_auth())
    assert response.status_code == 200
    return response.json()


def _start(api: TestClient, offset: int, days: int, kind: str) -> Any:
    return api.post(
        PERIODS, json={"start": _d(offset), "days": days, "kind": kind}, headers=_auth()
    )


def _days(api: TestClient, user_id: int = 42) -> Any:
    window = {"from": _d(-6), "to": _d(0)}
    return api.get("/api/v1/me/days", params=window, headers=_auth(user_id)).json()


# PUT /me/days → DaySaved


def test_ladies_today_returns_the_offer_with_the_servers_choices(api: TestClient) -> None:
    body = _put_day(api, 0, "ladies")

    assert body == {
        "date": _d(0),
        "status": "ladies",
        "practices": [],
        "pause_offer": {
            "start": _d(0),
            "kind": "ladies",
            "reminders_on": False,
            "choices": [2, 3, 5],
            "more": [4, 6, 7],
        },
        "period": None,
        "cut": None,
    }


@pytest.mark.parametrize("kind", ["sick", "travel"])
def test_sick_and_travel_offer_their_own_choices(api: TestClient, kind: str) -> None:
    offer = _put_day(api, -1, kind)["pause_offer"]

    assert offer["start"] == _d(-1)
    assert (offer["choices"], offer["more"]) == ([3, 4, 5], [2, 6, 7, 10, 14])


def test_the_offer_says_when_practice_reminders_are_on(api: TestClient) -> None:
    api.patch("/api/v1/me/notification-settings", json={"practice": {"on": True}}, headers=_auth())

    assert _put_day(api, 0, "sick")["pause_offer"]["reminders_on"] is True


@pytest.mark.parametrize(("offset", "status"), [(0, "rest"), (0, "practiced"), (-2, "ladies")])
def test_no_offer_for_other_statuses_or_backfill(api: TestClient, offset: int, status: str) -> None:
    assert _put_day(api, offset, status)["pause_offer"] is None


def test_no_offer_for_a_continuation(api: TestClient) -> None:
    _put_day(api, -1, "ladies")

    assert _put_day(api, 0, "ladies")["pause_offer"] is None


# POST /me/rest-periods


def test_start_a_period_and_see_it_on_the_days(api: TestClient) -> None:
    _put_day(api, -1, "ladies")

    started = _start(api, -1, 5, "ladies")
    days = _days(api)

    assert started.status_code == 200
    assert started.json() == {"start": _d(-1), "end": _d(3), "kind": "ladies"}
    assert days["periods"] == [{"start": _d(-1), "end": _d(3), "kind": "ladies"}]  # unclipped
    assert days["practice_on"] is False
    assert [d["date"] for d in days["days"]] == [_d(-1)]  # covered days are never stored


def test_covered_days_are_not_auto_days(api: TestClient) -> None:
    days_off = sorted({_today().isoweekday(), (_today() - timedelta(days=1)).isoweekday()})
    api.put("/api/v1/me/day-off", json={"day_off": days_off}, headers=_auth())
    assert {_d(-1), _d(0)} <= {a["date"] for a in _days(api)["auto"]}  # before the pause
    _put_day(api, -1, "travel")
    _start(api, -1, 7, "travel")

    auto = {a["date"] for a in _days(api)["auto"]}

    assert _d(-1) not in auto
    assert _d(0) not in auto


@pytest.mark.parametrize(
    ("offset", "days", "kind"),
    [(0, 10, "ladies"), (0, 14, "ladies"), (0, 15, "sick"), (0, 1, "travel"), (-2, 3, "sick")],
)
def test_start_refuses_choices_outside_the_kinds_set(
    api: TestClient, offset: int, days: int, kind: str
) -> None:
    response = _start(api, offset, days, kind)

    assert (response.status_code, response.json()) == (422, {"code": "invalid_rest_period"})
    assert _days(api)["periods"] == []


def test_start_allows_fourteen_days_of_sick(api: TestClient) -> None:
    assert _start(api, 0, 14, "sick").json() == {"start": _d(0), "end": _d(13), "kind": "sick"}


def test_start_refuses_a_kind_that_does_not_pause(api: TestClient) -> None:
    assert _start(api, 0, 3, "rest").status_code == 422


def test_start_refuses_a_future_day(api: TestClient) -> None:
    response = _start(api, 2, 3, "sick")

    assert (response.status_code, response.json()) == (422, {"code": "date_in_future"})


def test_periods_are_private_to_their_owner(api: TestClient) -> None:
    _start(api, 0, 3, "ladies")

    assert _days(api, user_id=43)["periods"] == []


# 🧘 inside a period, "keep the pause", end early


def test_practiced_inside_returns_the_cut_and_keep_restores_it(api: TestClient) -> None:
    _put_day(api, -1, "sick")
    _start(api, -1, 4, "sick")

    saved = _put_day(api, 0, "practiced")
    kept = api.put(
        f"{PERIODS}/{_d(-1)}", json={"end": saved["cut"]["end"], "kind": "sick"}, headers=_auth()
    )

    assert saved["cut"] == {"start": _d(-1), "end": _d(2), "kind": "sick"}
    assert saved["period"] is None
    assert kept.status_code == 200
    assert kept.json() == {"period": {"start": _d(-1), "end": _d(2), "kind": "sick"}}
    assert _days(api)["periods"] == [kept.json()["period"]]
    today = [d for d in _days(api)["days"] if d["date"] == _d(0)]
    assert today[0]["status"] == "practiced"  # the day stays practiced


def test_no_practice_inside_changes_only_that_day(api: TestClient) -> None:
    _start(api, 0, 3, "travel")

    saved = _put_day(api, 0, "skipped")

    assert saved["cut"] is None
    assert saved["period"] == {"start": _d(0), "end": _d(2), "kind": "travel"}


def test_a_stale_keep_is_null(api: TestClient) -> None:
    response = api.put(f"{PERIODS}/{_d(-4)}", json={"end": _d(-1), "kind": "sick"}, headers=_auth())

    assert (response.status_code, response.json()) == (200, {"period": None})


def test_a_keep_longer_than_the_kind_allows_is_refused(api: TestClient) -> None:
    response = api.put(
        f"{PERIODS}/{_d(-3)}", json={"end": _d(4), "kind": "ladies"}, headers=_auth()
    )  # 8 days of 🌸

    assert (response.status_code, response.json()) == (422, {"code": "invalid_rest_period"})


def test_end_early_twice(api: TestClient) -> None:
    _put_day(api, -1, "travel")
    _start(api, -1, 5, "travel")
    _put_day(api, 0, "travel")

    first = api.post(f"{PERIODS}/{_d(-1)}/end", headers=_auth())
    second = api.post(f"{PERIODS}/{_d(-1)}/end", headers=_auth())

    # Today stops being covered; yesterday alone is no period: removed.
    assert (first.status_code, first.json()) == (200, {"period": None})
    assert (second.status_code, second.json()) == (200, {"period": None})
    assert _days(api)["periods"] == []


def test_end_early_keeps_the_past_days(api: TestClient) -> None:
    # A pause that started two days ago, cut by yesterday's 🧘 and put back with "keep".
    _put_day(api, -1, "practiced")
    api.put(f"{PERIODS}/{_d(-2)}", json={"end": _d(3), "kind": "sick"}, headers=_auth())

    ended = api.post(f"{PERIODS}/{_d(-2)}/end", headers=_auth())

    assert ended.json() == {"period": {"start": _d(-2), "end": _d(-1), "kind": "sick"}}


def test_clearing_the_origin_removes_the_period(api: TestClient) -> None:
    _put_day(api, 0, "ladies")
    _start(api, 0, 3, "ladies")

    assert api.delete(f"/api/v1/me/days/{_d(0)}", headers=_auth()).status_code == 204
    assert _days(api)["periods"] == []


# /me/stats and the notification settings


def test_stats_show_covered_days_as_their_kind(api: TestClient) -> None:
    _put_day(api, -1, "sick")
    _start(api, -1, 3, "sick")

    stats = api.get("/api/v1/me/stats", headers=_auth()).json()

    assert stats["cells"][-1] == "sick"  # today: covered, not logged
    assert stats["year_total"]["rest"]["sick"] >= 1


def test_notification_settings_carry_the_pause(api: TestClient) -> None:
    url = "/api/v1/me/notification-settings"
    assert api.get(url, headers=_auth()).json()["practice"]["paused_until"] is None

    _start(api, 0, 4, "travel")
    practice = api.get(url, headers=_auth()).json()["practice"]

    assert (practice["paused_start"], practice["paused_until"]) == (_d(0), _d(3))


# /me hide_ladies


def test_hide_ladies_is_off_until_chosen_and_null_means_the_default(api: TestClient) -> None:
    assert api.get("/api/v1/me", headers=_auth()).json()["hide_ladies"] is False

    hidden = api.patch("/api/v1/me", json={"hide_ladies": True}, headers=_auth()).json()
    renamed = api.patch("/api/v1/me", json={"display_name": "Ash"}, headers=_auth()).json()
    shown = api.patch("/api/v1/me", json={"hide_ladies": None}, headers=_auth()).json()

    assert hidden["hide_ladies"] is True
    assert renamed["hide_ladies"] is True  # omitted = unchanged
    assert shown["hide_ladies"] is False


def test_openapi_has_the_new_paths_and_error_code(api: TestClient) -> None:
    schema = api.get("/openapi.json").json()

    assert "invalid_rest_period" in schema["components"]["schemas"]["ErrorCode"]["enum"]
    assert {
        "/api/v1/me/rest-periods",
        "/api/v1/me/rest-periods/{start}",
        "/api/v1/me/rest-periods/{start}/end",
    } <= set(schema["paths"])
    out = schema["components"]["schemas"]["RestPeriodOut"]
    # `rest`: a period whose seal can't be read any more is still sent, as plain rest.
    assert out["properties"]["kind"]["enum"] == ["ladies", "sick", "travel", "rest"]
    start = schema["components"]["schemas"]["StartBody"]
    assert start["properties"]["kind"]["enum"] == ["ladies", "sick", "travel"]


def test_keep_without_a_practiced_day_is_never_a_backfill(api: TestClient) -> None:
    """Review fix: a forged keep 13 days back (no 🧘 inside) creates nothing."""
    response = api.put(f"{PERIODS}/{_d(-13)}", json={"end": _d(0), "kind": "sick"}, headers=_auth())

    assert (response.status_code, response.json()) == (200, {"period": None})
    assert _days(api)["periods"] == []


def test_patching_the_reminder_keeps_the_pause_in_the_answer(api: TestClient) -> None:
    _start(api, 0, 4, "travel")

    url = "/api/v1/me/notification-settings"
    practice = api.patch(url, json={"practice": {"on": True}}, headers=_auth()).json()["practice"]

    assert (practice["paused_start"], practice["paused_until"]) == (_d(0), _d(3))


def test_a_period_whose_kind_cant_be_read_is_sent_as_rest(
    api: TestClient, storage: InMemoryStorage
) -> None:
    """Review fix: an unreadable seal reads as plain rest; the days view still shows it."""
    from tristhana.domain.days import DayStatus
    from tristhana.domain.rest_periods import RestPeriod

    [me] = storage.repo.accounts.values()
    start, end = _today() - timedelta(days=1), _today() + timedelta(days=1)
    storage.rest_periods.rows[(me.id, start)] = RestPeriod(start, end, DayStatus.REST)

    assert _days(api)["periods"] == [{"start": _d(-1), "end": _d(1), "kind": "rest"}]


def test_a_stale_keep_never_deletes_a_newer_pause(
    api: TestClient, storage: InMemoryStorage
) -> None:
    """Owner (second review): Keep after a newer pause began is `period: null`."""
    from tristhana.domain.days import DayStatus
    from tristhana.domain.rest_periods import RestPeriod

    [me] = storage.repo.accounts.values()
    first = _today() - timedelta(days=4)
    storage.rest_periods.rows[(me.id, first)] = RestPeriod(
        first, _today() + timedelta(days=2), DayStatus.LADIES
    )
    assert _put_day(api, -2, "practiced")["cut"] is not None  # cuts it to [-4, -3]
    _put_day(api, -1, "sick")
    _start(api, -1, 5, "sick")

    kept = api.put(f"{PERIODS}/{_d(-4)}", json={"end": _d(2), "kind": "ladies"}, headers=_auth())

    assert (kept.status_code, kept.json()) == (200, {"period": None})
    assert _days(api)["periods"] == [
        {"start": _d(-4), "end": _d(-3), "kind": "ladies"},
        {"start": _d(-1), "end": _d(3), "kind": "sick"},
    ]


def test_a_day_count_for_a_day_logged_otherwise_is_refused(api: TestClient) -> None:
    _put_day(api, 0, "practiced")

    response = _start(api, 0, 3, "sick")

    assert (response.status_code, response.json()) == (422, {"code": "invalid_rest_period"})
    assert _days(api)["periods"] == []
