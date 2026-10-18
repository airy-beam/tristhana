from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from tristhana.domain.accounts import (
    Account,
    ExternalProfile,
    IdentityKey,
    IdentityProvider,
    InvalidTimezone,
    NewAccount,
    ProfileUpdate,
    device_timezone,
    new_account,
    normalize_display_name,
    parse_timezone,
    profile_refresh,
)

NOW = datetime(2026, 10, 18, 6, 0, tzinfo=UTC)
KEY = IdentityKey(IdentityProvider.TELEGRAM, "42")


def _account(**overrides: object) -> Account:
    values: dict[str, object] = {
        "id": uuid4(),
        "display_name": "Ash",
        "locale": "en",
        "timezone": None,
        "last_seen_at": NOW - timedelta(hours=1),
    }
    return Account(**(values | overrides))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Аня", "Аня"),
        ("  Ash   Tanga ", "Ash Tanga"),
        ("Ash\u0000\u0007\nYoga", "Ash Yoga"),
        ("‮evil", "evil"),  # bidi override
        ("🧘‍♀️ Mira", "🧘‍♀️ Mira"),  # ZWJ emoji sequences stay intact
        ("x" * 200, "x" * 64),
        ("   ", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_display_name(raw: str | None, expected: str | None) -> None:
    assert normalize_display_name(raw) == expected


def test_new_account_from_profile() -> None:
    profile = ExternalProfile(KEY, display_name=" Аня ", language_code="kk")

    assert new_account(profile) == NewAccount(display_name="Аня", locale="ru")


def test_no_refresh_when_nothing_changed_and_seen_recently() -> None:
    profile = ExternalProfile(KEY, display_name="Ash", language_code="en-US")

    assert profile_refresh(_account(), profile, NOW) is None


@pytest.mark.parametrize(
    ("name", "language_code", "expected"),
    [
        ("Ashley", "en", ProfileUpdate(display_name="Ashley", locale="en")),
        ("Ash", "ru", ProfileUpdate(display_name="Ash", locale="ru")),
    ],
)
def test_refresh_when_name_or_locale_changed(
    name: str, language_code: str, expected: ProfileUpdate
) -> None:
    profile = ExternalProfile(KEY, display_name=name, language_code=language_code)

    assert profile_refresh(_account(), profile, NOW) == expected


@pytest.mark.parametrize(("hours", "refreshed"), [(23, False), (25, True)])
def test_refresh_touches_last_seen_about_once_a_day(hours: int, refreshed: bool) -> None:
    account = _account(last_seen_at=NOW - timedelta(hours=hours))
    profile = ExternalProfile(KEY, display_name="Ash", language_code="en")

    update = profile_refresh(account, profile, NOW)

    assert (update is not None) is refreshed


@pytest.mark.parametrize("name", ["Asia/Almaty", "Asia/Kolkata", "Asia/Kathmandu", "UTC"])
def test_parse_timezone_accepts_iana_zones(name: str) -> None:
    assert parse_timezone(name) == name


@pytest.mark.parametrize(
    "name",
    [
        "Etc/GMT+5",
        "Etc/GMT-14",
        "GMT+0",
        "EST",
        "+05:00",
        "UTC+5",
        "Mars/Base",
        "../etc",
        "",
        "a" * 80,
    ],
)
def test_parse_timezone_rejects_offsets_and_garbage(name: str) -> None:
    with pytest.raises(InvalidTimezone):
        parse_timezone(name)


def test_etc_utc_is_the_same_as_utc() -> None:
    assert parse_timezone("Etc/UTC") == "UTC"


@pytest.mark.parametrize(
    ("reported", "stored"), [("Asia/Almaty", "Asia/Almaty"), ("UTC", None), ("Etc/UTC", None)]
)
def test_device_utc_says_nothing_about_location(reported: str, stored: str | None) -> None:
    assert device_timezone(reported) == stored
