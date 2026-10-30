"""Export my data and delete my account (ST-09, ADR-0027). The bot and the API share these
use cases: the export is always sent by the bot to the person's own chat as a document."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from tristhana.application.labels import PracticeLabels
from tristhana.application.policies import Principal, can_delete_account, can_export
from tristhana.application.ports.accounts import AccountRepository
from tristhana.application.ports.export import ExportPacker, ExportRepository, Owned
from tristhana.application.ports.i18n import Translator
from tristhana.application.ports.notifications import (
    DeliveryStatus,
    ExportFile,
    Notifier,
    Recipient,
)
from tristhana.application.ports.storage import Clock, StorageUnavailable
from tristhana.domain.accounts import IdentityProvider
from tristhana.domain.days import DayStatus
from tristhana.domain.export import (
    EXPORT_EVERY,
    MAX_BYTES,
    REMINDER_DAYS,
    ExportLabels,
    Snapshot,
    check_rate,
    export_file_name,
    status_code,
    to_json,
    to_tables,
)
from tristhana.domain.locale import Locale
from tristhana.domain.moon import Cities
from tristhana.domain.notifications import defaults_for
from tristhana.domain.practice import PracticeContext
from tristhana.domain.progression import EventKind

log = logging.getLogger(__name__)

# The README, one Fluent message per paragraph (account's language).
README_KEYS = (
    "export-readme-title",
    "export-readme-files",
    "export-readme-days",
    "export-readme-moon-logged",
    "export-readme-moon-city",
    "export-readme-ladies",
    "export-readme-statuses",
    "export-readme-length",
    "export-readme-halves",
    "export-readme-contexts",
    "export-readme-series",
    "export-readme-day-off",
    "export-readme-hide-ladies",
    "export-readme-standing",
    "export-readme-marked-by",
    "export-readme-unreadable",
)
_README_STATUSES = (
    DayStatus.PRACTICED,
    DayStatus.REST,
    DayStatus.MOON,
    DayStatus.LADIES,
    DayStatus.SICK,
    DayStatus.TRAVEL,
    DayStatus.SKIPPED,
)
_KIND_KEYS = {
    EventKind.START: "export-kind-start",
    EventKind.GIVEN: "export-kind-given",
    EventKind.CHANGED: "export-kind-changed",
    EventKind.ITEM_GIVEN: "export-kind-item-given",
    EventKind.ITEM_REMOVED: "export-kind-item-removed",
}


class NotAllowed(Exception):
    """A policy refused (only ever one's own account today)."""


class ExportTooSoon(Exception):
    def __init__(self, wait: timedelta) -> None:
        super().__init__(f"next export in {wait}")
        self.wait = wait


class BotUnreachable(Exception):
    """The person blocked the bot or never started it: no chat to send the file to."""


class ExportFailed(Exception):
    """Telegram refused or the upload failed: the slot is released, try again."""


class ExportTooLarge(Exception):
    """Over the upload limit: nothing was sent."""


@dataclass(frozen=True, slots=True)
class ExportSent:
    file_name: str
    bytes: int
    sent_at: datetime


class SendMyExport:
    """claim → snapshot (one transaction) → JSON + CSV + README → ZIP → `sendDocument`."""

    def __init__(
        self,
        export: ExportRepository,
        packer: ExportPacker,
        notifier: Notifier,
        translator: Translator,
        labels: PracticeLabels,
        cities: Cities,
        catalog_version: str,
        clock: Clock,
    ) -> None:
        self._export = export
        self._packer = packer
        self._notifier = notifier
        self._t = translator
        self._labels = labels
        self._cities = cities
        self._catalog_version = catalog_version
        self._clock = clock

    async def execute(
        self, principal: Principal, claimed: Callable[[], Awaitable[None]] | None = None
    ) -> ExportSent:
        """Raises `ExportTooSoon`, `BotUnreachable`, `ExportFailed`, `ExportTooLarge`,
        `StorageUnavailable`. `claimed` runs once the slot is taken, before the slow part
        (the bot answers the tap with "Preparing…" there: a tap is answered only once)."""
        account = principal.account
        if not can_export(account, account):
            raise NotAllowed
        now = self._clock.now()
        earlier = await self._export.claim(account.id, now, now - EXPORT_EVERY)
        if earlier is not None:
            # A claim that waited on another one's row lock loses with the stale earlier
            # instant: someone claimed just now, so the whole window applies.
            raise ExportTooSoon(check_rate(earlier, now) or EXPORT_EVERY)
        try:
            if claimed is not None:
                await claimed()
            return await self._send(principal, now)
        except ExportTooLarge:
            raise  # trying again won't help: keep the slot
        except BaseException:  # unreachable, failed upload, storage, or a bug: free the slot
            await self._release(account.id)
            raise

    async def _send(self, principal: Principal, now: datetime) -> ExportSent:
        account = principal.account
        zone = account.timezone
        local = now.astimezone(ZoneInfo(zone) if zone else UTC).date()
        owned = await self._export.snapshot(
            account.id,
            defaults_for(account.day_off.days),
            local - timedelta(days=REMINDER_DAYS),
        )
        if owned is None:
            raise StorageUnavailable  # deleted meanwhile: nothing to send
        telegram = next(
            (i.id for i in owned.identities if i.provider == IdentityProvider.TELEGRAM), None
        )
        if telegram is None:
            raise BotUnreachable
        locale = owned.account.locale
        snapshot = self._snapshot(owned, now)
        labels = self.labels(locale)
        readme = self.readme(locale, snapshot)
        content = await self._packer.pack(
            to_json(snapshot, labels), to_tables(snapshot, labels), readme
        )
        if len(content) > MAX_BYTES:
            log.warning("export too large: %d bytes", len(content))
            raise ExportTooLarge
        name = export_file_name(local)
        result = await self._notifier.send_export(
            Recipient(telegram, locale), ExportFile(name, content, local)
        )
        match result.status:
            case DeliveryStatus.SENT:
                return ExportSent(name, len(content), now)
            case DeliveryStatus.BLOCKED:
                raise BotUnreachable
            case _:
                raise ExportFailed

    def _snapshot(self, owned: Owned, now: datetime) -> Snapshot:
        a = owned.account
        city = self._cities.get(a.moon_location) or self._cities.default
        return Snapshot(
            account=a,
            identities=owned.identities,
            settings=owned.settings,
            moon_city=city.slug,
            moon_city_default=a.moon_location is None or self._cities.get(a.moon_location) is None,
            catalog_version=self._catalog_version,
            days=owned.days,
            periods=owned.periods,
            practices=owned.practices,
            check_ins=owned.check_ins,
            notes=owned.notes,
            progression=owned.progression,
            events=owned.events,
            reminders=owned.reminders,
            exported_at=now,
            milestones=owned.milestones,
        )

    def labels(self, locale: Locale) -> ExportLabels:
        t, pl = self._t, self._labels

        def status(code: str) -> str:
            return t.t(locale, "status-skipped" if code == "no_practice" else f"status-{code}")

        def kind(k: EventKind, item: str) -> str:
            return t.t(locale, _KIND_KEYS[k], item=item)

        return ExportLabels(
            status=status,
            position=lambda p: pl.position(locale, p),
            stop=lambda series, key: pl.stop(locale, series, key),
            item=lambda key: pl.item(locale, key),
            kind=kind,
            length=lambda length: pl.length(locale, length),
            unreadable_rest=t.t(locale, "export-rest-unreadable"),
        )

    def readme(self, locale: Locale, snapshot: Snapshot) -> str:
        t = self._t
        city = self._cities.get(snapshot.moon_city) or self._cities.default
        args: dict[str, str] = {
            "city": city.name(locale),
            "statuses": "\n".join(
                f"  {status_code(s)}: {t.t(locale, f'status-{s.value}')}" for s in _README_STATUSES
            ),
            "contexts": "\n".join(
                f"  {c.value}: {t.t(locale, f'context-{c.value}')}" for c in PracticeContext
            ),
            "series": "\n".join(
                f"  {s.slug}: {t.t(locale, 'export-readme-series-name', n=s.number)}"
                for s in self._labels.all_series()
            ),
        }
        return "\n\n".join(t.t(locale, key, **args) for key in README_KEYS) + "\n"

    async def _release(self, account_id: UUID) -> None:
        try:
            await self._export.release(account_id)
        except StorageUnavailable:
            log.warning("export claim not released (storage down)")  # frees in 10 min anyway


class DeleteMyAccount:
    """One statement; every per-account row cascades (ADR-0027). Idempotent."""

    def __init__(self, accounts: AccountRepository) -> None:
        self._accounts = accounts

    async def execute(self, principal: Principal) -> None:
        account = principal.account
        if not can_delete_account(account, account):
            raise NotAllowed
        if await self._accounts.delete(account.id):
            # The only trace kept: the re-delete list after a backup restore (30 days of logs).
            # WARNING, so it survives any LOG_LEVEL: the restore runbook reads these lines.
            log.warning("account deleted %s", account.id)
