"""API errors as `{"code": ...}` bodies: stable codes the Mini App can branch on."""

from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from tristhana.application.ports.export import AccountGone
from tristhana.application.ports.storage import StorageUnavailable

type ErrorCode = Literal[
    "auth_missing",
    "auth_invalid",
    "auth_expired",
    "invalid_timezone",
    "invalid_range",
    "invalid_year",
    "invalid_display_name",
    "date_in_future",
    "date_too_early",
    "day_not_practiced",
    "invalid_length",
    "invalid_practice",
    "invalid_check_in",
    "note_too_long",
    "body_too_large",
    "timezone_unknown",
    "unknown_location",
    "unknown_city",
    "invalid_settings",
    "invalid_day_off",
    "invalid_rest_period",
    "invalid_progression",
    "progression_changed",
    "not_latest",
    "export_too_soon",
    "bot_unreachable",
    "export_too_large",
    "confirmation_required",
    "account_deleted",
    "unavailable",
]


class Error(BaseModel):
    code: ErrorCode
    retry_after_s: int | None = Field(
        default=None, description="export_too_soon: seconds until the next export"
    )


class ApiError(Exception):
    def __init__(self, status: int, code: ErrorCode) -> None:
        super().__init__(code)
        self.status = status
        self.code: ErrorCode = code


def error_responses(*statuses: int) -> dict[int | str, dict[str, object]]:
    """OpenAPI `responses=` entries, so the generated client knows the error shape."""
    return {status: {"model": Error} for status in statuses}


def install_error_handlers(app: FastAPI) -> None:
    async def api_error(_: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, ApiError)  # noqa: S101 - registered for ApiError only
        return JSONResponse({"code": exc.code}, status_code=exc.status)

    async def unavailable(_: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse({"code": "unavailable"}, status_code=503)

    async def invalid(_: Request, exc: Exception) -> JSONResponse:
        # Never echo what was sent (a diary note is private, PR-07): FastAPI's default puts
        # each error's `input` (and values in `ctx`) in the body.
        assert isinstance(exc, RequestValidationError)  # noqa: S101 - registered for it only
        detail = [{k: e[k] for k in ("type", "loc", "msg") if k in e} for e in exc.errors()]
        return JSONResponse({"detail": detail}, status_code=422)

    app.add_exception_handler(ApiError, api_error)
    app.add_exception_handler(RequestValidationError, invalid)

    async def gone(_: Request, _exc: Exception) -> JSONResponse:
        # A write raced the caller's own account deletion (ST-09).
        return JSONResponse({"code": "account_deleted"}, status_code=410)

    app.add_exception_handler(StorageUnavailable, unavailable)
    app.add_exception_handler(AccountGone, gone)
