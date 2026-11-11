# ruff: noqa: RUF001
"""SC-02 copy (spec §2 table, §10): every new bot key in both languages, the drafted rows
exactly, the class-type and moon-policy selects (Q117, Q128, Chanting), RU gender-neutral, and
the Mini App's keys in `app.ftl` for both languages."""

import re
from pathlib import Path

import pytest

from tristhana.domain.locale import Locale
from tristhana.infrastructure.i18n.fluent import FluentTranslator, message_ids

ROOT = Path(__file__).resolve().parents[3]
APP_FTL = ROOT / "miniapp/src/locales/{}/app.ftl"
LOCALES: tuple[Locale, ...] = ("en", "ru")
BOT_KEYS = (
    "class-type",
    "class-led-hint",
    "schedule-title",
    "schedule-zone",
    "schedule-your-time",
    "schedule-moon-day",
    "schedule-reason",
    "schedule-swap",
    "schedule-swapped-to",
    "schedule-moved",
    "schedule-substitute",
    "schedule-day-off",
    "schedule-empty",
    "shala-moon-policy",
    "shala-day-off-line",
    "shala-day-off-adopt",
    "class-cancel-ask",
    "schedule-open",
    "class-cancel",
    "class-restore",
    "class-hold",
    "class-cancel-pick",
    "class-gone",
    "class-caps",
    "class-invalid",
)
APP_KEYS = (
    "class-type",
    "class-led-hint",
    "shala-moon-policy",
    "shala-moon-policy-note",
    "shala-day-off-adopt",
    "schedule-moon-day",
    "schedule-day-off",
    "schedule-empty",
    "schedule-your-time",
    "class-form-type",
    "class-form-title",
    "class-form-teacher",
    "class-form-start",
    "class-form-until",
    "class-form-length",
    "class-form-days",
    "class-form-every",
    "class-form-from",
    "class-form-end",
    "class-form-online",
    "class-form-zone",
    "class-form-applies",
)
APP_PREFIXES = ("closure-", "swap-", "occurrence-")
COPY: list[tuple[str, dict[str, str | int], str, str]] = [
    ("class-led-hint", {}, "Often Friday or Sunday", "Часто в пятницу или воскресенье"),
    (
        "schedule-title",
        {"shala": "S", "range": "9–15 Nov"},
        "🗓 S: schedule, 9–15 Nov",
        "🗓 S: расписание, 9–15 Nov",
    ),
    ("schedule-zone", {"zone": "Almaty (UTC+5)"}, "Times: Almaty (UTC+5)", "Время: Almaty (UTC+5)"),
    ("schedule-your-time", {"time": "16:30"}, "(16:30 your time)", "(16:30 по твоему времени)"),
    ("schedule-moon-day", {}, "🌙 Moon day", "🌙 Лунный день"),
    ("schedule-swap", {"day": "Fri 13 Nov"}, "🔁 Instead of Fri 13 Nov", "🔁 Вместо Fri 13 Nov"),
    (
        "schedule-swapped-to",
        {"class": "06:00 Mysore", "day": "Sat 14 Nov", "reason": "moon day"},
        "🔁 06:00 Mysore: moved to Sat 14 Nov (moon day)",
        "🔁 06:00 Mysore: перенесено на Sat 14 Nov (moon day)",
    ),
    (
        "schedule-moved",
        {"day": "Mon 9 Nov", "time": "06:00"},
        "↪ moved from Mon 9 Nov 06:00",
        "↪ перенесено с Mon 9 Nov 06:00",
    ),
    ("schedule-substitute", {"name": "Dana"}, "Dana (substitute)", "Dana (замена)"),
    ("schedule-day-off", {}, "😌 Shala day off", "😌 Выходной в шале"),
    ("schedule-empty", {}, "No classes these days.", "В эти дни занятий нет."),
    ("shala-day-off-line", {"days": "Saturday"}, "😌 Day off: Saturday", "😌 Выходной: Saturday"),
    (
        "shala-day-off-adopt",
        {"days": "Saturday"},
        "😌 Make Saturday my day off too",
        "😌 Мой выходной тоже: Saturday",
    ),
    (
        "class-cancel-ask",
        {"class": "Mysore", "day": "Tue 10 Nov"},
        "Cancel Mysore on Tue 10 Nov? It shows on the schedule. No one gets a message.",
        "Отменить Mysore Tue 10 Nov? Отмена будет видна в расписании. Сообщений никто не получит.",
    ),
]
TYPES = {
    "conference": ("Conference", "Конференция"),
    "pranayama": ("Pranayama", "Пранаяма"),
    "chanting": ("Chanting", "Чантинг"),
    "workshop": ("Workshop", "Семинар"),
}
POLICIES = {
    "closed": ("🌙 Moon days: the shala is closed", "🌙 В лунные дни шала закрыта"),
    "pranayama": (
        "🌙 Moon days: pranayama, chanting and talks only",
        "🌙 В лунные дни только пранаяма, чантинг и конференции",
    ),
    "open": ("🌙 Moon days: classes as usual", "🌙 В лунные дни занятия как обычно"),
}
REASONS = {
    "moon": ("moon day", "лунный день"),
    "closure": ("shala closed", "шала закрыта"),
    "cancelled": ("cancelled", "отменено"),
}


def _flat(text: str) -> str:
    return " ".join(text.replace("⁨", "").replace("⁩", "").split())


@pytest.mark.parametrize("locale", LOCALES)
def test_every_bot_key_exists(locale: Locale) -> None:
    assert set(BOT_KEYS) - message_ids(locale) == set()


@pytest.mark.parametrize(("key", "args", "en", "ru"), COPY)
def test_the_drafted_rows(key: str, args: dict[str, str | int], en: str, ru: str) -> None:
    t = FluentTranslator()

    assert (_flat(t.t("en", key, **args)), _flat(t.t("ru", key, **args))) == (en, ru)


@pytest.mark.parametrize(("type", "labels"), list(TYPES.items()))
def test_the_class_type_select(type: str, labels: tuple[str, str]) -> None:
    t = FluentTranslator()

    assert (t.t("en", "class-type", type=type), t.t("ru", "class-type", type=type)) == labels


@pytest.mark.parametrize(("policy", "labels"), list(POLICIES.items()))
def test_the_moon_policy_select(policy: str, labels: tuple[str, str]) -> None:
    t = FluentTranslator()

    assert (
        _flat(t.t("en", "shala-moon-policy", p=policy)),
        _flat(t.t("ru", "shala-moon-policy", p=policy)),
    ) == labels


@pytest.mark.parametrize(("reason", "labels"), list(REASONS.items()))
def test_the_reasons(reason: str, labels: tuple[str, str]) -> None:
    t = FluentTranslator()

    assert (
        t.t("en", "schedule-reason", reason=reason),
        t.t("ru", "schedule-reason", reason=reason),
    ) == labels


def _app_ids(locale: Locale) -> set[str]:
    text = APP_FTL.with_name("app.ftl").parent.parent.joinpath(locale, "app.ftl").read_text()
    return set(re.findall(r"^([a-z][a-z0-9-]*)\s*=", text, flags=re.MULTILINE))


@pytest.mark.parametrize("locale", LOCALES)
def test_every_mini_app_key_exists(locale: Locale) -> None:
    ids = _app_ids(locale)

    assert set(APP_KEYS) - ids == set()
    for prefix in APP_PREFIXES:
        assert any(i.startswith(prefix) for i in ids), prefix


def test_the_mini_app_keys_are_in_parity() -> None:
    sc02 = ("class-", "schedule-", "closure-", "swap-", "occurrence-", "shala-moon-", "shala-day-")
    en = {i for i in _app_ids("en") if i.startswith(sc02)}
    ru = {i for i in _app_ids("ru") if i.startswith(sc02)}

    assert en == ru
    assert en


def test_the_russian_copy_is_gender_neutral() -> None:
    """«отменено», «замена»: no gendered past tense about a teacher or a student."""
    t = FluentTranslator()
    words = [_flat(t.t("ru", key, **args)) for key, args, _, _ in COPY] + [
        t.t("ru", "schedule-reason", reason=r) for r in REASONS
    ]

    for text in words:
        for gendered in ("отменил ", "отменила", "заменил ", "заменила", "перенёс ", "перенесла"):
            assert gendered not in text, text
