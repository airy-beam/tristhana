"""API errors as `{"code": ...}` bodies: stable codes the Mini App can branch on."""

from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

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
    "timezone_unknown",
    "unknown_location",
    "invalid_settings",
    "invalid_day_off",
    "unavailable",
]


class Error(BaseModel):
    code: ErrorCode


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

    app.add_exception_handler(ApiError, api_error)
    app.add_exception_handler(StorageUnavailable, unavailable)
