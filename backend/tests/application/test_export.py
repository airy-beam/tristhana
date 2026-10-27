"""Export and delete use cases (ST-09, ADR-0027) with fakes and a fixed clock: one export per
10 minutes (released when sending fails), the bot sends the file to the owner's own chat,
labels and README in the account's language, oversize is never sent, delete is idempotent,
and the policies only ever allow one's own account."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from tests.domain.test_practice import catalog
from tests.fakes import (
    FakeNotifier,
    FakePacker,
    FixedClock,
    InMemoryAccounts,
    InMemoryExport,
    cities,
)
from tristhana.application.export import (
    BotUnreachable,
    DeleteMyAccount,
    ExportFailed,
    ExportTooLarge,
    ExportTooSoon,
    SendMyExport,
)
from tristhana.application.labels import PracticeLabels
from tristhana.application.policies import Principal, can_delete_account, can_export
from tristhana.application.ports.export import Owned
from tristhana.application.ports.notifications import DeliveryResult, DeliveryStatus
from tristhana.application.ports.storage import StorageUnavailable
from tristhana.domain.accounts import (
    Account,
    ExternalProfile,
    IdentityKey,
    IdentityProvider,
    NewAccount,
)
from tristhana.domain.days import DayStatus
from tristhana.domain.export import MAX_BYTES, ExportDay, ExportEvent, ExportIdentity, MarkedBy
from tristhana.domain.notifications import DEFAULTS
from tristhana.domain.progression import EventKind, Position, ProgressionEvent, Track
from tristhana.infrastructure.i18n.fluent import FluentTranslator

NOW = datetime(2026, 10, 27, 20, 0, tzinfo=UTC)
KEY = IdentityKey(IdentityProvider.TELEGRAM, "4242")


class Setup:
    def __init__(self, locale: str = "en") -> None:
        self.clock = FixedClock(NOW)
        self.accounts = InMemoryAccounts(clock=self.clock)
        self.export = InMemoryExport(self.accounts)
        self.packer = FakePacker()
        self.notifier = FakeNotifier()
        t = FluentTranslator()
        self.use_case = SendMyExport(
            self.export,
            self.packer,
            self.notifier,
            t,
            PracticeLabels(t, catalog(), Track(catalog())),
            cities(),
            "cat-v1",
            self.clock,
        )
        self.locale = locale

    async def principal(self, zone: str | None = "Asia/Almaty") -> Principal:
        account = await self.accounts.create_with_identity(
            KEY,
            NewAccount("Asha", self.locale),  # type: ignore[arg-type]
        )
        account = replace(account, timezone=zone)
        self.accounts.accounts[account.id] = account
        return Principal(account)


async def test_sends_the_file_to_the_owners_own_chat() -> None:
    s = Setup()
    me = await s.principal()

    sent = await s.use_case.execute(me)

    ((recipient, file),) = s.notifier.exports
    assert recipient.telegram_id == "4242"
    assert recipient.locale == "en"
    assert file.name == "tristhana-export-2026-10-28.zip"  # 01:00 in Almaty
    assert file.local_date == date(2026, 10, 28)
    assert sent.file_name == file.name
    assert sent.bytes == len(file.content)
    assert sent.sent_at == NOW


async def test_second_export_within_ten_minutes_is_too_soon() -> None:
    s = Setup()
    me = await s.principal()
    await s.use_case.execute(me)
    s.clock.instant = NOW + timedelta(minutes=7)

    with pytest.raises(ExportTooSoon) as e:
        await s.use_case.execute(me)

    assert e.value.wait == timedelta(minutes=3)
    assert len(s.notifier.exports) == 1


async def test_after_ten_minutes_it_goes_again() -> None:
    s = Setup()
    me = await s.principal()
    await s.use_case.execute(me)
    s.clock.instant = NOW + timedelta(minutes=10)

    await s.use_case.execute(me)

    assert len(s.notifier.exports) == 2


async def test_success_keeps_the_claim() -> None:
    s = Setup()
    me = await s.principal()

    await s.use_case.execute(me)

    assert s.export.claimed[me.account.id] == NOW
    assert s.export.released == []


async def test_blocked_bot_releases_and_says_unreachable() -> None:
    s = Setup()
    me = await s.principal()
    s.notifier.export_outcomes.append(DeliveryResult(DeliveryStatus.BLOCKED))

    with pytest.raises(BotUnreachable):
        await s.use_case.execute(me)

    assert s.export.released == [me.account.id]
    await s.use_case.execute(me)  # free again at once


@pytest.mark.parametrize("status", [DeliveryStatus.FAILED, DeliveryStatus.RETRY_AFTER])
async def test_failed_upload_releases(status: DeliveryStatus) -> None:
    s = Setup()
    me = await s.principal()
    s.notifier.export_outcomes.append(DeliveryResult(status))

    with pytest.raises(ExportFailed):
        await s.use_case.execute(me)

    assert s.export.released == [me.account.id]


async def test_storage_down_after_the_claim_releases() -> None:
    s = Setup()
    me = await s.principal()

    async def down(*_: object) -> Owned | None:
        raise StorageUnavailable

    s.export.snapshot = down  # type: ignore[method-assign]

    with pytest.raises(StorageUnavailable):
        await s.use_case.execute(me)

    assert s.export.released == [me.account.id]


async def test_too_large_is_never_sent() -> None:
    s = Setup()
    me = await s.principal()
    s.packer.size = MAX_BYTES + 1

    with pytest.raises(ExportTooLarge):
        await s.use_case.execute(me)

    assert s.notifier.exports == []


async def test_no_telegram_identity_is_unreachable() -> None:
    s = Setup()
    me = await s.principal()
    s.accounts.identities.clear()

    with pytest.raises(BotUnreachable):
        await s.use_case.execute(me)

    assert s.notifier.exports == []


async def test_labels_and_readme_in_the_accounts_language() -> None:
    s = Setup("ru")
    me = await s.principal()
    event = ProgressionEvent(
        1,
        EventKind.GIVEN,
        NOW.date(),
        Position("primary", "navasana"),
        Position("primary", "bhujapidasana"),
    )
    s.export.owned = Owned(
        me.account,
        (ExportIdentity("telegram", "4242", NOW),),
        DEFAULTS,
        (ExportDay(NOW.date(), DayStatus.SKIPPED, None),),
        (),
        (),
        (),
        (),
        None,
        (ExportEvent(event, MarkedBy.SELF, NOW),),
        (),
    )

    await s.use_case.execute(me)
    data, tables, readme = s.packer.packed[0]

    assert data["days"][0]["status_label"] == "🌱 Без практики"  # type: ignore[index]
    (ev,) = data["progression_events"]  # type: ignore[misc]
    assert ev["kind_label"] == "Новая асана"
    assert ev["from_name"] == "Навасана"
    assert tables["days"][1][2] == "🌱 Без практики"
    assert "Дни отдыха — часть практики." in readme
    assert "Помни об этом, если будешь делиться файлом." in readme  # noqa: RUF001 - Q56
    assert "📍 Майсур" in readme
    assert "no_practice: 🌱 Без практики" in readme
    assert "primary: Первая серия (Primary)" in readme
    assert "skipped" not in readme


async def test_readme_in_english_names_the_moon_city() -> None:
    s = Setup()
    me = await s.principal()

    await s.use_case.execute(me)
    data, _, readme = s.packer.packed[0]

    assert "📍 Mysuru" in readme
    assert "Rest days are part of the practice." in readme
    assert "Keep this in mind before sharing the file." in readme  # Q56
    assert data["account"]["moon_city"] == {"slug": "mysuru", "default": True}  # type: ignore[index]
    assert data["catalog_version"] == "cat-v1"


async def test_reminders_window_is_sixty_days() -> None:
    s = Setup()
    me = await s.principal()
    seen: list[date] = []
    original = s.export.snapshot

    async def spy(account_id: object, defaults: object, reminders_from: date) -> Owned | None:
        seen.append(reminders_from)
        return await original(account_id, defaults, reminders_from)  # type: ignore[arg-type]

    s.export.snapshot = spy  # type: ignore[method-assign]

    await s.use_case.execute(me)

    assert seen == [date(2026, 10, 28) - timedelta(days=60)]


async def test_delete_twice_is_fine() -> None:
    accounts = InMemoryAccounts()
    account = await accounts.create_with_identity(KEY, NewAccount("Asha", "en"))
    delete = DeleteMyAccount(accounts)

    await delete.execute(Principal(account))
    await delete.execute(Principal(account))

    assert account.id not in accounts.accounts
    assert await accounts.find_by_identity(KEY) is None


async def test_after_delete_first_contact_creates_a_fresh_account() -> None:
    from tristhana.application.accounts import EnsureAccount

    accounts = InMemoryAccounts()
    ensure = EnsureAccount(accounts, FixedClock(NOW))
    profile = ExternalProfile(KEY, "Asha", "en")
    old = await ensure.execute(profile)
    await DeleteMyAccount(accounts).execute(Principal(old))

    new = await ensure.execute(profile)

    assert new.id != old.id


def test_policies_only_allow_ones_own_account() -> None:
    me = Account(uuid4(), "A", "en", None, NOW)
    other = Account(uuid4(), "B", "en", None, NOW)

    assert can_export(me, me)
    assert not can_export(me, other)
    assert can_delete_account(me, me)
    assert not can_delete_account(me, other)


async def test_an_unexpected_error_after_the_claim_frees_the_slot() -> None:
    s = Setup()
    me = await s.principal()

    async def broken(*_: object) -> bytes:
        raise RuntimeError("a bug in packing")

    s.packer.pack = broken  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        await s.use_case.execute(me)

    assert s.export.released == [me.account.id]


async def test_too_large_keeps_the_slot() -> None:
    s = Setup()
    me = await s.principal()
    s.packer.size = MAX_BYTES + 1

    with pytest.raises(ExportTooLarge):
        await s.use_case.execute(me)

    assert s.export.released == []
