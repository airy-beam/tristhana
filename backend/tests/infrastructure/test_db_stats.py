"""`history` on real Postgres: days + practices + the first date in one statement."""

import base64
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.application.practice_patch import PracticePatch
from tristhana.domain.accounts import IdentityKey, IdentityProvider, NewAccount
from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.practice import PracticeContext
from tristhana.infrastructure.crypto import FieldCipher
from tristhana.infrastructure.db.accounts import SqlAccountRepository
from tristhana.infrastructure.db.days import SqlDayLogRepository
from tristhana.infrastructure.db.practice import SqlPracticeRepository

pytestmark = pytest.mark.db

KEYS = "1:" + base64.b64encode(b"\x07" * 32).decode()


async def test_history_returns_days_practices_and_the_first_date(engine: AsyncEngine) -> None:
    account = await SqlAccountRepository(engine).create_with_identity(
        IdentityKey(IdentityProvider.TELEGRAM, "42"), NewAccount(display_name="A", locale="en")
    )
    days = SqlDayLogRepository(engine, FieldCipher(KEYS))
    await days.upsert(account.id, DayLog(date(2023, 5, 1), DayStatus.REST), None)
    await days.upsert(account.id, DayLog(date(2026, 10, 1), DayStatus.PRACTICED), None)
    await days.upsert(account.id, DayLog(date(2026, 10, 2), DayStatus.LADIES), None)
    await SqlPracticeRepository(engine).save(
        account.id, date(2026, 10, 1), PracticePatch.of(context=PracticeContext.MYSORE)
    )

    found = await days.history(account.id, date(2026, 1, 1), date(2026, 12, 31))
    empty = await days.history(account.id, date(2020, 1, 1), date(2020, 12, 31))

    assert found.first_date == date(2023, 5, 1)
    assert [(d.local_date, d.status) for d in found.days] == [
        (date(2026, 10, 1), DayStatus.PRACTICED),
        (date(2026, 10, 2), DayStatus.LADIES),  # unsealed for the owner
    ]
    assert found.days[0].practices[0].context is PracticeContext.MYSORE
    assert (empty.days, empty.first_date) == ([], date(2023, 5, 1))


async def test_history_without_any_logs(engine: AsyncEngine) -> None:
    account = await SqlAccountRepository(engine).create_with_identity(
        IdentityKey(IdentityProvider.TELEGRAM, "43"), NewAccount(display_name="B", locale="en")
    )

    found = await SqlDayLogRepository(engine, FieldCipher(KEYS)).history(
        account.id, date(2026, 1, 1), date(2026, 12, 31)
    )

    assert (found.days, found.first_date) == ([], None)
