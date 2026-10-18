"""Authorization lives here, never in handlers or the UI (CLAUDE.md).

A `Principal` is the authenticated caller. Today every operation acts on the caller's own
account; reads across accounts (teachers, ST-06) get a named policy function here.
"""

from dataclasses import dataclass

from tristhana.domain.accounts import Account


@dataclass(frozen=True, slots=True)
class Principal:
    account: Account
