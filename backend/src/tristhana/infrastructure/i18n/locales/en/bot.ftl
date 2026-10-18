# Telegram bot messages (en). Keys must match locales/ru/bot.ftl.

start-greeting =
    Namaste 🙏
    I'm Tristhana, your Ashtanga practice companion. Glad you're here.

# Button under the /start greeting that opens the Mini App.
start-open-app = Open the app

help-text =
    I'm Tristhana, a companion for your Ashtanga practice: breath, bandha, drishti.
    /log: note how your day went (practice, rest, moon day…), today or any earlier day.

fallback-text = I can't answer messages yet. Try /start or /help 🙏

# The database is unreachable; the person should simply try again.
error-temporary = Sorry, I've hit a small hiccup on my side. Please try again in a minute 🙏

## Day status (PR-01). Dates arrive pre-formatted ("Sun, Oct 18").

# Button under the /start greeting.
start-log-today = 📝 Log today

day-label =
    { $rel ->
        [today] Today, { $date }
        [yesterday] Yesterday, { $date }
       *[other] { $date }
    }

log-prompt =
    { $day }
    How was your day?

status-practiced = 🧘 Practiced
status-rest = 😌 Rest day
status-moon = 🌙 Moon day
status-ladies = 🌸 Ladies' holiday
status-sick = 🤒 Sick / injury
status-travel = ✈️ Travel
status-skipped = 🌱 No practice

log-saved =
    ✓ { $day }: { $label }
    { $status ->
        [practiced] Practice done 🙏
        [sick] Get well soon 🌿
        [travel] Safe travels ✈️
        [skipped] Every day is different 🌱
       *[other] Rest is part of the practice 🌿
    }
log-private-note = Only you see this. Others see “Rest day”.
log-zone-hint = Tip: open the app once so I know your time zone and your days land on the right date.
log-cleared = Cleared: { $day }.
log-date-future = That day hasn't come yet in your time zone.
log-date-too-early = I keep days from the year 2000 on.

log-another-day = 📅 Another day
log-change = ✏️ Change
log-clear = Clear
log-pick-day = Which day?
log-earlier = ‹ Earlier
log-later = Later ›

## Bot command menu (setMyCommands, via tools/telegram/set_webhook.py). One line each.
command-log = Log today or an earlier day
command-help = What I can do
command-start = Start
