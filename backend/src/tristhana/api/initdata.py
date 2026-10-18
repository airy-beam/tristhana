"""Telegram Mini App initData: verify and sign (ADR-0015). Standard library only: importing
aiogram here would add ~3 s to the API's cold start.

https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from urllib.parse import parse_qsl, urlencode

MAX_AGE = timedelta(hours=24)
MAX_CLOCK_SKEW = timedelta(seconds=60)

type InitDataError = Literal["auth_invalid", "auth_expired"]


class InvalidInitData(Exception):
    def __init__(self, code: InitDataError) -> None:
        super().__init__(code)
        self.code: InitDataError = code


@dataclass(frozen=True, slots=True)
class TelegramUser:
    id: int
    first_name: str | None
    language_code: str | None


def verify(raw: str, bot_token: str, now: datetime) -> TelegramUser:
    """The signed user, or `InvalidInitData`. Never log `raw`: it is a bearer credential."""
    try:
        fields = dict(parse_qsl(raw, keep_blank_values=True, strict_parsing=True))
    except ValueError:
        raise InvalidInitData("auth_invalid") from None
    given = fields.pop("hash", "")
    if not hmac.compare_digest(given.encode(), _signature(fields, bot_token).encode()):
        raise InvalidInitData("auth_invalid")
    try:
        signed_at = datetime.fromtimestamp(int(fields["auth_date"]), now.tzinfo)
        user = json.loads(fields["user"])
        user_id = int(user["id"])
    except (KeyError, ValueError, TypeError, OverflowError, OSError):  # bad auth_date too
        raise InvalidInitData("auth_invalid") from None
    if not -MAX_CLOCK_SKEW <= now - signed_at <= MAX_AGE:
        raise InvalidInitData("auth_expired")
    if user.get("is_bot"):
        raise InvalidInitData("auth_invalid")
    first_name, language_code = user.get("first_name"), user.get("language_code")
    return TelegramUser(
        id=user_id,
        first_name=first_name if isinstance(first_name, str) else None,
        language_code=language_code if isinstance(language_code, str) else None,
    )


def sign(fields: dict[str, str], bot_token: str) -> str:
    """Raw initData for `fields`, signed like Telegram does (dev mock and tests)."""
    return urlencode(fields | {"hash": _signature(fields, bot_token)})


def _signature(fields: dict[str, str], bot_token: str) -> str:
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    return hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
