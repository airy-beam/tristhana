"""Profile settings (ID-06): explicit choices stick; null goes back to Telegram's."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from tristhana.domain.accounts import (
    Account,
    ExternalProfile,
    IdentityKey,
    IdentityProvider,
    InvalidDisplayName,
    InvalidTimezone,
    ProfilePatch,
    profile_refresh,
    resolve_profile,
)

NOW = datetime(2026, 10, 19, 5, tzinfo=UTC)
ME = Account(uuid4(), "Ash", "en", "Asia/Almaty", NOW)
TG = ExternalProfile(IdentityKey(IdentityProvider.TELEGRAM, "42"), "Telegram Ash", "kk")


def test_a_chosen_name_and_language_survive_the_next_contact() -> None:
    custom = replace(ME, display_name="Ашенька", name_custom=True, locale="en", locale_custom=True)

    update = profile_refresh(custom, TG, NOW)

    assert update is None  # nothing changed, last seen is fresh


def test_only_the_unchosen_field_follows_telegram() -> None:
    custom = replace(ME, display_name="Ашенька", name_custom=True)

    update = profile_refresh(custom, TG, NOW)

    assert update is not None
    assert (update.display_name, update.locale) == ("Ашенька", "ru")  # kk → ru


def test_resolve_name_language_zone() -> None:
    change = resolve_profile(ME, ProfilePatch("  Ash 🧘‍♀️ ", "ru", "UTC"), TG)

    assert (change.display_name, change.name_custom) == ("Ash 🧘‍♀️", True)
    assert (change.locale, change.locale_custom) == ("ru", True)
    assert change.timezone == "UTC"  # allowed as an explicit choice


def test_blank_or_null_goes_back_to_telegram() -> None:
    custom = replace(ME, display_name="X", name_custom=True, locale="ru", locale_custom=True)

    blank = resolve_profile(custom, ProfilePatch(display_name="  "), TG)
    auto = resolve_profile(custom, ProfilePatch(display_name=None, locale=None), TG)

    assert (blank.display_name, blank.name_custom) == ("Telegram Ash", False)
    assert (auto.locale, auto.locale_custom) == ("ru", False)  # negotiated from kk


def test_omitted_fields_stay() -> None:
    change = resolve_profile(ME, ProfilePatch(), TG)

    assert (change.display_name, change.locale, change.timezone) == ("Ash", "en", "Asia/Almaty")


def test_invalid_values() -> None:
    with pytest.raises(InvalidDisplayName):
        resolve_profile(ME, ProfilePatch(display_name="x" * 65), TG)
    with pytest.raises(InvalidTimezone):
        resolve_profile(ME, ProfilePatch(timezone="Etc/GMT+5"), TG)


# WH-01 part 2: "hide the 🌸 button" is one account setting (bot grids and Mini App chips).


def test_the_ladies_button_is_shown_by_default() -> None:
    assert ME.hide_ladies is False


@pytest.mark.parametrize(("sent", "hidden"), [(True, True), (False, False), (None, False)])
def test_hide_ladies_is_its_own_field_group(sent: bool | None, hidden: bool) -> None:
    change = resolve_profile(replace(ME, hide_ladies=True), ProfilePatch(hide_ladies=sent), TG)

    assert change.hide_ladies is hidden  # None = back to the default (shown)
    assert change.fields == {"hide_ladies"}


def test_other_settings_keep_the_ladies_button_as_it_is() -> None:
    change = resolve_profile(replace(ME, hide_ladies=True), ProfilePatch(locale="ru"), TG)

    assert change.hide_ladies is True
    assert "hide_ladies" not in change.fields


# PR-06: "Offer a check-in after practice" is one account setting (bot and Mini App).


def test_the_check_in_is_offered_by_default() -> None:
    assert ME.offer_check_in is True  # type: ignore[attr-defined]


@pytest.mark.parametrize(("sent", "offered"), [(True, True), (False, False), (None, True)])
def test_offer_check_in_is_its_own_field_group(sent: bool | None, offered: bool) -> None:
    me = replace(ME, offer_check_in=not offered)  # type: ignore[call-arg]

    change = resolve_profile(me, ProfilePatch(offer_check_in=sent), TG)  # type: ignore[call-arg]

    assert change.offer_check_in is offered  # type: ignore[attr-defined]  # None = default (on)
    assert change.fields == {"offer_check_in"}


def test_other_settings_keep_the_check_in_setting_as_it_is() -> None:
    me = replace(ME, offer_check_in=False)  # type: ignore[call-arg]

    change = resolve_profile(me, ProfilePatch(locale="ru"), TG)

    assert change.offer_check_in is False  # type: ignore[attr-defined]
    assert "offer_check_in" not in change.fields
