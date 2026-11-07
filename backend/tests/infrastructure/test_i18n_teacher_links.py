# ruff: noqa: RUF001
"""ID-04 copy (spec §2, §10): every new key in both languages, exactly as accepted; strings that
became false are gone; RU avoids the words Q15 and S3 rule out; no one is ever "unverified"."""

import re
from pathlib import Path

import pytest

from tristhana.domain.locale import Locale
from tristhana.infrastructure.i18n.fluent import FluentTranslator, message_ids

ROOT = Path(__file__).resolve().parents[3]
BOT_FTL = ROOT / "backend/src/tristhana/infrastructure/i18n/locales/{}/bot.ftl"
APP_FTL = ROOT / "miniapp/src/locales/{}/app.ftl"
LOCALES: tuple[Locale, ...] = ("en", "ru")

BOT_KEYS = (
    "invite-ask",
    "invite-consent",
    "invite-know-them",
    "invite-not-told",
    "invite-accept",
    "invite-decline",
    "invite-linked",
    "invite-already",
    "invite-own",
    "invite-invalid",
    "invite-full",
    "link-student-joined",
    "invite-hint",
    "invite-share-text",
    "invite-new-ask",
    "invite-qr-caption",
    "link-unlink-ask",
    "link-next-main",
    "link-remove-ask",
    "links-empty",
    "links-no-students",
    "links-primary-hint",
    "links-main-chosen",
    "links-main-auto",
    "links-title",
    "command-teachers",
    "link-no-name",
    "export-readme-links",
    "links-make-main",
    "links-remove",
    "links-invite-first",
    "links-students",
    "links-invite",
    "links-remove-yes",
    "invite-share",
    "invite-qr",
    "invite-new",
    "invite-new-yes",
)
# The rows of §2's table: key, arguments, EN, RU.
COPY: list[tuple[str, dict[str, str | int], str, str]] = [
    ("invite-accept", {}, "✅ Confirm", "✅ Подтвердить"),
    ("invite-decline", {}, "Not now", "Не сейчас"),
    (
        "invite-linked",
        {"name": "Лена"},
        "✅ Лена is on your list of teachers now.",
        "✅ Лена теперь в списке твоих учителей.",
    ),
    (
        "invite-already",
        {"name": "Лена"},
        "Лена is already on your list of teachers.",
        "Лена уже в списке твоих учителей.",
    ),
    (
        "invite-own",
        {},
        "This is your own invite link: share it with your students.",
        "Это твоя ссылка-приглашение: поделись ею с учениками.",
    ),
    (
        "invite-invalid",
        {},
        "This invite link no longer works. The person who shared it can send a new one.",
        "Эта ссылка больше не работает. Новую может прислать тот, кто ею поделился.",
    ),
    (
        "invite-full",
        {},
        "This link can't add a teacher right now.",
        "Сейчас по этой ссылке не получится добавить учителя.",
    ),
    (
        "link-student-joined",
        {"name": "Ash"},
        "👥 Ash is on your list of students now.",
        "👥 Ash теперь в списке твоих учеников.",
    ),
    (
        "invite-hint",
        {},
        "Share this link or QR code. Each student confirms for themselves.",
        "Поделись ссылкой или QR-кодом. Каждый ученик подтверждает сам.",
    ),
    (
        "invite-share-text",
        {},
        "My link to add me as your teacher in Tristhana. The bot shows what I'd see before you "
        "confirm.",
        "Моя ссылка, чтобы добавить меня как учителя в Tristhana. Перед подтверждением бот "
        "покажет, что мне будет видно.",
    ),
    (
        "invite-new-ask",
        {},
        "Get a new link? The old link and QR stop working. People already on your list stay.",
        "Сделать новую ссылку? Старая ссылка и QR перестанут работать. Те, кто уже в списке, "
        "останутся.",
    ),
    (
        "invite-qr-caption",
        {},
        "Scan to add me as your teacher in Tristhana.",
        "Отсканируй, чтобы добавить меня как учителя в Tristhana.",
    ),
    (
        "link-unlink-ask",
        {"name": "Лена"},
        "Remove Лена from your teachers? They won't get a message, but you'll no longer be on "
        "their list.",
        "Убрать из списка учителей: Лена? Сообщений никто не получит, просто в списке учеников "
        "тебя больше не будет.",
    ),
    (
        "link-next-main",
        {"name": "Лена"},
        "Лена becomes your main teacher.",
        "Основным учителем станет: Лена.",
    ),
    (
        "link-remove-ask",
        {"name": "Ash"},
        "Remove Ash from your students? They won't get a message.",
        "Убрать из списка учеников: Ash? Сообщений никто не получит.",
    ),
    (
        "links-empty",
        {},
        "No teachers on your list. Your log works the same either way.",
        "Учителей в списке нет. Журнал практики работает и так.",
    ),
    ("links-no-students", {}, "No students on your list.", "Учеников в списке нет."),
    (
        "links-primary-hint",
        {},
        "⭐ marks your main teacher. You can change it any time.",
        "⭐ — твой основной учитель. Поменять можно в любой момент.",
    ),
    (
        "links-main-chosen",
        {"name": "Лена"},
        "⭐ Main teacher: Лена",
        "⭐ Основной учитель: Лена",
    ),
    (
        "links-main-auto",
        {"name": "Лена"},
        "⭐ Main teacher: Лена (first on your list)",
        "⭐ Основной учитель: Лена (в начале списка)",
    ),
    ("links-title", {}, "👥 Teachers and students", "👥 Учителя и ученики"),
    ("command-teachers", {}, "My teachers and students", "Мои учителя и ученики"),
    ("link-no-name", {}, "(no name)", "(без имени)"),
    (
        "export-readme-links",
        {},
        "teacher_links in data.json: your teachers and students, without names, so this list "
        "holds no one else's details.",
        "teacher_links в data.json: твои учителя и ученики без имён, поэтому чужих данных "
        "в этом списке нет.",
    ),
    ("links-make-main", {}, "⭐ Make main", "⭐ Сделать основным"),
    ("links-remove", {}, "Remove…", "Убрать…"),
    (
        "links-invite-first",
        {},
        "I teach: invite students",
        "Я преподаю: пригласить учеников",
    ),
    ("links-students", {"count": 12}, "👥 My students (12)", "👥 Мои ученики (12)"),
    ("links-invite", {}, "➕ Invite students", "➕ Пригласить учеников"),
    ("links-remove-yes", {}, "Remove", "Убрать"),
    ("invite-share", {}, "📤 Share", "📤 Поделиться"),
    ("invite-qr", {}, "🔳 QR code", "🔳 QR-код"),
    ("invite-new", {}, "🔄 New link…", "🔄 Новая ссылка…"),
    ("invite-new-yes", {}, "🔄 Yes, new link", "🔄 Да, новая ссылка"),
]


def _t(locale: Locale, key: str, **args: str | int) -> str:
    return " ".join(FluentTranslator().t(locale, key, **args).split())


def _sources(path: Path) -> dict[str, str]:
    """Each message of an .ftl file with its raw value (a crude parser, enough for greps)."""
    found: dict[str, str] = {}
    key = None
    for line in path.read_text().splitlines():
        start = re.match(r"([a-z][a-z0-9-]*) *=(.*)", line)
        if start:
            key = start[1]
            found[key] = start[2]
        elif key and line.startswith((" ", "\t")):
            found[key] += "\n" + line
        else:
            key = None
    return found


def _new_copy(locale: str) -> dict[str, str]:
    """The ID-04 messages of both surfaces, plus the two app strings it rewrites."""
    every = _sources(BOT_FTL.parent.parent / locale / "bot.ftl") | _sources(
        APP_FTL.parent.parent / locale / "app.ftl"
    )
    return {
        k: v
        for k, v in every.items()
        if k in BOT_KEYS
        or k.startswith(("invite-", "link-", "links-"))
        or k in ("settings-privacy-sharing", "settings-name-hint")
    }


@pytest.mark.parametrize("locale", LOCALES)
def test_every_new_bot_key_exists(locale: Locale) -> None:
    assert sorted(set(BOT_KEYS) - message_ids(locale)) == []


@pytest.mark.parametrize(("key", "args", "en", "ru"), COPY, ids=[row[0] for row in COPY])
def test_the_copy_reads_as_accepted(key: str, args: dict[str, str | int], en: str, ru: str) -> None:
    assert _t("en", key, **args) == en
    assert _t("ru", key, **args) == ru


def _app(locale: str) -> dict[str, str]:
    return _sources(Path(str(APP_FTL).format(locale)))


def _bot(locale: str) -> dict[str, str]:
    return _sources(Path(str(BOT_FTL).format(locale)))


@pytest.mark.parametrize(
    ("locale", "text"),
    [
        (
            "en",
            "Your log is yours. A teacher on your list sees your name. When teachers get their "
            "own screen, they'll also see what you log: practice or rest, your practice length "
            "and your last asana. A teacher on your list will also be able to mark a new asana "
            "for you, and you can undo it. Check-ins, diary notes and the reason for a rest stay "
            "private unless you choose to share them. You can remove a teacher from your list "
            "any time.",
        ),
        (
            "ru",
            "Твой журнал принадлежит тебе. Учитель из твоего списка видит твоё имя. Когда у "
            "учителей появится свой экран, будет видно и то, что ты отмечаешь: практика или "
            "отдых, объём практики и последняя асана. Учитель из твоего списка также сможет "
            "отметить тебе новую асану, а ты сможешь это отменить. Самочувствие, заметки и "
            "причина отдыха остаются личными, если ты не решишь ими делиться. Убрать учителя из "
            "списка можно в любой момент.",
        ),
    ],
)
def test_the_privacy_line_says_what_a_link_shows(locale: str, text: str) -> None:
    assert " ".join(_app(locale)["settings-privacy-sharing"].split()) == text


@pytest.mark.parametrize(
    "gone",
    ["When teachers join, you choose what they see.", "Когда появятся учителя, ты выберешь"],
)
def test_the_old_privacy_sentence_is_gone(gone: str) -> None:
    for locale in LOCALES:
        assert gone not in Path(str(APP_FTL).format(locale)).read_text()
        assert gone not in Path(str(BOT_FTL).format(locale)).read_text()


@pytest.mark.parametrize(
    ("locale", "text"),
    [
        (
            "en",
            "How I greet you, and the name your teachers and students here see. Leave it empty "
            "to use your Telegram name.",
        ),
        (
            "ru",
            "Так я к тебе обращаюсь, и это имя видят твои учителя и ученики. Оставь пустым, и я "
            "возьму имя из Telegram.",
        ),
    ],
)
def test_the_name_hint_says_who_sees_it(locale: str, text: str) -> None:
    assert " ".join(_app(locale)["settings-name-hint"].split()) == text


@pytest.mark.parametrize(
    ("locale", "words"),
    [("en", "teacher and student lists"), ("ru", "списки учителей и учеников")],
)
def test_the_delete_explanation_lists_the_links(locale: str, words: str) -> None:
    assert words in _app(locale)["delete-explain"]
    assert words in _bot(locale)["delete-explain"]


def test_the_readme_key_is_part_of_the_export() -> None:
    from tristhana.application.export import README_KEYS

    assert "export-readme-links" in README_KEYS


def test_russian_copy_avoids_the_ruled_out_words() -> None:
    for key, value in _new_copy("ru").items():
        lowered = value.lower()
        assert "отвяз" not in lowered, key
        assert "связ" not in lowered, key
        assert "преподавател" not in lowered, key  # Q15; «преподаю» is fine


def test_the_consent_and_privacy_say_объём_not_длина() -> None:
    copy = _new_copy("ru")
    for key in ("invite-consent", "settings-privacy-sharing"):
        assert "длин" not in copy[key].lower(), key
        assert "объём" in copy[key].lower(), key


@pytest.mark.parametrize(
    ("locale", "words"),
    [
        ("en", ("unverified", "not verified", "guru", "instructor", "coach")),
        ("ru", ("непровер", "неподтвержд", "верифиц", "гуру", "инструктор", "коуч", "тренер")),
    ],
)
def test_no_one_is_unverified_and_a_teacher_is_a_teacher(
    locale: str, words: tuple[str, ...]
) -> None:
    for key, value in _new_copy(locale).items():
        for word in words:
            assert word not in value.lower(), (key, word)


def test_russian_copy_is_gender_neutral() -> None:
    for key, value in _new_copy("ru").items():
        assert "(а)" not in value, key
        assert not re.search(r"\bты\s+\w+л[аи]?\b", value, re.IGNORECASE), key


@pytest.mark.parametrize(
    ("locale", "words"),
    [
        ("en", ("should", "must", "forgot", "miss", "failed", "sorry", "lose")),
        ("ru", ("надо", "должен", "должна", "забы", "пропус", "потер")),
    ],
)
def test_the_copy_stays_free_of_nudges(locale: str, words: tuple[str, ...]) -> None:
    for key, value in _new_copy(locale).items():
        for word in words:
            assert word not in value.lower(), (key, word)


def test_names_stay_as_given_in_russian() -> None:
    """No declension can happen: every RU line keeps `$name` where the nominative reads right."""
    assert _t("ru", "link-unlink-ask", name="Игорь").startswith("Убрать из списка учителей: Игорь?")
    assert _t("ru", "link-next-main", name="Игорь") == "Основным учителем станет: Игорь."
