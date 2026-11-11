# ruff: noqa: RUF001
"""ST-06 copy (spec §2, §8): every new key on the right surface in both languages, as accepted;
the consent and Settings lines that became false are gone, and the quiet note is named in both;
the teacher's rest word is the one the private notes quote; RU keeps to Q15 and stays neutral."""

import re
from pathlib import Path

import pytest

from tristhana.domain.locale import Locale
from tristhana.infrastructure.i18n.fluent import FluentTranslator, message_ids

ROOT = Path(__file__).resolve().parents[3]
BOT_FTL = ROOT / "backend/src/tristhana/infrastructure/i18n/locales/{}/bot.ftl"
APP_FTL = ROOT / "miniapp/src/locales/{}/app.ftl"
LOCALES: tuple[Locale, ...] = ("en", "ru")

BOTH = (
    "students-days-note",
    "students-week",
    "students-last-asana",
    "students-last-standing",
    "students-blank-note",
    "students-quiet",
    "students-mark",
    "students-day-blank",
    "students-day",
    "students-day-length",
)
APP_ONLY = (
    "students-more",
    "students-load-failed",
    "students-card-load-failed",
    "students-day-blank-mark",
)
ADDED_TO_APP = ("links-students", "link-students-open", "day-label")

COPY: list[tuple[str, dict[str, str], str, str]] = [
    (
        "students-days-note",
        {},
        "Days follow each student's own time zone.",
        "Дни считаются по часовому поясу каждого ученика.",
    ),
    ("students-week", {}, "Last 7 days", "Последние 7 дней"),
    (
        "students-last-asana",
        {"asana": "Kapotasana", "series": "Intermediate"},
        "Last asana, as marked in their log: Kapotasana (Intermediate)",
        "Последняя асана по отметкам в журнале: Kapotasana (Intermediate серия)",
    ),
    (
        "students-last-standing",
        {},
        "As marked in their log: sun salutations and standing",
        "По отметкам в журнале: Сурья Намаскар и стоячие",
    ),
    (
        "students-blank-note",
        {},
        "Not every day gets logged, rest days included. A blank says nothing about the practice.",
        "Не каждый день попадает в журнал, в том числе дни отдыха. Пустой день ничего не говорит "
        "о практике.",
    ),
    ("students-quiet", {}, "Nothing shared for a while", "Какое-то время показать нечего"),
    ("students-mark", {"state": "practiced"}, "🧘", "🧘"),
    ("students-mark", {"state": "rest"}, "😌", "😌"),
    ("students-day", {"date": "D", "state": "S"}, "D: S", "D: S"),
    ("students-day-length", {"date": "D", "state": "S", "length": "L"}, "D: S, L", "D: S, L"),
    ("students-day-blank", {"date": "D"}, "D: ·", "D: ·"),
]

CONSENT_EN = (
    "If you confirm: "
    "• Лена sees your name (Ash) and what you log from today on: practice or rest and your "
    "practice length. "
    "• Лена also sees your last asana as marked in your log. "
    "• All rest you log looks the same, whatever the reason. "
    "• If nothing shows for a while, Лена sees a short note saying just that. "
    "• Any teacher on your list can also mark a new asana for you. You get a message and can "
    "undo it. "
    "• Check-ins, diary notes and the reason for a rest stay private. "
    "• Лена can send announcements to all their students through the bot. You can mute them. "
    "• You can remove Лена from your list any time in /teachers. No one gets a message."
)
CONSENT_RU = (
    "Если подтвердить: "
    "• Лена увидит твоё имя (Ash) и то, что ты отмечаешь с сегодняшнего дня: практика или отдых "
    "и объём практики. "
    "• Ещё будет видна твоя последняя асана по отметкам в журнале. "
    "• Любой отмеченный отдых выглядит одинаково, какой бы ни была причина. "
    "• Если какое-то время показать нечего, Лена увидит об этом короткую пометку. "
    "• Любой учитель из твоего списка может отметить тебе новую асану. Придёт сообщение, и "
    "отметку можно отменить. "
    "• Самочувствие, заметки и причина отдыха остаются личными. "
    "• Лена может отправлять объявления всем своим ученикам через бота. Их можно отключить. "
    "• Убрать из списка можно в любой момент в /teachers. Сообщений никто не получит."
)
PRIVACY_EN = (
    "Your log is yours. A teacher on your list sees your name, your last asana and what you log "
    "from the day you added them: practice or rest and your practice length. All rest you log "
    "looks the same, whatever the reason. If nothing shows for a while, the teacher sees a short "
    "note saying just that. A teacher on your list can also mark a new asana for you: you get a "
    "message and can undo it. Check-ins, diary notes and the reason for a rest stay private. "
    "You can remove a teacher from your list any time."
    " Teachers on your list and your shalas can send you announcements; "
    "you can mute each one."
)
PRIVACY_RU = (
    "Твой журнал принадлежит тебе. Учитель из твоего списка видит твоё имя, последнюю асану и "
    "то, что ты отмечаешь со дня добавления: практика или отдых и объём практики. Любой "
    "отмеченный отдых выглядит одинаково, какой бы ни была причина. Если какое-то время показать "
    "нечего, учитель увидит об этом короткую пометку. Учитель из твоего списка также может "
    "отметить тебе новую асану: придёт сообщение, и отметку можно отменить. Самочувствие, "
    "заметки и причина отдыха "
    "остаются личными. Убрать учителя из списка можно в любой момент."
    " Учителя из твоего списка и твои шалы могут присылать объявления; "
    "отключить их можно отдельно для каждого."
)


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


def _app(locale: str) -> dict[str, str]:
    return _sources(Path(str(APP_FTL).format(locale)))


def _bot(locale: str) -> dict[str, str]:
    return _sources(Path(str(BOT_FTL).format(locale)))


def _flat(text: str) -> str:
    return " ".join(text.split())


def _new_copy(locale: str) -> dict[str, str]:
    every = _bot(locale) | _app(locale)
    named = {k: v for k, v in every.items() if k.startswith("students-")}
    return named | {k: every[k] for k in ("invite-consent", "settings-privacy-sharing")}


# Keys, by surface


@pytest.mark.parametrize("locale", LOCALES)
def test_the_bot_has_its_keys(locale: Locale) -> None:
    assert sorted(set(BOTH) - message_ids(locale)) == []


@pytest.mark.parametrize("locale", LOCALES)
def test_the_app_has_its_keys(locale: str) -> None:
    assert sorted(set(BOTH + APP_ONLY + ADDED_TO_APP) - set(_app(locale))) == []


@pytest.mark.parametrize("key", APP_ONLY)
def test_app_only_keys_stay_out_of_the_bot(key: str) -> None:
    assert key not in _bot("en")


@pytest.mark.parametrize("load", [_bot, _app], ids=["bot", "app"])
def test_the_new_keys_have_parity_across_languages(load: object) -> None:
    def students(locale: str) -> set[str]:
        return {k for k in load(locale) if k.startswith("students-")}  # type: ignore[operator]

    assert students("en")
    assert students("en") == students("ru")


# The copy


@pytest.mark.parametrize(
    ("key", "args", "en", "ru"), COPY, ids=[f"{r[0]}-{i}" for i, r in enumerate(COPY)]
)
def test_the_copy_reads_as_accepted(key: str, args: dict[str, str], en: str, ru: str) -> None:
    assert _t("en", key, **args) == en
    assert _t("ru", key, **args) == ru


def test_the_mark_is_only_the_two_states() -> None:
    """Anything but `practiced` falls to the default; no third emoji exists to fall to."""
    assert not re.search(r"🌙|🌸|🤒|✈|🌱", _bot("en")["students-mark"])


@pytest.mark.parametrize(
    ("locale", "more", "failed", "blank"),
    [
        (
            "en",
            "Show more",
            "Couldn't load your students. Try again in a moment.",
            "{ $date }: nothing to show",
        ),
        (
            "ru",
            "Показать ещё",
            "Не получилось загрузить учеников. Попробуй ещё раз чуть позже.",
            "{ $date }: показать нечего",
        ),
    ],
)
def test_the_app_only_copy(locale: str, more: str, failed: str, blank: str) -> None:
    app = _app(locale)

    assert _flat(app["students-more"]) == more
    assert _flat(app["students-load-failed"]) == failed
    assert _flat(app["students-day-blank"]) == blank


@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("key", [*BOTH[:6]])
def test_the_shared_keys_read_the_same_on_both_surfaces(locale: str, key: str) -> None:
    assert _flat(_app(locale)[key]) == _flat(_bot(locale)[key])


@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("key", ADDED_TO_APP)
def test_the_keys_added_to_the_app_read_as_the_bots(locale: str, key: str) -> None:
    assert _flat(_app(locale)[key]) == _flat(_bot(locale)[key])


# The consent and the Settings line


def test_the_consent_reads_as_accepted() -> None:
    assert _t("en", "invite-consent", name="Лена", me=" (Ash)") == CONSENT_EN
    assert _t("ru", "invite-consent", name="Лена", me=" (Ash)") == CONSENT_RU


def test_the_privacy_line_reads_as_accepted() -> None:
    assert _flat(_app("en")["settings-privacy-sharing"]) == PRIVACY_EN
    assert _flat(_app("ru")["settings-privacy-sharing"]) == PRIVACY_RU


@pytest.mark.parametrize(
    "gone",
    [
        "nothing more for now",
        "when teachers get their own screen",
        "When teachers get their own screen",
        "will then also",
        "unless you choose",
        "пока больше ничего",
        "когда у учителей появится свой экран",
        "Когда у учителей появится свой экран",
        "Тогда же",
        "если ты не решишь",
    ],
)
@pytest.mark.parametrize("locale", LOCALES)
def test_the_old_sentences_are_gone(locale: str, gone: str) -> None:
    assert gone not in Path(str(BOT_FTL).format(locale)).read_text()
    assert gone not in Path(str(APP_FTL).format(locale)).read_text()


@pytest.mark.parametrize(
    ("locale", "consent", "privacy"),
    [
        (
            "en",
            "If nothing shows for a while, { $name } sees a short note saying just that.",
            "If nothing shows for a while, the teacher sees a short note saying just that.",
        ),
        (
            "ru",
            "Если какое-то время показать нечего, { $name } увидит об этом короткую пометку.",
            "Если какое-то время показать нечего, учитель увидит об этом короткую пометку.",
        ),
    ],
)
def test_the_quiet_sentence_is_in_both(locale: str, consent: str, privacy: str) -> None:
    assert consent in _flat(_bot(locale)["invite-consent"])
    assert privacy in _flat(_app(locale)["settings-privacy-sharing"])


def test_the_consent_says_all_rest_you_log() -> None:
    assert "All rest you log looks the same" in _bot("en")["invite-consent"]
    assert "Любой отмеченный отдых выглядит одинаково" in _bot("ru")["invite-consent"]


@pytest.mark.parametrize("locale", LOCALES)
def test_the_consent_fits_a_message_with_long_names(locale: Locale) -> None:
    longest = "😀" * 64

    text = FluentTranslator().t(locale, "invite-consent", name=longest, me=f" ({longest})")

    assert len(text.encode("utf-16-le")) // 2 <= 4096


# The promise the private notes make


def _quoted(text: str) -> str:
    [word] = re.findall(r"[“«]([^”»]+)[”»]", text)
    return word


def _word(status_rest: str) -> str:
    return status_rest.strip().split(" ", 1)[1]


@pytest.mark.parametrize("locale", LOCALES)
def test_the_teachers_rest_label_is_what_the_private_notes_quote(locale: str) -> None:
    bot, app = _bot(locale), _app(locale)
    label = _word(bot["status-rest"])

    assert _word(app["status-rest"]) == label
    assert _quoted(bot["log-private-note"]) == label
    assert _quoted(app["today-private-note"]) == label
    assert _quoted(app["settings-privacy-ladies"]) == label


# RU rules and tone


def test_russian_copy_avoids_the_ruled_out_words() -> None:
    for key, value in _new_copy("ru").items():
        lowered = value.lower()
        assert "отвяз" not in lowered, key
        assert "связ" not in lowered, key
        assert "преподавател" not in lowered, key
        assert "длин" not in lowered, key


def test_russian_copy_is_gender_neutral() -> None:
    for key, value in _new_copy("ru").items():
        assert "(а)" not in value, key
        assert not re.search(r"\bты\s+\w+л[аи]?\b", value, re.IGNORECASE), key


@pytest.mark.parametrize(
    ("locale", "words"),
    [
        ("en", ("should", "must", "forgot", "miss", "failed", "sorry", "lose", "streak")),
        ("ru", ("надо", "должен", "должна", "забы", "пропус", "потер")),
    ],
)
def test_the_copy_stays_free_of_nudges(locale: str, words: tuple[str, ...]) -> None:
    for key, value in _new_copy(locale).items():
        for word in words:
            assert word not in value.lower(), (key, word)


def test_names_stay_nominative_in_russian() -> None:
    text = _t("ru", "invite-consent", name="Игорь", me="")

    assert "Игорь увидит твоё имя" in text
    assert "Игорь увидит об этом" in text
