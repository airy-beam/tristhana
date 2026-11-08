# ruff: noqa: RUF001
"""Teacher-mark copy (PR-08 Phase 3, spec §8): every new key on the right surface in both
languages, as accepted; the consent and Settings lines lose "Later" and say a message comes;
the banned words of PR-08 §7 stay out; RU stays gender-neutral."""

import re
from pathlib import Path

import pytest

from tristhana.domain.locale import Locale
from tristhana.infrastructure.i18n.fluent import FluentTranslator, message_ids

ROOT = Path(__file__).resolve().parents[3]
BOT_FTL = ROOT / "backend/src/tristhana/infrastructure/i18n/locales/{}/bot.ftl"
APP_FTL = ROOT / "miniapp/src/locales/{}/app.ftl"
LOCALES: tuple[Locale, ...] = ("en", "ru")

BOT = (
    "students-give",
    "students-give-pick",
    "students-give-option",
    "students-give-range",
    "students-give-ask",
    "students-give-ask-range",
    "students-give-ask-across",
    "students-give-yes",
    "students-given",
    "students-given-range",
    "students-give-stale",
    "students-give-unset",
    "mark-received",
    "mark-received-range",
    "mark-received-back",
    "mark-received-undo-hint",
    "progression-marked-by",
    "progression-by-teacher",
    "progression-mark-moved-on",
    "progression-undo-mark",
)
APP = (
    "students-give",
    "students-give-option",
    "students-give-range",
    "students-give-ask",
    "students-give-ask-range",
    "students-give-ask-across",
    "students-give-yes",
    "students-given",
    "students-given-range",
    "students-give-stale",
    "students-give-unset",
    "progression-marked-by",
    "progression-event-by",
    "progression-by-teacher",
    "progression-mark-moved-on",
)
NEW = tuple(dict.fromkeys(BOT + APP))

A = {"asana": "Bharadvajasana", "from": "Supta Vajrasana", "series": "Intermediate"}
NAMED = {"name": "Anna", **A}
COPY: list[tuple[str, dict[str, str], str, str]] = [
    ("students-give", {}, "🎉 Mark new asana", "🎉 Отметить новую асану"),
    (
        "students-give-pick",
        {"name": "Anna"},
        "Anna: which new asana? Anna gets one message, even for a few.",
        "Anna: какая новая асана? Anna получит одно сообщение, даже если асан несколько.",
    ),
    ("students-give-option", {"asana": "Supta Vajrasana"}, "Supta Vajrasana", "Supta Vajrasana"),
    # The picker's range buttons name only the last stop (owner, 2026-11-08).
    ("students-give-range", A, "→ Bharadvajasana", "→ Bharadvajasana"),
    (
        "students-give-ask-across",
        {
            "name": "Anna",
            "from": "Setu Bandhasana",
            "from_series": "Primary",
            "asana": "Krounchasana",
            "series": "Intermediate",
        },
        "Anna: new asanas Setu Bandhasana (Primary) → Krounchasana (Intermediate). Mark them? "
        "Anna gets one message from the bot and can undo it.",
        "Anna: новые асаны — Setu Bandhasana (Primary серия) → Krounchasana (Intermediate "
        "серия). Отметить? Anna получит одно сообщение от бота и сможет отменить отметку.",
    ),
    ("progression-undo-mark", {}, "↩︎ Undo the mark", "↩︎ Отменить отметку"),
    (
        "students-give-ask",
        {"name": "Anna", "asana": "Supta Vajrasana", "series": "Intermediate"},
        "Anna: the next asana is Supta Vajrasana (Intermediate). Mark it as new? Anna gets a "
        "message from the bot and can undo it.",
        "Anna: следующая асана — Supta Vajrasana (Intermediate серия). Отметить как новую? Anna "
        "получит сообщение от бота и сможет отменить отметку.",
    ),
    (
        "students-give-ask-range",
        NAMED,
        "Anna: new asanas Supta Vajrasana → Bharadvajasana (Intermediate). Mark them? Anna gets "
        "one message from the bot and can undo it.",
        "Anna: новые асаны — Supta Vajrasana → Bharadvajasana (Intermediate серия). Отметить? "
        "Anna получит одно сообщение от бота и сможет отменить отметку.",
    ),
    ("students-give-yes", {}, "🎉 Yes, mark", "🎉 Да, отметить"),
    (
        "students-given",
        {"asana": "Supta Vajrasana"},
        "✅ Marked: Supta Vajrasana.",
        "✅ Отмечено: Supta Vajrasana.",
    ),
    (
        "students-given-range",
        A,
        "✅ Marked: Supta Vajrasana → Bharadvajasana.",
        "✅ Отмечено: Supta Vajrasana → Bharadvajasana.",
    ),
    (
        "students-give-stale",
        {},
        "This card was out of date, so nothing was marked. Here it is now.",
        "Карточка устарела, поэтому ничего не отмечено. Вот актуальная.",
    ),
    (
        "students-give-unset",
        {"name": "Anna"},
        "Anna hasn't set their practice yet.",
        "Anna: практика пока не указана.",
    ),
    (
        "mark-received",
        {"asana": "Supta Vajrasana", "teacher": "Лена"},
        "🎉 New asana: Supta Vajrasana. Enjoy it! Marked by Лена.",
        "🎉 Новая асана: Supta Vajrasana. Приятного знакомства! Отметка: Лена.",
    ),
    (
        "mark-received-range",
        {**A, "teacher": "Лена"},
        "🎉 New asanas: Supta Vajrasana → Bharadvajasana. Enjoy them! Marked by Лена.",
        "🎉 Новые асаны: Supta Vajrasana → Bharadvajasana. Приятного знакомства! Отметка: Лена.",
    ),
    (
        "mark-received-back",
        {"asana": "Bakasana B", "teacher": "Лена"},
        "Bakasana B is in your practice. Marked by Лена.",
        "Bakasana B — в твоей практике. Отметка: Лена.",
    ),
    (
        "mark-received-undo-hint",
        {},
        "If this doesn't match your practice, you can undo it.",
        "Если это не совпадает с твоей практикой, отметку можно отменить.",
    ),
    ("progression-marked-by", {"teacher": "Лена"}, "Marked by Лена", "Отметка: Лена"),
    ("progression-by-teacher", {}, "a teacher", "учитель"),
    (
        "progression-mark-moved-on",
        {},
        "Your practice has changed since this mark, so nothing was undone. To set where it ends "
        "now, use ✏️ Change.",
        "С этой отметки практика уже изменилась, поэтому ничего не отменено. Чтобы указать, где "
        "она заканчивается сейчас, нажми ✏️ Изменить.",
    ),
]
APP_COPY: list[tuple[str, dict[str, str], str, str]] = [
    ("progression-event-by", {"teacher": "Anna"}, "· Anna", "· Anna"),
]

# PR-08 §7, applied to every new key.
BANNED_EN = (
    "unlock", "level", "achieve", "earn", "finally", "behind", "lost", "regress", "back to",
    "demote", "only", "again", "streak", "rank", "goal", "should", "faster",
)  # fmt: skip
BANNED_RU = (
    "уровень", "достижен", "разблок", "наконец", "откат", "потер", "отстал", "только", "опять",
    "цель", "надо", "должен",
)  # fmt: skip
# No exemptions: every new key is held to the full list.
EXEMPT: set[tuple[str, str]] = set()

CONSENT_LINE_EN = (
    "Any teacher on your list can also mark a new asana for you. You get a message and can undo it."
)
CONSENT_LINE_RU = (
    "Любой учитель из твоего списка может отметить тебе новую асану. Придёт сообщение, и отметку "
    "можно отменить."
)
PRIVACY_LINE_EN = (
    "A teacher on your list can also mark a new asana for you: you get a message and can undo it."
)
PRIVACY_LINE_RU = (
    "Учитель из твоего списка также может отметить тебе новую асану: придёт сообщение, и отметку "
    "можно отменить."
)


def _flat(text: str) -> str:
    return " ".join(text.replace("⁨", "").replace("⁩", "").split())


def _t(locale: Locale, key: str, **args: str) -> str:
    return _flat(FluentTranslator().t(locale, key, **args))


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


def _bot(locale: str) -> dict[str, str]:
    return _sources(Path(str(BOT_FTL).format(locale)))


def _app(locale: str) -> dict[str, str]:
    return _sources(Path(str(APP_FTL).format(locale)))


# Keys, by surface


@pytest.mark.parametrize("locale", LOCALES)
def test_the_bot_has_every_new_key(locale: Locale) -> None:
    assert sorted(set(BOT) - message_ids(locale)) == []


@pytest.mark.parametrize("locale", LOCALES)
def test_the_app_has_every_new_key(locale: str) -> None:
    assert sorted(set(APP) - set(_app(locale))) == []


@pytest.mark.parametrize("load", [_bot, _app], ids=["bot", "app"])
def test_en_and_ru_have_the_same_new_keys(load: object) -> None:
    def new(locale: str) -> set[str]:
        return {k for k in load(locale) if k in NEW}  # type: ignore[operator]

    assert new("en")
    assert new("en") == new("ru")


def test_the_mark_undo_label_is_bot_only() -> None:
    """The Mini App puts Undo on each history row, so it needs no second label."""
    assert "progression-undo-mark" not in _app("en")
    assert "progression-undo-mark" not in _app("ru")


def test_the_give_keys_dont_clash_with_the_day_mark() -> None:
    assert "students-mark" not in NEW
    assert "students-mark" in message_ids("en")


# The copy


@pytest.mark.parametrize(("key", "args", "en", "ru"), COPY, ids=[r[0] for r in COPY])
def test_the_bot_copy_reads_as_accepted(key: str, args: dict[str, str], en: str, ru: str) -> None:
    assert _t("en", key, **args) == en
    assert _t("ru", key, **args) == ru


@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("key", [k for k in APP if k in BOT])
def test_the_shared_keys_read_the_same_on_both_surfaces(locale: str, key: str) -> None:
    assert _flat(_app(locale)[key]) == _flat(_bot(locale)[key])


@pytest.mark.parametrize(("key", "args", "en", "ru"), APP_COPY, ids=[r[0] for r in APP_COPY])
def test_the_app_only_copy(key: str, args: dict[str, str], en: str, ru: str) -> None:
    def render(source: str) -> str:
        return _flat(re.sub(r"\{ *\$(\w+) *\}", lambda m: args[m[1]], source))

    assert render(_app("en")[key]) == en
    assert render(_app("ru")[key]) == ru


# Consent and Settings: "Later" is false now


def test_the_consent_says_a_message_comes_and_no_longer_later() -> None:
    en = _t("en", "invite-consent", name="Лена", me=" (Ash)")
    ru = _t("ru", "invite-consent", name="Лена", me=" (Ash)")

    assert CONSENT_LINE_EN in en
    assert CONSENT_LINE_RU in ru
    assert "Later" not in en
    assert "Позже" not in ru
    assert "will also be able to" not in en
    assert "сможет отметить" not in ru


@pytest.mark.parametrize(
    ("locale", "line", "later"),
    [("en", PRIVACY_LINE_EN, "Later"), ("ru", PRIVACY_LINE_RU, "Позже")],
)
def test_the_privacy_line_says_a_message_comes_and_no_longer_later(
    locale: str, line: str, later: str
) -> None:
    text = _flat(_app(locale)["settings-privacy-sharing"])

    assert line in text
    assert later not in text


def test_the_consent_still_fits_one_message_with_long_names() -> None:
    long = "😀" * 64
    for locale in LOCALES:
        text = FluentTranslator().t(locale, "invite-consent", name=long, me=f" ({long})")
        assert len(text.encode("utf-16-le")) // 2 <= 4096


# Tone


@pytest.mark.parametrize("locale", LOCALES)
def test_no_new_key_uses_a_banned_word(locale: str) -> None:
    sources = _bot(locale) | _app(locale)
    banned = BANNED_EN if locale == "en" else BANNED_RU
    found = {
        (key, word)
        for key in NEW
        if key in sources
        for word in banned
        if re.search(rf"(?<!\w){re.escape(word)}", sources[key], re.IGNORECASE)
    }

    assert found - EXEMPT == set()


def test_the_russian_copy_is_gender_neutral() -> None:
    """«Отметка: …», «отмечено», «получит»: no past tense with a gender ending, about anyone."""
    sources = _bot("ru") | _app("ru")
    for key in NEW:
        value = sources.get(key, "")
        assert "(а)" not in value, key
        for gendered in ("отметил ", "отметила", "дал ", "дала ", "сам ", "сама "):
            assert gendered not in value, (key, gendered)


def test_the_teacher_fallback_works_in_the_colon_form() -> None:
    """ "Marked by a teacher." / «Отметка: учитель.» (Q9)."""
    teacher_en = _t("en", "progression-by-teacher")
    teacher_ru = _t("ru", "progression-by-teacher")

    assert _t("en", "mark-received", asana="X", teacher=teacher_en).endswith("Marked by a teacher.")
    assert _t("ru", "mark-received", asana="X", teacher=teacher_ru).endswith("Отметка: учитель.")
