from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader

from tristhana.api import initdata
from tristhana.api.errors import ApiError
from tristhana.application.accounts import EnsureAccount, RecordDeviceTimezone
from tristhana.application.days import ClearDayStatus, GetDays, SetDayStatus
from tristhana.application.moon import (
    GetMoonView,
    NotificationSettingsUseCase,
    SetMoonLocation,
)
from tristhana.application.policies import Principal
from tristhana.application.ports.storage import Storage
from tristhana.application.practice import ClearPractice, GetPracticePresets, SavePractice
from tristhana.application.stats import GetYearStats
from tristhana.domain.accounts import ExternalProfile, IdentityKey, IdentityProvider
from tristhana.domain.moon import Cities
from tristhana.domain.practice import PracticeCatalog
from tristhana.settings import Settings

# Declared as an API key scheme so OpenAPI (and the generated client) documents the header.
_authorization = APIKeyHeader(
    name="Authorization",
    scheme_name="TelegramInitData",
    description="`tma <raw Telegram initData>` (ADR-0015)",
    auto_error=False,
)


def app_settings(request: Request) -> Settings:
    """The Settings the app was created with (see `tristhana.main.create_app`)."""
    return cast(Settings, request.app.state.settings)


def storage(request: Request) -> Storage:
    return cast(Storage, request.app.state.storage)


def ensure_account(request: Request) -> EnsureAccount:
    return cast(EnsureAccount, request.app.state.ensure_account)


def record_device_timezone(request: Request) -> RecordDeviceTimezone:
    return cast(RecordDeviceTimezone, request.app.state.record_device_timezone)


def year_stats(request: Request) -> "GetYearStats":
    return cast("GetYearStats", request.app.state.year_stats)


def get_days(request: Request) -> GetDays:
    return cast(GetDays, request.app.state.get_days)


def set_day_status(request: Request) -> SetDayStatus:
    return cast(SetDayStatus, request.app.state.set_day_status)


def clear_day_status(request: Request) -> ClearDayStatus:
    return cast(ClearDayStatus, request.app.state.clear_day_status)


def save_practice(request: Request) -> SavePractice:
    return cast(SavePractice, request.app.state.save_practice)


def clear_practice(request: Request) -> ClearPractice:
    return cast(ClearPractice, request.app.state.clear_practice)


def practice_presets(request: Request) -> GetPracticePresets:
    return cast(GetPracticePresets, request.app.state.practice_presets)


def practice_catalog(request: Request) -> tuple[PracticeCatalog, str]:
    """The catalog and its version (content hash, used as the ETag)."""
    state = request.app.state
    return cast(PracticeCatalog, state.practice_catalog), cast(str, state.catalog_version)


def cities(request: Request) -> Cities:
    return cast(Cities, request.app.state.cities)


def moon_view(request: Request) -> GetMoonView:
    return cast(GetMoonView, request.app.state.moon.view)


def set_moon_location(request: Request) -> SetMoonLocation:
    return cast(SetMoonLocation, request.app.state.moon.set_location)


def notification_settings(request: Request) -> NotificationSettingsUseCase:
    return cast(NotificationSettingsUseCase, request.app.state.notification_settings)


async def principal(
    request: Request,
    authorization: Annotated[str | None, Depends(_authorization)],
    ensure: Annotated[EnsureAccount, Depends(ensure_account)],
) -> Principal:
    """The caller, from verified initData; the account is created on first contact."""
    scheme, _, raw = (authorization or "").partition(" ")
    if scheme.lower() != "tma" or not raw:
        raise ApiError(401, "auth_missing")
    token = app_settings(request).telegram_bot_token
    if token is None:
        raise ApiError(503, "unavailable")
    try:
        user = initdata.verify(raw, token.get_secret_value(), datetime.now(UTC))
    except initdata.InvalidInitData as e:
        raise ApiError(401, e.code) from None
    key = IdentityKey(IdentityProvider.TELEGRAM, str(user.id))
    profile = ExternalProfile(key, display_name=user.first_name, language_code=user.language_code)
    return Principal(await ensure.execute(profile))


CurrentPrincipal = Annotated[Principal, Depends(principal)]
