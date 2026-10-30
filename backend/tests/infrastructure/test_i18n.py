from importlib.resources import files

import pytest

from tristhana.domain.locale import LOCALES
from tristhana.infrastructure.i18n.fluent import FluentTranslator, message_ids

BOT_KEYS = ["start-greeting", "help-text", "fallback-text"]


def test_every_locale_has_the_same_keys() -> None:
    keys = {locale: message_ids(locale) for locale in LOCALES}

    assert keys["en"] == keys["ru"]
    assert set(BOT_KEYS) <= keys["en"]


def test_ftl_files_ship_as_package_data() -> None:
    root = files("tristhana.infrastructure.i18n") / "locales"
    for locale in LOCALES:
        assert (root / locale / "bot.ftl").is_file()


@pytest.mark.parametrize(("locale", "word"), [("en", "Namaste 🙏"), ("ru", "Намасте 🙏")])
def test_greeting_renders(locale: str, word: str) -> None:
    text = FluentTranslator().t(locale, "start-greeting")  # type: ignore[arg-type]

    assert text.startswith(word)
    assert "{" not in text


def test_unknown_key_raises() -> None:
    with pytest.raises(KeyError):
        FluentTranslator().t("en", "no-such-key")


def test_dates_are_localized_and_the_caller_decides_the_year() -> None:
    from datetime import date

    from tristhana.application.ports.i18n import DateArg

    t = FluentTranslator()
    day = date(2026, 10, 18)

    assert t.t("en", "day-label", rel="other", date=DateArg(day)) == "Sun, Oct 18"
    assert t.t("ru", "day-label", rel="today", date=DateArg(day)) == "Сегодня, вс, 18 окт."
    assert "2026" in t.t("en", "day-label", rel="other", date=DateArg(day, with_year=True))


@pytest.mark.parametrize(
    ("day", "at", "zone", "locale", "label"),
    [
        ("2026-10-19", "06:30", "Asia/Almaty", "en", "06:30 Almaty (UTC+5)"),
        ("2026-10-19", "06:30", "Asia/Almaty", "ru", "06:30 Алматы (UTC+5)"),
        ("2026-10-19", "04:30", "Asia/Kolkata", "en", "04:30 Kolkata (UTC+5:30)"),
        ("2026-10-19", "05:00", "Asia/Kathmandu", "en", "05:00 Kathmandu (UTC+5:45)"),
        ("2026-03-28", "06:30", "Europe/Berlin", "en", "06:30 Berlin (UTC+1)"),  # before DST
        ("2026-03-29", "06:30", "Europe/Berlin", "en", "06:30 Berlin (UTC+2)"),  # DST day
        ("2026-10-19", "06:30", "UTC", "en", "06:30 UTC"),
    ],
)
def test_time_labels_carry_city_and_the_offset_on_that_date(
    day: str, at: str, zone: str, locale: str, label: str
) -> None:
    from datetime import date, time

    from tristhana.application.ports.i18n import TimeArg

    arg = TimeArg(date.fromisoformat(day), time.fromisoformat(at), zone)

    assert FluentTranslator().t(locale, "time-label", time=arg) == label  # type: ignore[arg-type]


# WH-01 part 2 (spec §7): new keys exist in both locales and format as written.

WH01_KEYS = [
    "pause-ask",
    "pause-days",
    "pause-other",
    "pause-back",
    "pause-set",
    "log-auto-period",
    "pause-end",
    "pause-ended",
    "pause-cut",
    "pause-keep",
    "pause-kept",
    "remind-paused-until",
    "remind-resume",
    "settings-ladies-line",
    "settings-ladies-hide",
    "settings-ladies-show",
]
RU_ASK_ON = (
    "⏸ На сколько дней приостановить напоминания о практике, включая сегодня? "  # noqa: RUF001
    "Эти дни отметятся как „🌸 Женские дни“, если не отметишь иначе."
)
RU_ASK_OFF = "Сколько дней отметить как „🌸 Женские дни“, включая вчерашний день?"
RU_PAUSED = "⏸ На паузе по чт, 29 окт. включительно"  # noqa: RUF001
EN_ASK_ON = (
    "⏸ Pause practice reminders for how many days, including today? Those days show "
    "as 🌸 Ladies' holiday unless you log something else."
)
EN_ASK_OFF = "How many days should show as 🌸 Ladies' holiday, including yesterday?"


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_wh01_keys_exist(locale: str) -> None:
    assert set(WH01_KEYS) <= message_ids(locale)  # type: ignore[arg-type]


def _t(locale: str, key: str, **args: object) -> str:
    return FluentTranslator().t(locale, key, **args)  # type: ignore[arg-type]


def _flat(locale: str, key: str, **args: object) -> str:
    return " ".join(_t(locale, key, **args).split())


def _label(locale: str, status: str) -> str:
    return _t(locale, f"status-{status}")


def _until() -> object:
    from datetime import date

    from tristhana.application.ports.i18n import DateArg

    return DateArg(date(2026, 10, 29))  # a Thursday


@pytest.mark.parametrize(
    ("locale", "reminders", "rel", "expected"),
    [
        ("en", "on", "today", EN_ASK_ON),
        ("en", "off", "yesterday", EN_ASK_OFF),
        ("ru", "on", "today", RU_ASK_ON),
        ("ru", "off", "yesterday", RU_ASK_OFF),
    ],
)
def test_pause_ask(locale: str, reminders: str, rel: str, expected: str) -> None:
    label = _label(locale, "ladies")
    assert _flat(locale, "pause-ask", label=label, rel=rel, reminders=reminders) == expected


@pytest.mark.parametrize(
    ("locale", "n", "expected"),
    [
        ("en", 2, "2 days"),
        ("en", 14, "14 days"),
        ("ru", 2, "2 дня"),
        ("ru", 3, "3 дня"),
        ("ru", 4, "4 дня"),
        ("ru", 5, "5 дней"),
        ("ru", 6, "6 дней"),
        ("ru", 7, "7 дней"),
        ("ru", 10, "10 дней"),
        ("ru", 14, "14 дней"),
    ],
)
def test_pause_days_plurals(locale: str, n: int, expected: str) -> None:
    assert _t(locale, "pause-days", n=n) == expected


@pytest.mark.parametrize(
    ("locale", "reminders", "expected"),
    [
        ("en", "on", "⏹ End the pause"),
        ("en", "off", "⏹ End early"),
        ("ru", "on", "⏹ Завершить паузу"),
        ("ru", "off", "⏹ Закончить раньше"),
    ],
)
def test_pause_end_label_follows_the_reminders(locale: str, reminders: str, expected: str) -> None:
    assert _t(locale, "pause-end", reminders=reminders) == expected


def test_pause_set_and_ended_have_reminders_off_variants() -> None:
    label = _label("en", "sick")
    assert _flat("en", "pause-set", label=label, until=_until(), reminders="on") == (
        "⏸ Practice reminders are paused through Thu, Oct 29. Those days show as "
        "🤒 Sick / injury; you can log any day differently."
    )
    assert _flat("en", "pause-set", label=label, until=_until(), reminders="off") == (
        "⏸ Set through Thu, Oct 29. Those days show as 🤒 Sick / injury; you can log any day "
        "differently."
    )
    assert _t("en", "pause-ended", label=label, reminders="on") == (
        "▶️ Practice reminders are back from today."
    )
    assert _t("en", "pause-ended", label=label, reminders="off") == (
        "⏹ Done: from today on, days no longer show as 🤒 Sick / injury."
    )


def test_pause_cut_and_kept_name_the_period_gently() -> None:
    en, ru = _label("en", "sick"), _label("ru", "sick")
    assert _flat("en", "pause-cut", label=en, until=_until(), rel="today") == (
        "⏸ Practice logged for today, so the following days, through Thu, Oct 29, "
        "no longer show as 🤒 Sick / injury. Keep them as they were?"
    )
    assert "yesterday" in _t("en", "pause-cut", label=en, until=_until(), rel="yesterday")
    assert "на вчера" in _t("ru", "pause-cut", label=ru, until=_until(), rel="yesterday")
    assert _t("en", "pause-kept", label=en, until=_until()) == (
        "⏸ Pause kept: 🤒 Sick / injury through Thu, Oct 29."
    )
    assert _t("ru", "pause-kept", label=ru, until=_until()) == (
        "⏸ Пауза сохранена: „🤒 Болезнь / травма“ по чт, 29 окт. включительно."
    )
    for locale, label in (("en", en), ("ru", ru)):
        text = _t(locale, "pause-cut", label=label, until=_until(), rel="today").lower()
        assert "missed" not in text
        assert "пропущ" not in text


def test_period_line_paused_line_and_settings_line() -> None:
    travel = _label("en", "travel")
    assert _flat("en", "log-auto-period", label=travel, until=_until()) == (
        "✈️ Travel through Thu, Oct 29. If the day went differently, log it below."
    )
    assert _t("ru", "remind-paused-until", until=_until()) == RU_PAUSED
    assert _t("en", "remind-resume") == "▶️ Resume now"
    assert _t("ru", "settings-ladies-line", shown="yes") == "🌸 Кнопка „Женские дни“: показана"
    assert _t("en", "settings-ladies-line", shown="no") == "🌸 Ladies' holiday button: hidden"
    assert (_t("en", "settings-ladies-hide"), _t("en", "settings-ladies-show")) == (
        "🌸 Hide the button",
        "🌸 Show the button",
    )


# PR-06 (spec §6): the check-in copy exists in both locales, formats as written, every tag
# has a label, and the copy avoids judging words.

PR06_KEYS = [
    "checkin-prompt",
    "checkin-explain",
    "checkin-mood-chip",
    "checkin-energy-chip",
    "checkin-effort-chip",
    "checkin-summary-energy",
    "checkin-summary-effort",
    "checkin-edit",
    "checkin-tags-open",
    "checkin-tags-pick",
    "checkin-clear",
    "checkin-tag",
    "settings-checkin-line",
    "settings-checkin-off",
    "settings-checkin-on",
]
TAG_LABELS = {
    "stiff": ("Stiff", "Скованность"),
    "open": ("Open", "Раскрытость"),
    "strong": ("Strong", "Сила"),
    "light": ("Light", "Лёгкость"),
    "heavy": ("Heavy", "Тяжесть"),
    "sore": ("Sore muscles", "Ноющие мышцы"),
    "focused": ("Focused", "Собранность"),
    "calm": ("Calm", "Спокойствие"),
    "scattered": ("Scattered", "Рассеянность"),
    "steady_breath": ("Steady breath", "Ровное дыхание"),
}
AVOID = [
    "missed",
    "forgot",
    "bad",
    "pain",
    "push",
    "should",
    "only",
    "again",
    "streak",
    "recovery",
    "training load",
    "плохо",
    "пропустил",
    "боль",
    "надо",
    "всего лишь",
    "опять",
]


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_pr06_keys_exist(locale: str) -> None:
    assert set(PR06_KEYS) - message_ids(locale) == set()  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("locale", "key", "text"),
    [
        ("en", "checkin-prompt", "How do you feel after practice? Optional."),
        ("ru", "checkin-prompt", "Как ты после практики? По желанию."),
        (
            "en",
            "checkin-explain",
            "⚡ Energy: 1 low → 5 high · 🔥 Effort: 1 easy → 5 hard. Tap what fits, all optional.",
        ),
        (
            "ru",
            "checkin-explain",
            "⚡ Энергия: 1 мало → 5 много · 🔥 Усилие: 1 легко → 5 тяжело. "
            "Отметь, что подходит, всё по желанию.",
        ),
        ("en", "checkin-edit", "✨ Check-in"),
        ("ru", "checkin-edit", "✨ Самочувствие"),
        ("en", "checkin-tags-open", "🏷 Body and mind…"),
        ("ru", "checkin-tags-open", "🏷 Тело и ум…"),
        ("en", "checkin-tags-pick", "How did body and mind feel? Pick any."),
        ("ru", "checkin-tags-pick", "Как тело и ум? Отметь, что подходит."),
        ("en", "checkin-clear", "Remove check-in"),
        ("ru", "checkin-clear", "Убрать самочувствие"),
        ("en", "settings-checkin-off", "✨ Don't offer"),
        ("ru", "settings-checkin-off", "✨ Не предлагать"),  # noqa: RUF001
        ("en", "settings-checkin-on", "✨ Offer"),
        ("ru", "settings-checkin-on", "✨ Предлагать"),
    ],
)
def test_pr06_copy_reads_as_written(locale: str, key: str, text: str) -> None:
    assert _flat(locale, key) == text


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_mood_energy_and_effort_chips(locale: str) -> None:
    assert [_t(locale, "checkin-mood-chip", n=n) for n in range(1, 6)] == [
        "😔",
        "😕",
        "😐",
        "🙂",
        "😊",
    ]
    assert _t(locale, "checkin-energy-chip", n=4) == "⚡4"
    assert _t(locale, "checkin-effort-chip", n=2) == "🔥2"


def test_summary_parts_are_plural_free() -> None:
    assert _t("en", "checkin-summary-energy", n=4) == "⚡ energy 4/5"
    assert _t("ru", "checkin-summary-energy", n=1) == "⚡ энергия 1/5"
    assert _t("en", "checkin-summary-effort", n=3) == "🔥 effort 3/5"
    assert _t("ru", "checkin-summary-effort", n=5) == "🔥 усилие 5/5"


def test_settings_line_says_offered_or_not() -> None:
    assert _t("en", "settings-checkin-line", offered="yes") == "✨ Check-in after practice: offered"
    assert _t("en", "settings-checkin-line", offered="no") == (
        "✨ Check-in after practice: not offered"
    )
    assert _t("ru", "settings-checkin-line", offered="yes") == (
        "✨ Самочувствие после практики: предлагаю"
    )
    assert _t("ru", "settings-checkin-line", offered="no") == (
        "✨ Самочувствие после практики: не предлагаю"
    )


def test_every_tag_has_a_label_in_both_locales() -> None:
    from tristhana.domain.check_in import CheckInTag

    assert [t.value for t in CheckInTag] == list(TAG_LABELS)
    for tag in CheckInTag:
        en, ru = TAG_LABELS[tag.value]
        assert _t("en", "checkin-tag", tag=tag.value) == en
        assert _t("ru", "checkin-tag", tag=tag.value) == ru


def _check_in_sources(locale: str) -> dict[str, str]:
    """The source of every `checkin-*` / `settings-checkin*` message (all variants)."""
    from fluent.syntax import FluentParser, FluentSerializer, ast

    root = files("tristhana.infrastructure.i18n") / "locales" / locale / "bot.ftl"
    parsed = FluentParser().parse(root.read_text(encoding="utf-8"))
    return {
        e.id.name: FluentSerializer().serialize_entry(e)
        for e in parsed.body
        if isinstance(e, ast.Message)
        and (e.id.name.startswith("checkin-") or e.id.name.startswith("settings-checkin"))
    }


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_check_in_copy_avoids_judging_words(locale: str) -> None:
    import re

    sources = _check_in_sources(locale)
    assert set(PR06_KEYS) <= set(sources)
    found = {
        (key, word)
        for key, source in sources.items()
        for word in AVOID
        if re.search(rf"\b{re.escape(word)}", source.split("=", 1)[1], re.IGNORECASE)
    }

    assert found == set()


# PR-07 (spec §6): the diary copy exists in both locales, formats as written (the prompt in
# RU with today / yesterday / another day), the length is a number with no plural forms, and
# the copy avoids judging words (PR-06's list plus the diary's own).

PR07_KEYS = [
    "diary-button",
    "diary-empty",
    "diary-prompt",
    "diary-prompt-replace",
    "diary-placeholder",
    "diary-saved",
    "diary-write",
    "diary-rewrite",
    "diary-clear",
    "diary-clear-confirm",
    "diary-clear-yes",
    "diary-removed",
    "diary-too-long",
    "diary-text-only",
    "diary-unreadable",
    "diary-preview",
]
DIARY_AVOID = [
    *AVOID,
    "journal",
    "wrong",
    "mistake",
    "fail",
    "improve",
    "progress",
    "goal",
    "performance",
    "achieve",
    "lazy",
    "excuse",
    "keep up",
    "don't forget",
    "remember to",
    "every day",
    "habit",
    "журнал",
    "ошибк",
    "неудач",
    "прогресс",
    "цель",
    "результат",
    "лень",
    "оправдан",
    "не забудь",
    "каждый день",
    "привычк",
    "должен",
    "должна",
]


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_pr07_keys_exist(locale: str) -> None:
    assert set(PR07_KEYS) - message_ids(locale) == set()  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("locale", "key", "text"),
    [
        ("en", "diary-button", "📓 Note"),
        ("ru", "diary-button", "📓 Заметка"),
        (
            "en",
            "diary-empty",
            "No note for this day. Write anything you'd like to keep: how the practice felt, "
            "what your teacher said, a new asana, or just a thought.",
        ),
        (
            "ru",
            "diary-empty",
            "Заметки за этот день нет. Можно записать что угодно: как прошла практика, что "
            "сказал преподаватель, новая асана или просто мысль.",
        ),
        (
            "en",
            "diary-prompt-replace",
            "It will replace the current note. Copy the note above to edit it.",
        ),
        (
            "ru",
            "diary-prompt-replace",
            "Она заменит текущую. Текст заметки выше можно скопировать и поправить.",
        ),
        ("en", "diary-placeholder", "Your note…"),
        ("ru", "diary-placeholder", "Твоя заметка…"),
        ("en", "diary-saved", "📓 Saved to your diary."),
        ("ru", "diary-saved", "📓 Сохранено в дневнике."),
        ("en", "diary-write", "✏️ Write"),
        ("ru", "diary-write", "✏️ Написать"),
        ("en", "diary-rewrite", "✏️ Rewrite"),
        ("ru", "diary-rewrite", "✏️ Переписать"),
        ("en", "diary-clear", "Remove note"),
        ("ru", "diary-clear", "Удалить заметку"),
        ("en", "diary-clear-confirm", "Remove this note?"),
        ("ru", "diary-clear-confirm", "Удалить заметку?"),
        ("en", "diary-clear-yes", "Remove"),
        ("ru", "diary-clear-yes", "Удалить"),
        (
            "en",
            "diary-removed",
            "Removed from your diary. Earlier messages in this chat stay until you delete them.",
        ),
        (
            "ru",
            "diary-removed",
            "Заметка удалена из дневника. Сообщения выше в чате остаются, их можно удалить "
            "в Telegram.",
        ),
        (
            "en",
            "diary-text-only",
            "Notes are text for now. Type your note as a reply to the prompt above.",
        ),
        (
            "ru",
            "diary-text-only",
            "Пока заметки бывают только текстом. Напиши её ответом на сообщение выше.",
        ),
        (
            "en",
            "diary-unreadable",
            "This note can't be read right now. You can write a new one or remove it.",
        ),
        (
            "ru",
            "diary-unreadable",
            "Эту заметку сейчас не получается прочитать. Можно написать новую или удалить старую.",
        ),
    ],
)
def test_pr07_copy_reads_as_written(locale: str, key: str, text: str) -> None:
    assert _flat(locale, key) == text


def _day(iso: str) -> object:
    from datetime import date

    from tristhana.application.ports.i18n import DateArg

    return DateArg(date.fromisoformat(iso))


@pytest.mark.parametrize(
    ("locale", "rel", "expected"),
    [
        (
            "en",
            "today",
            "Write your note for today as a reply to this message. It's private, just for you.",
        ),
        (
            "en",
            "yesterday",
            "Write your note for yesterday as a reply to this message. It's private, just for you.",
        ),
        (
            "en",
            "other",
            "Write your note for Tue, Oct 27 as a reply to this message. It's private, just for "
            "you.",
        ),
        (
            "ru",
            "today",
            "Напиши заметку за сегодня в ответ на это сообщение. Она личная, только для тебя.",
        ),
        (
            "ru",
            "yesterday",
            "Напиши заметку за вчера в ответ на это сообщение. Она личная, только для тебя.",
        ),
        (
            "ru",
            "other",
            "Напиши заметку за вт, 27 окт. в ответ на это сообщение. Она личная, только для тебя.",
        ),
    ],
)
def test_the_prompt_names_the_day(locale: str, rel: str, expected: str) -> None:
    # `rel` + `date` as in `day-label` (the spec's `$day`): RU needs «за сегодня», not
    # «за Сегодня, вт, 27 окт.».
    assert _flat(locale, "diary-prompt", rel=rel, date=_day("2026-10-27")) == expected


def test_too_long_names_the_limit_as_a_number() -> None:
    assert _flat("en", "diary-too-long", max=2000) == (
        "That's a bit long for one note: up to 2,000 characters. Your text is still above, "
        "so you can shorten it and resend."
    )
    assert _flat("ru", "diary-too-long", max=2000) == (
        # _flat turns the NBSP group separator into a space.
        "Для одной заметки длинновато: до 2 000 символов. Текст остался выше, можно "
        "сократить и отправить снова."
    )


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_the_preview_is_the_text_after_the_icon(locale: str) -> None:
    assert _t(locale, "diary-preview", text="Felt light…") == "📓 Felt light…"


def _diary_sources(locale: str) -> dict[str, str]:
    """The source (every variant) of each `diary-*` message, value only."""
    from fluent.syntax import FluentParser, FluentSerializer, ast

    root = files("tristhana.infrastructure.i18n") / "locales" / locale / "bot.ftl"
    parsed = FluentParser().parse(root.read_text(encoding="utf-8"))
    return {
        e.id.name: FluentSerializer().serialize_entry(e).split("=", 1)[1]
        for e in parsed.body
        if isinstance(e, ast.Message) and e.id.name.startswith("diary-")
    }


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_diary_copy_avoids_judging_words(locale: str) -> None:
    import re

    sources = _diary_sources(locale)
    assert set(PR07_KEYS) <= set(sources)
    found = {
        (key, word)
        for key, source in sources.items()
        for word in DIARY_AVOID
        if re.search(rf"(?<![\w']){re.escape(word)}", source, re.IGNORECASE)
    }

    assert found == set()


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_an_absent_note_is_never_nudged(locale: str) -> None:
    # The quiet entry points: no "yet" / «пока», no question marks, no counts.
    sources = _diary_sources(locale)
    for key in ("diary-button", "diary-empty", "diary-write"):
        text = sources[key].lower()
        assert "?" not in text, key
        assert "yet" not in text, key
        assert "пока" not in text, key
        assert not any(ch.isdigit() for ch in text), key


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_the_diary_icon_is_the_notebook(locale: str) -> None:
    sources = _diary_sources(locale)
    joined = " ".join(sources.values())
    assert "📓" in sources["diary-button"]
    for icon in ("📝", "📖", "🪷", "🙏", "🌸", "🌺", "🌼", "🌷"):
        assert icon not in joined, icon


def test_russian_diary_copy_has_no_gendered_past_tense_for_the_reader() -> None:
    import re

    for key, source in _diary_sources("ru").items():
        assert "(а)" not in source, key  # noqa: RUF001
        assert not re.search(r"\bты\s+\w+л[аи]?\b", source, re.IGNORECASE), key


# PR-08: progression and celebration copy stays gentle and non-competitive (spec §7).
_AVOID = {
    "en": (
        "unlock", "level", "achieve", "earn", "finally", "behind", "lost", "regress",
        "back to", "demote", "only", "again", "streak", "rank", "goal", "should", "faster",
    ),
    "ru": (
        "уровень", "достижен", "разблок", "наконец", "откат", "потер", "отстал", "только",
        "опять", "цель", "надо", "должен",
    ),
}  # fmt: skip


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_progression_copy_avoids_competitive_or_guilty_words(locale: str) -> None:
    text = (files("tristhana.infrastructure.i18n") / "locales" / locale / "bot.ftl").read_text(
        encoding="utf-8"
    )
    section = text.split("(PR-08)", 1)[1].split("(ST-09)", 1)[0]  # the progression section
    lines = [
        line.split("=", 1)[-1].lower()
        for line in section.splitlines()[1:]
        if line.strip() and not line.startswith("#") and not line.startswith("command-")
    ]
    assert len(lines) > 30
    for word in _AVOID[locale]:
        assert not [line for line in lines if word in line], word


# GM-01 part 2 (spec §7): a count is a thank-you, never a score, and 365 is never "a year"
# or daily practice (rest days are part of the method). On top of `_AVOID`.
_AVOID_COUNT = {
    "en": (
        "record", "best", "total", "in a row", "left", "until", "badge", "year", "daily",
        "every day", "keep",
    ),
    "ru": (
        "рекорд", "лучш", "подряд", "осталось", "до цели", "значок", "год", "ежедневн",
        "каждый день", "продолжай", "так держать",
    ),
}  # fmt: skip


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_practice_count_copy_avoids_scores_and_years(locale: str) -> None:
    from tristhana.infrastructure.i18n.fluent import FluentTranslator

    t = FluentTranslator()
    for n in (100, 365, 1000):
        line = t.t(locale, "celebrate-practice-count", count=n).lower()  # type: ignore[arg-type]
        assert str(n)[0] in line
        for word in (*_AVOID[locale], *_AVOID_COUNT[locale]):
            assert word not in line, (n, word)


# ST-09 (spec §9): no sadness, retention nudges, "are you sure?", banned progression words, or
# "skipped" anywhere in the export/delete copy and the README.
_DATA_AVOID = {
    "en": ("sad", "miss you", "sure?", "unlocked", "level up", "skipped"),
    "ru": ("жаль", "уверен", "открыта серия", "пропуск", "скучать"),
}


def _data_section(locale: str) -> dict[str, str]:
    text = (files("tristhana.infrastructure.i18n") / "locales" / locale / "bot.ftl").read_text(
        encoding="utf-8"
    )
    section = text.split("(ST-09)", 1)[1]
    messages: dict[str, str] = {}
    key = ""
    for line in section.splitlines()[1:]:
        if not line.strip() or line.startswith("#"):
            continue
        if not line.startswith(" ") and "=" in line:
            key, value = line.split("=", 1)
            key = key.strip()
            messages[key] = value.strip()
        elif key:
            messages[key] += "\n" + line.strip()
    return messages


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_my_data_copy_avoids_guilt_nudges_and_banned_words(locale: str) -> None:
    messages = _data_section(locale)
    assert len(messages) > 30
    for word in _DATA_AVOID[locale]:
        assert not [k for k, v in messages.items() if word in v.lower()], word


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_export_sent_never_names_ladies_holiday_in_the_chat(locale: str) -> None:
    sent = _data_section(locale)["export-sent"]

    assert "🌸" not in sent
    assert "ladies" not in sent.lower()
    assert "женск" not in sent.lower()


def test_ru_my_data_copy_is_gender_neutral() -> None:
    """No past-tense verbs with a gender ending addressed to the person («удалил(а)»)."""  # noqa: RUF002
    for key, value in _data_section("ru").items():
        for word in value.replace("\n", " ").split():
            stripped = word.strip(".,:;!?«»()").lower()
            assert not stripped.endswith("(а)"), (key, word)  # noqa: RUF001
        assert "ты удалил" not in value, key
        assert "ты скачал" not in value, key
