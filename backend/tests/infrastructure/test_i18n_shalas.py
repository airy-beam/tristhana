"""SC-01 copy (spec §2): every new key in both languages, the drafted rows exactly, the role
select (Q104), and the glossary split: «Преподаватель» is the shala role, «учитель» the
personal teacher. No copy implies SYC authorisation."""

from pathlib import Path

import pytest

from tristhana.domain.locale import Locale
from tristhana.infrastructure.i18n.fluent import FluentTranslator, message_ids

ROOT = Path(__file__).resolve().parents[3]
BOT_FTL = str(ROOT / "backend/src/tristhana/infrastructure/i18n/locales/{}/bot.ftl")
LOCALES: tuple[Locale, ...] = ("en", "ru")
KEYS = (
    "shala-join-ask",
    "shala-join-consent",
    "shala-know-them",
    "shala-staff-ask",
    "shala-staff-consent",
    "shala-staff-joined",
    "shala-staff-link-hint",
    "shala-role",
    "moon-source-shala",
    "moon-follow-shala",
    "shala-moon-shared",
    "settings-moon-line-shala",
    "shala-invalid",
    "shala-already",
    "shala-already-staff",
    "shala-full",
    "shala-joined",
    "shala-leave",
    "shala-leave-ask",
    "shala-leave-yes",
    "shala-remove-ask",
    "shala-students",
    "shala-staff-title",
    "shala-invite-students",
    "shala-invite-staff",
    "shala-create",
    "shala-online",
    "shala-time",
    "shala-delete-ask",
    "shala-name-invalid",
    "shala-caps",
    "export-readme-shalas",
)
COPY: list[tuple[str, dict[str, str | int], str, str]] = [
    (
        "shala-join-ask",
        {"shala": "S", "city": "Almaty"},
        "🏛 Join S (📍 Almaty)?",
        "🏛 Присоединиться к шале S (📍 Almaty)?",
    ),
    (
        "shala-staff-ask",
        {"name": "Anna", "shala": "S", "role": "Teacher"},
        "🏛 Anna invites you to S as Teacher.",
        "🏛 Anna приглашает тебя в шалу S. Роль: Teacher.",
    ),
    (
        "shala-staff-joined",
        {"name": "Boris", "shala": "S", "role": "Assistant"},
        "🏛 Boris joined S as Assistant.",
        "🏛 Boris теперь в шале S. Роль: Assistant.",
    ),
    (
        "moon-source-shala",
        {"shala": "S"},
        "🏛 Same as your shala, S. You can choose another city.",
        "🏛 Как в шале: S. Можно выбрать другой город.",
    ),
    ("moon-follow-shala", {"shala": "S"}, "🏛 Follow my shala (S)", "🏛 Как в шале (S)"),
    (
        "settings-moon-line-shala",
        {"city": "Almaty", "shala": "S"},
        "🌙 Moon days: 📍 Almaty (as S)",
        "🌙 Лунные дни: 📍 Almaty (как в шале: S)",
    ),
]
ROLES = {
    "owner": ("Owner", "Владелец"),
    "admin": ("Manager", "Управляющий"),
    "teacher": ("Teacher", "Преподаватель"),
    "assistant": ("Assistant", "Ассистент"),
    "office": ("Front desk", "Администратор"),
}


def _flat(text: str) -> str:
    return " ".join(text.replace("⁨", "").replace("⁩", "").split())


@pytest.mark.parametrize("locale", LOCALES)
def test_every_key_exists(locale: Locale) -> None:
    missing = set(KEYS) - message_ids(locale)

    assert missing == set()


@pytest.mark.parametrize(("key", "args", "en", "ru"), COPY)
def test_the_drafted_rows(key: str, args: dict[str, str | int], en: str, ru: str) -> None:
    t = FluentTranslator()

    assert (_flat(t.t("en", key, **args)), _flat(t.t("ru", key, **args))) == (en, ru)


@pytest.mark.parametrize(("role", "labels"), list(ROLES.items()))
def test_the_role_select(role: str, labels: tuple[str, str]) -> None:
    t = FluentTranslator()

    assert (t.t("en", "shala-role", role=role), t.t("ru", "shala-role", role=role)) == labels


def test_the_student_count_is_a_plural_in_russian() -> None:
    """one (1, 21), few (2, 34), many (5, 11): three forms, the same within a category."""
    t = FluentTranslator()

    def word(n: int) -> str:
        text = t.t("ru", "shala-students", n=n)
        assert str(n) in text
        return text.replace(str(n), "")

    assert len({word(1), word(2), word(5)}) == 3
    assert (word(21), word(34), word(11)) == (word(1), word(2), word(5))


def test_no_shala_copy_claims_syc_or_certification() -> None:
    for locale in LOCALES:
        text = Path(BOT_FTL.format(locale)).read_text().lower()
        shala_lines = [line for line in text.splitlines() if line.startswith("shala-")]
        assert shala_lines, locale
        for line in shala_lines:
            for word in ("syc", "certif", "authoris", "authoriz", "сертиф", "авториз"):
                assert word not in line, line


def test_the_shala_role_is_never_uchitel() -> None:
    """«учитель» is the personal teacher (ID-04); the shala role is «Преподаватель»."""
    ru = FluentTranslator()
    for role in ROLES:
        assert "учител" not in ru.t("ru", "shala-role", role=role).lower()
