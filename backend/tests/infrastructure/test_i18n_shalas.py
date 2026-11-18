# ruff: noqa: RUF001
"""SC-01 copy (spec §2): every new key in both languages, the drafted rows exactly, the role
select (Q104), and the glossary split: «Преподаватель» is the shala role, «учитель» the
personal teacher. No copy implies SYC authorisation."""

from pathlib import Path
from uuid import UUID

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
    # UI-06 stage 6 (spec §6 and the ux-writer's review).
    (
        "shala-staff-welcome",
        {"shala": "S", "role": "Teacher"},
        "✅ You're on the staff now: S. Role: Teacher. The shala's card is below. Your week of "
        "classes is under ☰ Menu → 🗓 My schedule.",
        "✅ Теперь ты в команде шалы: S. Роль: Teacher. Карточка шалы — ниже. Неделя занятий — "
        "в ☰ Меню → 🗓 Моё расписание.",
    ),
    (
        "shala-students-not-yours",
        {},
        "These are the shala's students. They show up in 👥 My students once they pick you as "
        "their teacher or open your own link (➕ Invite my students).",
        "Это ученики шалы. В «👥 Мои ученики» они появятся, когда выберут тебя учителем или "
        "откроют твою личную ссылку (➕ Пригласить своих учеников).",
    ),
    (
        "shala-moon-shared",
        {},
        "🌙 Staff and students follow this calendar unless they chose a city.",
        "🌙 Команда и ученики шалы следуют этому календарю, если сами не выбрали город.",
    ),
    ("ann-announce", {}, "📣 Announce to the shala", "📣 Объявление для шалы"),
    ("ann-announce-students", {}, "📣 Announce to my students", "📣 Объявление своим ученикам"),
    # C19: each dead end says what to do next.
    (
        "shala-full",
        {},
        "This link can't add you to the shala right now. Please let the shala know.",
        "Сейчас по этой ссылке не получится присоединиться к шале. Сообщи об этом в шалу.",
    ),
    (
        "shala-caps",
        {},
        "No more shalas or staff links for now: that's the limit. A staff link works for 7 "
        "days; after that you can make a new one.",
        "Больше шал или ссылок для команды пока не получится: это предел. Ссылка для команды "
        "действует 7 дней, потом можно создать новую.",
    ),
    (
        "class-invalid",
        {},
        "That change doesn't fit the schedule. Open the class in the app and check its days "
        "and times.",
        "Такое изменение не вписывается в расписание. Открой занятие в приложении и проверь "
        "дни и время.",
    ),
]
# C14 (UI-06 stage 6, the owner kept «Администратор»): what each role a picker offers can do,
# as `application/policies.py` allows it.
ROLE_HINTS = {
    "admin": (
        "Everything except deleting the shala and adding managers.",
        "Всё, кроме удаления шалы и назначения управляющих.",
    ),
    "teacher": (
        "Classes and schedule, attendance, announcements, the student list; students can pick "
        "them as their teacher.",
        "Занятия и расписание, посещаемость, объявления, список учеников; ученики могут выбрать "
        "преподавателя своим учителем.",
    ),
    "assistant": (
        "Attendance and the student list; not the schedule or announcements.",
        "Посещаемость и список учеников; без расписания и объявлений.",
    ),
    "office": (
        "Classes and schedule, attendance, announcements, the student list; can remove a "
        "student; not the shala's settings or roles.",
        "Занятия и расписание, посещаемость, объявления, список учеников; может убрать ученика; "
        "без настроек шалы и ролей.",
    ),
}
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


@pytest.mark.parametrize(("role", "lines"), list(ROLE_HINTS.items()))
def test_each_role_says_what_it_can_do(role: str, lines: tuple[str, str]) -> None:
    t = FluentTranslator()

    assert (t.t("en", "shala-role-hint", role=role), t.t("ru", "shala-role-hint", role=role)) == (
        lines
    )


def test_the_role_hints_follow_the_policies() -> None:
    """The schedule and announcements for exactly `can_manage_schedule`'s roles (the front desk
    included), a student's removal for the front desk, and the student list for every seat."""
    from tristhana.application.policies import (
        can_manage_schedule,
        can_remove_student,
        can_view_shala_students,
    )
    from tristhana.domain.shalas import Membership, ShalaRole

    t = FluentTranslator()
    for role in ShalaRole:
        seat = Membership(UUID(int=1), False, frozenset({role}), False)
        hint = t.t("en", "shala-role-hint", role=role.value)
        schedule = hint.startswith(("Classes and schedule", "Everything"))
        assert schedule == can_manage_schedule(seat), role
        assert ("remove a student" in hint or hint.startswith("Everything")) == (
            can_remove_student(seat, own=False)
        ), role
        assert can_view_shala_students(seat)
        assert "student list" in hint or hint.startswith("Everything"), role


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
