from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader

from tristhana.api import initdata
from tristhana.api.errors import ApiError
from tristhana.application.accounts import EnsureAccount, RecordDeviceTimezone
from tristhana.application.policies import Principal
from tristhana.application.ports.storage import Storage
from tristhana.domain.accounts import ExternalProfile, IdentityKey, IdentityProvider
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
