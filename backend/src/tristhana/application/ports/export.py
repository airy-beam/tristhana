from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from tristhana.domain.accounts import Account
from tristhana.domain.export import (
    ExportCheckIn,
    ExportDay,
    ExportEvent,
    ExportIdentity,
    ExportMilestone,
    ExportNote,
    ExportPeriod,
    ExportPractice,
    ExportReminder,
)
from tristhana.domain.notifications import NotificationSettings
from tristhana.domain.progression import Progression


class AccountGone(Exception):
    """The account was deleted while this request ran (ST-09): a write hit the missing
    parent row. The API answers 410; the bot stays silent; the tick skips it."""


@dataclass(frozen=True, slots=True)
class Owned:
    """Every stored row of one account, seals opened, read in one transaction."""

    account: Account
    identities: tuple[ExportIdentity, ...]
    settings: NotificationSettings  # effective (missing columns = `defaults`)
    days: tuple[ExportDay, ...]
    periods: tuple[ExportPeriod, ...]
    practices: tuple[ExportPractice, ...]
    check_ins: tuple[ExportCheckIn, ...]
    notes: tuple[ExportNote, ...]
    progression: Progression | None
    events: tuple[ExportEvent, ...]
    reminders: tuple[ExportReminder, ...]
    milestones: tuple[ExportMilestone, ...] = ()  # GM-01 part 2


class ExportRepository(Protocol):
    async def snapshot(
        self, account_id: UUID, defaults: NotificationSettings, reminders_from: date
    ) -> Owned | None:
        """One read-only REPEATABLE READ transaction; None = the account is gone."""
        ...

    async def claim(self, account_id: UUID, now: datetime, before: datetime) -> datetime | None:
        """One statement: claims the export slot if the last claim is older than `before`
        (or none). None = claimed; else the earlier claim's instant."""
        ...

    async def release(self, account_id: UUID) -> None:
        """Frees the slot (sending failed: the person may try again at once)."""
        ...


class ExportPacker(Protocol):
    async def pack(
        self, data: dict[str, object], tables: dict[str, list[list[str]]], readme: str
    ) -> bytes:
        """The ZIP: data.json, one CSV per table (UTF-8 with BOM), README.txt."""
        ...
