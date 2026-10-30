"""MD-04 + ID-06 on Postgres (ADR-0029): `account.home_city`, two calendars in one
statement, migration 0018."""

import asyncio
from datetime import date

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.fakes import cities
from tristhana.domain.accounts import (
    NOT_LISTED,
    Account,
    ExternalProfile,
    IdentityKey,
    IdentityProvider,
    NewAccount,
    ProfilePatch,
    resolve_profile,
)
from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.infrastructure.db import migrate
from tristhana.infrastructure.db.accounts import SqlAccountRepository
from tristhana.infrastructure.db.moon import SqlMoonCalendarRepository

KEY = IdentityKey(IdentityProvider.TELEGRAM, "42")
TG = ExternalProfile(KEY, "A", "en")


def test_0018_follows_0017_and_is_the_head() -> None:
    script = ScriptDirectory.from_config(migrate.alembic_config("postgresql://unused"))
    revision = script.get_revision("0018")
    assert revision is not None
    assert revision.down_revision == "0017"
    assert script.get_current_head() == "0018"


async def _account(engine: AsyncEngine, zone: str | None = None) -> Account:
    repo = SqlAccountRepository(engine)
    me = await repo.create_with_identity(KEY, NewAccount(display_name="A", locale="en"))
    return await repo.set_timezone_if_unset(me.id, zone) if zone else me


async def _patch(engine: AsyncEngine, me: Account, patch: ProfilePatch) -> Account:
    change = resolve_profile(me, patch, TG, cities())
    return await SqlAccountRepository(engine).update_settings(me.id, change)


@pytest.mark.db
async def test_a_city_and_its_zone_in_one_write_and_back(engine: AsyncEngine) -> None:
    me = await _account(engine)
    assert (me.home_city, me.home_city_chosen) == (None, False)

    astana = await _patch(engine, me, ProfilePatch(home_city="astana"))
    away = await _patch(engine, astana, ProfilePatch(timezone="Asia/Bangkok"))
    found = await SqlAccountRepository(engine).find_by_identity(KEY)

    assert (astana.home_city, astana.timezone) == ("astana", "Asia/Almaty")
    assert (away.home_city, away.timezone) == (NOT_LISTED, "Asia/Bangkok")
    assert found == away


@pytest.mark.db
@pytest.mark.parametrize(
    ("home", "zone"),
    [("Astana", "Asia/Almaty"), ("astana", None), ("a" * 25, "Asia/Almaty")],
)
async def test_the_checks(engine: AsyncEngine, home: str, zone: str | None) -> None:
    me = await _account(engine)

    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE tristhana.account SET home_city = :home, timezone = :zone"
                    " WHERE id = :id"
                ),
                {"home": home, "zone": zone, "id": me.id},
            )


@pytest.mark.db
async def test_not_listed_needs_no_zone(engine: AsyncEngine) -> None:
    me = await _account(engine)

    saved = await _patch(engine, me, ProfilePatch(home_city=None))

    assert (saved.home_city, saved.timezone) == (NOT_LISTED, None)


@pytest.mark.db
async def test_two_calendars_in_one_statement(engine: AsyncEngine) -> None:
    repo = SqlMoonCalendarRepository(engine)
    await repo.replace_year("mysuru", 2026, [MoonDay(date(2026, 10, 26), MoonDayKind.PURNIMA)], "t")
    await repo.replace_year(
        "almaty",
        2026,
        [
            MoonDay(date(2026, 10, 25), MoonDayKind.PURNIMA),
            MoonDay(date(2026, 12, 24), MoonDayKind.PURNIMA),
        ],
        "t",
    )

    both = await repo.days_for(
        ["mysuru", "almaty", "mysuru"], date(2026, 10, 1), date(2026, 11, 30)
    )
    empty = await repo.days_for(["kazan"], date(2026, 10, 1), date(2026, 11, 30))

    assert both == {
        "mysuru": [MoonDay(date(2026, 10, 26), MoonDayKind.PURNIMA)],
        "almaty": [MoonDay(date(2026, 10, 25), MoonDayKind.PURNIMA)],
    }
    assert empty == {"kazan": []}


@pytest.mark.db
async def test_0018_down_and_up(migrated_url: str, engine: AsyncEngine) -> None:
    has_column = (
        "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'tristhana'"
        " AND table_name = 'account' AND column_name = 'home_city'"
    )
    await asyncio.to_thread(migrate.downgrade, migrated_url, "0017")
    async with engine.connect() as conn:
        assert (await conn.execute(text(has_column))).scalar_one() == 0
    await asyncio.to_thread(migrate.upgrade, migrated_url)
    async with engine.connect() as conn:
        assert (await conn.execute(text(has_column))).scalar_one() == 1
    await asyncio.to_thread(migrate.check, migrated_url)
