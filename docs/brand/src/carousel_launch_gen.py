"""Instagram carousel for the public launch: 20 slides, 1080x1350 (4:5), Russian and English.

Usage: python3 carousel_launch_gen.py OUT_DIR [ru|en]
Writes the slide sources to a temporary folder and renders tristhana_carousel_launch_<lang>_<NN>.png
into OUT_DIR with ../render.sh (headless Chrome). The screenshots are the guide's own
(site/src/assets/shots/<lang>/), so run `npm run shots` in site/ first if the product changed.
To change a text, edit SLIDES below and run the script again. The caption is in ../launch.md.

promo_shots/<lang>/ holds two screens shot with the product's own "hide the 🌸 button" setting
on (bot-start, app-home): public posts do not show that button (owner's rule for public
material). To re-shoot them: in site/shots/lib/seed.mjs add `hide_ladies: true` to the
`PATCH /me` call, in site/shots/manifest.yaml set bot-start to `as: student`, run
`npm run shots -- --only bot-start` and `-- --only app-home`, copy the four .webp files here,
then `git checkout` the two pipeline files and site/src/assets/shots.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHOTS = HERE.parents[2] / "site/src/assets/shots"
PROMO = HERE / "promo_shots"  # screens shot specially for promo; they win over the guide's
MARK = (HERE / "mark.svg.part").read_text().strip()
CSS = (HERE / "style.css").as_uri()
TAG = {"ru": "Асана · Дыхание · Дришти", "en": "Asana · Breath · Drishti"}

# Each slide: kind ("shot" | "cover" | "cards" | "end"), kicker, title, lead, then
# shot = (screenshot name, pixels to skip from its top) or cards = [(title, text), ...].
S, C = "shot", "cards"
SLIDES = {
    "ru": [
        ("cover", "Открыто для всех", "Спутник твоей практики аштанги",
         "Журнал практики и&nbsp;отдыха, лунные дни, учителя и&nbsp;шалы — прямо в&nbsp;Telegram.", ("app-home", 0)),
        (S, "Практикующим", "Отметить день — одно касание",
         "Практика или отдых: в&nbsp;журнал идёт и&nbsp;то, и&nbsp;другое. Прошедший день тоже можно отметить.", ("bot-start", 0)),
        (S, "Практикующим", "Детали — только если хочется",
         "Майсор, лед-класс, индивидуально или самостоятельно. Серия до&nbsp;твоей последней асаны, длительность. Или <b>«как в&nbsp;прошлый раз»</b>.", ("bot-log-practice", 0)),
        (S, "Практикующим", "Отдых — часть практики",
         "День отдыха, лунный день, болезнь, дорога: у&nbsp;каждого своя отметка. На&nbsp;несколько дней можно поставить паузу.", ("bot-pause", 0)),
        (S, "Практикующим", "Лунные дни для твоего города",
         "Полнолуние и&nbsp;новолуние — по&nbsp;лунным суткам на&nbsp;восходе в&nbsp;твоём городе. Бот напомнит заранее.", ("bot-moon", 0)),
        (S, "Практикующим", "Напоминание в&nbsp;удобное время",
         "По&nbsp;желанию: раз в&nbsp;день, только в&nbsp;дни практики. Ответить можно одним нажатием. В&nbsp;лунные дни оно не&nbsp;приходит.", ("bot-remind", 0)),
        (S, "Практикующим", "Твой год и&nbsp;твой месяц",
         "Календарь года, практики подряд и&nbsp;итоги месяца. Отдых и&nbsp;лунные дни счёт не&nbsp;сбрасывают. Никаких соревнований.", ("app-my-practice", 0)),
        (S, "Практикующим", "Самочувствие за&nbsp;год",
         "После практики можно отметить настроение, энергию и&nbsp;усилие. Средние по&nbsp;месяцам и&nbsp;дням недели видишь только ты.", ("app-trends", 0)),
        (S, "Практикующим", "Мои асаны",
         "Последняя асана и&nbsp;путь по&nbsp;сериям: когда пришла новая асана и&nbsp;что было до&nbsp;неё.", ("app-my-asanas", 0)),
        (S, "Практикующим", "Значки и&nbsp;карточки",
         "Тихие вехи на&nbsp;пути: первая практика, сто практик, практика до&nbsp;рассвета. Месяц или год можно превратить в&nbsp;карточку и&nbsp;поделиться.", ("app-badges", 0)),
        (S, "Практикующим", "Заметка к&nbsp;дню",
         "Пара строк о&nbsp;практике, для себя. Заметки хранятся зашифрованными, и&nbsp;никто, кроме тебя, их не&nbsp;видит.", ("bot-note", 0)),
        (S, "Учителям", "Ученики — по&nbsp;твоей ссылке",
         "Отдельного аккаунта учителя нет. Поделись ссылкой или QR-кодом: каждый ученик подтверждает сам.", ("bot-invite", 0)),
        (S, "Учителям", "Что видит учитель",
         "Имя, практика или отдых за&nbsp;последние 7&nbsp;дней, объём практики и&nbsp;последняя асана. Заметки, самочувствие и&nbsp;причина отдыха — никогда.", ("app-student-card", 0)),
        (S, "Учителям", "Новая асана для ученика",
         "Отметь её в&nbsp;карточке ученика: ему придёт короткое сообщение&nbsp;🎉. Журнал остаётся за&nbsp;учеником: отметку он может отменить.", ("bot-mark-asana", 0)),
        (S, "Шалам", "Шала и&nbsp;её расписание",
         "Майсор, лед-классы и&nbsp;другие занятия по&nbsp;дням недели. Закрытые дни, переносы из-за лунных дней и&nbsp;замены преподавателя.", ("app-shala", 0)),
        (S, "Шалам", "Каждый видит своё время",
         "<b>Моё расписание</b> собирает занятия всех твоих шал в&nbsp;твоём часовом поясе. Их можно добавить в&nbsp;календарь телефона.", ("app-schedule", 0)),
        (S, "Шалам", "Посещения занятий",
         "Ученик отмечается сам, или отмечает команда шалы. Это отдельно от&nbsp;личного журнала, а&nbsp;списка отсутствующих нет.", ("bot-attendance", 0)),
        (C, "Шалам и&nbsp;учителям", "Объявления", "Короткое сообщение от&nbsp;бота — всем сразу.", [
            ("🏛 Всем в&nbsp;шале", "Ученикам и&nbsp;команде: занятие отменили, приехал учитель, шала закрыта."),
            ("👥 Всем своим ученикам", "Учитель пишет один раз — получают все, кто его добавил."),
            ("📌 Закрепить", "Объявление можно закрепить в&nbsp;приложении на&nbsp;неделю или на&nbsp;месяц."),
            ("🔕 Без шума", "Каждый может отключить объявления учителя или шалы у&nbsp;себя."),
        ]),
        (C, "О&nbsp;проекте", "Личное остаётся личным", "", [
            ("🔒 Только ты", "Заметки, самочувствие и&nbsp;причину отдыха видишь только ты. Заметки зашифрованы."),
            ("🤝 Только с&nbsp;согласия", "Учитель видит твою практику после того, как ты подтвердишь. Любой отдых для него выглядит одинаково."),
            ("📦 Данные — твои", "Выгрузить или удалить всё можно в&nbsp;любой момент."),
            ("🔓 Открытый код", "Лицензия AGPL-3.0: <b>github.com/airy-beam/tristhana</b>"),
        ]),
        ("end", "О&nbsp;проекте", "Бесплатно — и&nbsp;так и&nbsp;останется",
         "Некоммерческий хобби-проект для сообщества аштанги: сделан практикующим для практикующих. Без рейтингов и&nbsp;соревнований. По-русски и&nbsp;по-английски.",
         ("Как начать", "@tristhana_bot", "Справка с&nbsp;картинками: <b>tristhana.app/ru</b>",
          ["Открой <b>@tristhana_bot</b> в&nbsp;Telegram", "Нажми <b>/start</b>", "Отметь сегодняшний день: практика или отдых"])),
    ],
    "en": [
        ("cover", "Now open to all", "A companion for your Ashtanga practice",
         "A log for practice and rest, moon days, teachers and shalas, right in Telegram.", ("app-home", 0)),
        (S, "For practitioners", "Log a day in one tap",
         "Practice or rest: both go in your log. You can log an earlier day too.", ("bot-start", 0)),
        (S, "For practitioners", "Details only if you want them",
         "Mysore, Led, 1:1 or self-practice. The series up to your last asana, the duration. Or <b>“same as last time”</b>.", ("bot-log-practice", 0)),
        (S, "For practitioners", "Rest is part of the practice",
         "A rest day, a moon day, a sick day, travel: each has its own mark. You can set a pause for several days.", ("bot-pause", 0)),
        (S, "For practitioners", "Moon days for your city",
         "Full and new moon days go by the lunar day at sunrise in your city. The bot reminds you ahead of time.", ("bot-moon", 0)),
        (S, "For practitioners", "A reminder when it suits you",
         "If you want one: once a day, on practice days only. One tap answers it. It doesn't come on moon days.", ("bot-remind", 0)),
        (S, "For practitioners", "Your year and your month",
         "The year at a glance, practices in a row and the month's summary. Rest and moon days don't reset the count. No competition.", ("app-my-practice", 0)),
        (S, "For practitioners", "Check-ins over time",
         "After practice you can note mood, energy and effort. The averages by month and weekday are for your eyes only.", ("app-trends", 0)),
        (S, "For practitioners", "My asanas",
         "Your last asana and your way through the series: when each new asana arrived and what came before it.", ("app-my-asanas", 0)),
        (S, "For practitioners", "Badges, and cards to share",
         "Quiet milestones along the way: a first practice, a hundred practices, practice before dawn. Share a month or a year as a picture.", ("app-badges", 0)),
        (S, "For practitioners", "A note for the day",
         "A few lines about the practice, for yourself. Notes are stored encrypted, and nobody but you sees them.", ("bot-note", 0)),
        (S, "For teachers", "Students join by your link",
         "There is no separate teacher account. Share a link or a QR code: each student confirms for themselves.", ("bot-invite", 0)),
        (S, "For teachers", "What a teacher sees",
         "The name, practice or rest for the last 7&nbsp;days, how far the practice went and the last asana. Notes, check-ins and the reason for a rest: never.", ("app-student-card", 0)),
        (S, "For teachers", "A new asana for a student",
         "Mark it on the student's card: they get a short message&nbsp;🎉. The log stays the student's own: they can undo the mark.", ("bot-mark-asana", 0)),
        (S, "For shalas", "A shala and its schedule",
         "Mysore, Led and other classes by weekday. Closed days, classes moved for moon days and substitute teachers.", ("app-shala", 0)),
        (S, "For shalas", "Everyone sees their own time",
         "<b>My schedule</b> gathers the classes of all your shalas in your time zone. Add them to your phone's calendar.", ("app-schedule", 0)),
        (S, "For shalas", "Class attendance",
         "A student marks it, or the shala's team does. It is kept apart from the personal log, and there is no list of who was away.", ("bot-attendance", 0)),
        (C, "For shalas and teachers", "Announcements", "A short message from the bot, to everyone at once.", [
            ("🏛 Everyone in the shala", "Students and the team: a class is cancelled, a teacher is visiting, the shala is closed."),
            ("👥 All your students", "A teacher writes once, and everyone who added them gets it."),
            ("📌 Pin it", "An announcement can stay pinned in the app for a week or a month."),
            ("🔕 No noise", "Each person can mute a teacher's or a shala's announcements."),
        ]),
        (C, "About the project", "Private things stay private", "", [
            ("🔒 Only you", "Notes, check-ins and the reason for a rest stay with you. Notes are encrypted."),
            ("🤝 Only if you agree", "A teacher sees your practice after you confirm. Every rest day looks the same to them."),
            ("📦 Your data is yours", "Export or delete everything at any time."),
            ("🔓 Open source", "AGPL-3.0: <b>github.com/airy-beam/tristhana</b>"),
        ]),
        ("end", "About the project", "Free, and it will stay free",
         "A not-for-profit hobby project for the Ashtanga community: made by a practitioner for practitioners. No rankings, no competition. In English and Russian.",
         ("How to start", "@tristhana_bot", "Guide with pictures: <b>tristhana.app</b>",
          ["Open <b>@tristhana_bot</b> in Telegram", "Tap <b>/start</b>", "Log today: practice or rest"])),
    ],
}
SWIPE = {"ru": "Листай →", "en": "Swipe →"}


def page(lang: str, n: int, total: int, slide: tuple) -> str:
    kind, kicker, title, lead, extra = slide
    body = f'<div class="kicker">{kicker}</div>\n<h1>{title}</h1>\n'
    if lead:
        body += f'<p class="lead">{lead}</p>\n'
    if kind in ("shot", "cover"):
        name, skip = extra
        if kind == "cover":
            body += f'<div class="swipe">{SWIPE[lang]}</div>\n'
        own = PROMO / lang / f"{name}.webp"
        src = (own if own.exists() else SHOTS / lang / f"{name}.webp").as_uri()
        chat = " chat" if name.startswith("bot-") else ""
        body += f'<div class="shot{chat}"><img src="{src}" style="margin-top:-{skip}px" alt=""></div>\n'
    elif kind == "cards":
        cards = "\n".join(
            f'<div class="c"><div class="ct">{t}</div><div class="cd">{d}</div></div>' for t, d in extra
        )
        body += f'<div class="cards">\n{cards}\n</div>\n'
    else:  # end
        t, h, s, steps = extra
        items = "\n".join(f'<li><span class="e">{i}</span><span>{x}</span></li>' for i, x in enumerate(steps, 1))
        body += f'<ul class="list steps">\n{items}\n</ul>\n'
        body += f'<div class="cta"><div class="t">{t}</div><div class="h">{h}</div><div class="s">{s}</div></div>\n'
    cover = " cover" if kind == "cover" else ""
    return f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><link rel="stylesheet" href="{CSS}"></head>
<body><div class="slide{cover}"><div class="moon"></div>
<div class="top"><div class="mark">{MARK}
<div><div class="brand">Tristhana</div></div></div><div class="num">{n} / {total}</div></div>
{body}</div></body></html>
"""


def main() -> None:
    out = Path(sys.argv[1]).expanduser().resolve()
    langs = sys.argv[2:] or list(SLIDES)
    with tempfile.TemporaryDirectory() as tmp:
        for lang in langs:
            slides = SLIDES[lang]
            for i, slide in enumerate(slides, 1):
                src = Path(tmp) / f"{lang}_{i:02d}.html"
                src.write_text(page(lang, i, len(slides), slide))
                png = out / f"tristhana_carousel_launch_{lang}_{i:02d}.png"
                subprocess.run([str(HERE.parent / "render.sh"), str(src), str(png), "1080", "1350"], check=True, stdout=subprocess.DEVNULL)
    print(f"ok: {sum(len(SLIDES[lang]) for lang in langs)} slides in {out}")


if __name__ == "__main__":
    main()
