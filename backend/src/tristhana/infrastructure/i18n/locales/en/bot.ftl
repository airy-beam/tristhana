# Telegram bot messages (en). Keys must match locales/ru/bot.ftl.

start-greeting =
    Namaste 🙏
    I'm Tristhana, your Ashtanga practice companion. Glad you're here.

start-prompt =
    { $day }
    Practice or rest? Both go in your log.
# The other-language button; $language is that language's own name ("Русский").
start-switch-language = 🗣 { $language }
# Mini App button: under /start and under a saved day while the time zone is unknown.
start-open-app = Open the app

help-text =
    I'm Tristhana, a companion for your Ashtanga practice.
    📝 /log: today or an earlier day
    🔔 /remind: daily practice reminder
    🌙 /moon: upcoming moon days and reminders
    ⚙️ /settings: language, time zone, reminders
    📊 Your practice log and stats live in the app (the button next to the message field).

fallback-text = I can't answer messages yet. Try /start or /help 🙏

# The database is unreachable; the person should simply try again.
error-temporary = Sorry, I've hit a small hiccup on my side. Please try again in a minute.

## Day status (PR-01). Dates arrive pre-formatted ("Sun, Oct 18").


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
log-cleared = Cleared.
log-date-future = That day hasn't come yet in your time zone.
log-date-too-early = I keep days from 2000 onwards.

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

length-pick =
    Where did your practice end?
    ☀️ Short: Surya Namaskara, standing and finishing.
preset-short = ☀️ Short → standing
preset-half-primary = ½ Primary → Navasana
preset-full-primary = Full Primary
preset-other = 🎯 Other…
length-pick-series = Which series did you end with?
length-pick-range = What did you practice?
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

## Moon days and reminders (MD-03). City names come from data/seed/cities.yaml.

command-moon = Moon days and reminders
moon-title = 🌙 Moon days · 📍 { $city }
moon-phase =
    { $phase ->
        [purnima] 🌕 Full moon
       *[amavasya] 🌑 New moon
    }
moon-phase-lower =
    { $phase ->
        [purnima] 🌕 full moon
       *[amavasya] 🌑 new moon
    }
moon-phase-long =
    { $phase ->
        [purnima] 🌕 Full moon (Purnima)
       *[amavasya] 🌑 New moon (Amavasya)
    }
moon-in-days =
    { $n ->
        [0] today
        [1] tomorrow
        [one] in { $n } day
       *[other] in { $n } days
    }
moon-day-line = { $phase } · { $date } · { $in }
moon-none = No moon days in the next two months yet: the calendar is being prepared.
moon-calc-note = Dates are calculated for 📍 { $city } (lunar day at sunrise). Your shala's calendar may differ by a day; follow your teacher.
moon-offsets =
    { $code ->
        [731] 7, 3 and 1 day
        [71] 7 and 1 day
        [73] 7 and 3 days
        [31] 3 and 1 day
        [7] 7 days
        [3] 3 days
       *[1] 1 day
    }
moon-reminders-on = 🔔 Reminders: { $offsets } before at { $time }
moon-reminders-off = 🔕 Reminders are off
moon-zone-needed = To remind you at the right hour I need your time zone: pick your city or open the app once.
moon-change-city = 📍 Change city
moon-reminders = 🔔 Reminders
moon-pick-city = Which city's moon days do you follow?
# Full-width button: sets the account's time zone to the city's (only when unknown).
moon-use-city-zone = 🕐 Time zone: 📍 { $city }
# Toggle buttons, 3 per row; the screen text above already says "… before".
moon-offset =
    { $n ->
        [one] { $n } day
       *[other] { $n } days
    }
moon-turn-on = 🔔 Turn on
moon-turn-off = 🔕 Turn off
moon-only-day-before = Only the day before
moon-all-days = 🌙 All moon days
moon-turn-back-on = 🔔 Turn back on
moon-reminder =
    { $days ->
        [7] { $phase } in a week: { $date } · 📍 { $city }
        [3] { $phase } in 3 days: { $date } · 📍 { $city }. A traditional rest day.
       *[1] { $phase } tomorrow, { $date } · 📍 { $city }. Enjoy your rest 🌿
    }
moon-reminder-intro = In Ashtanga we traditionally rest on full and new moon days. I'll remind you { $offsets } before; one tap below changes it.
moon-reminder-only-1 = ✓ I'll only remind you the day before.
moon-reminder-off = 🔕 Moon reminders are off. You can turn them back on in /moon.
moon-reminder-on = 🔔 Moon reminders are on again.

## Practice reminder (PR-10). { $day } and { $date } arrive formatted ("Mon, Oct 19"); { $d } is an ISO weekday (1 = Monday).
command-remind = Daily practice reminder
remind-practice = 🌿 { $day }: practice or rest? One tap to log it.
remind-same = ✅ Practiced, same as last time
remind-practiced = 🧘 Practiced…
remind-other = 📅 Other…
remind-turn-off = 🔕 Turn off
remind-turn-on = 🔔 Turn on
remind-turn-back-on = 🔔 Turn back on
remind-off-note = 🔕 Practice reminders are off. You can turn them back on in /remind.
remind-on-again = 🔔 Practice reminders are on again.
# After 10 reminders in a row with nothing logged: one note, then reminders turn off.
remind-paused = 🌿 I'll stop asking for now. Whenever you'd like the daily prompt back, tap below or open /remind.
remind-copied-from = Copied from { $date }.
remind-offer = 🔔 Want me to ask once a day, so logging takes one tap?
remind-offer-yes = 🔔 Yes, remind me
remind-offer-no = No, thanks
remind-explain = Once a day I'll ask how it went, with one-tap buttons. Not on moon days or days you've already logged.
remind-status-on = 🔔 Practice reminder: { $days } at { $time }
remind-status-off = 🔕 Practice reminder is off
remind-local-time = { $time } your time
remind-every-day = every day
remind-days-except = every day except { remind-weekday-except }
remind-weekday-except = { $d ->
        [1] Monday
        [2] Tuesday
        [3] Wednesday
        [4] Thursday
        [5] Friday
        [6] Saturday
       *[7] Sunday
    }
remind-weekday = { $d ->
        [1] Mon
        [2] Tue
        [3] Wed
        [4] Thu
        [5] Fri
        [6] Sat
       *[7] Sun
    }
remind-day-off = Day off: { remind-weekday }
remind-moon-link = 🌙 Moon reminders
remind-practice-link = 🧘 Practice reminder

## Settings (ID-06).
command-settings = Language, time zone, reminders
settings-title = ⚙️ Settings
language-auto = As in Telegram
language-en = English
language-ru = Русский
settings-language-line = 🗣 Language: { $language }
settings-zone-line = 🕐 Time zone: { $zone }
settings-zone-unset-line = 🕐 Time zone: not set yet. Reminders start once it's set.
settings-moon-line = 🌙 Moon days: 📍 { $city }
settings-quiet-line = 🔕 Quiet hours { $start }–{ $end } · { $n ->
        [one] at most { $n } message a day
       *[other] at most { $n } messages a day
    }
settings-quiet-off-line = 🔕 No quiet hours · { $n ->
        [one] at most { $n } message a day
       *[other] at most { $n } messages a day
    }
settings-zone-button = 🕐 Time zone
settings-moon-link = 🌙 Moon days
settings-pick-zone = Pick the city whose time you live by. Not in the list? Open the app: it can use your phone's zone.
settings-open-app = ⚙️ More in the app
settings-link = ⚙️ Settings
