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

## Practice details (PR-02, PR-03, PR-05). Asana names come from the catalog, not from here.

practice-details-prompt = Add details? Optional, one tap is enough.
practice-last-time = Last time: { $summary }
practice-same-as-last = 🔁 Same as last time
context-mysore = Mysore
context-led = Led
context-private = 1:1
context-self = Self-practice
practice-online = 🌐 Online
practice-online-suffix = online
practice-length = 📏 Length
practice-duration = ⏱ Duration
practice-done = ✓ Done
practice-details = 📝 Details
practice-clear = Remove details
practice-day-not-practiced = This day isn't marked as practice anymore.
practice-no-previous = Nothing to copy yet: this is your first practice with details.

length-pick = Where did your practice end?
preset-short = ☀️ Short: sun salutations, standing, finishing
preset-half-primary = ½ Primary → Navasana
preset-full-primary = Full Primary
preset-other = 🎯 Other…
length-pick-series = Which series did you end with?
length-pick-range = What did you practise?
length-only = Only { $series }
length-pick-asana = Last asana in { $series }:
length-full-series = Full series
log-back = ‹ Back

duration-pick = How long was it?
duration-min = { $min } min
duration-none = No duration

# Series names: `series-name` starts a phrase, `series-lower` continues one,
# `series-half` follows "½" (RU genitive).
series-name =
    { $n ->
        [1] Primary
        [2] Intermediate
        [3] Advanced A
        [4] Advanced B
        [5] Advanced C
       *[6] Advanced D
    }
series-lower =
    { $n ->
        [1] Primary
        [2] Intermediate
        [3] Advanced A
        [4] Advanced B
        [5] Advanced C
       *[6] Advanced D
    }
series-half =
    { $n ->
        [1] Primary
        [2] Intermediate
        [3] Advanced A
        [4] Advanced B
        [5] Advanced C
       *[6] Advanced D
    }
half-first = { $series }, 1st half
half-second = { $series }, 2nd half

length-summary =
    { $kind ->
        [short] Short practice
        [full-one] Full { $range }
        [full] { $range } (full)
       *[to] { $range } → { $asana }
    }

time-label = { $time }

# Paging in the asana grid.
page-prev = ◀
page-next = ▶
