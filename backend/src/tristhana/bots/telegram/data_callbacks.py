"""Callback data for "📦 My data" (ST-09), versioned `x1:`.

x1:o              open D (export / delete)
x1:e  x1:e:x      send the export (from D / from X, which is shown again)
x1:d              delete step 1: screen X
x1:y:<a8>:<m>     delete step 2: `a8` = the first 8 hex digits of the account id, `m` =
                  the unix minute X was rendered (base 36); valid for 10 minutes and only
                  for that account (stateless, ADR-0008)
"""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

PREFIX = "x1"
CONFIRM_MINUTES = 10
type Action = Literal["open", "export", "explain", "delete"]
_ACTIONS: dict[str, Action] = {"o": "open", "e": "export", "d": "explain", "y": "delete"}
_LETTER = {a: k for k, a in _ACTIONS.items()}
_HEX = frozenset("0123456789abcdef")
_B36 = frozenset("0123456789abcdefghijklmnopqrstuvwxyz")


@dataclass(frozen=True, slots=True)
class DataCallback:
    action: Action
    from_delete: bool = False  # export tapped on X: show X again afterwards
    account: str = ""  # delete: the 8-hex account prefix
    minute: int = 0  # delete: unix minute of rendering


def account_tag(account_id: UUID) -> str:
    return account_id.hex[:8]


def encode(cb: DataCallback) -> str:
    letter = _LETTER[cb.action]
    if cb.action == "delete":
        return f"{PREFIX}:{letter}:{cb.account}:{_base36(cb.minute)}"
    if cb.action == "export" and cb.from_delete:
        return f"{PREFIX}:{letter}:x"
    return f"{PREFIX}:{letter}"


def decode(data: str | None) -> DataCallback | None:
    """None for anything malformed (old or forged keyboards stay harmless)."""
    parts = (data or "").split(":")
    if len(parts) < 2 or parts[0] != PREFIX or parts[1] not in _ACTIONS:
        return None
    action = _ACTIONS[parts[1]]
    if action == "delete":
        if len(parts) != 4 or len(parts[2]) != 8 or not set(parts[2]) <= _HEX:
            return None
        if not parts[3] or len(parts[3]) > 8 or not set(parts[3]) <= _B36:
            return None
        return DataCallback(action, account=parts[2], minute=int(parts[3], 36))
    if action == "export" and parts[2:] == ["x"]:
        return DataCallback(action, from_delete=True)
    if len(parts) != 2:
        return None
    return DataCallback(action)


def _base36(n: int) -> str:
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while True:
        n, r = divmod(n, 36)
        out = digits[r] + out
        if n == 0:
            return out
