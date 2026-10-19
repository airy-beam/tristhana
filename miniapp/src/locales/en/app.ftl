# Mini App copy (en). Keys must match locales/ru/app.ftl. Keys are prefixed by screen.

# Home: greeting with the Telegram first name (display only).
home-greeting = Namaste, { $name } 🙏
home-greeting-anon = Namaste 🙏
home-subtitle = Your Ashtanga practice companion.

# Home: server status (dev, or after a long press on the greeting).
home-server-status = Server { $version } · { $commit }
home-server-loading = Connecting to the server…
home-server-offline = Can't reach the server right now. Your data is safe. Try again in a moment.

# Telegram main button, and its result when server details are hidden.
home-check-connection = Check connection
home-connection-ok = Connection is fine ✓

# Shown if the app fails to start (plain text, outside React).
startup-failed = Something went wrong. Please reopen Tristhana.

# Shown when the page is opened outside Telegram (in production).
not-in-telegram = Open Tristhana in Telegram: @tristhana_bot

# Plural example used by the consistency stats later (ST-03).
practice-days =
    { $count ->
        [one] { $count } day
       *[other] { $count } days
    }

# Shown when the Telegram session is older than 24 hours (or can't be verified).
session-expired = This session has expired. Close Tristhana and open it again from the bot.

# Home: today's status card (PR-01). Status labels match the bot.
home-first-hint = Start by noting today: practice or rest.
today-title = Today
status-practiced = 🧘 Practiced
status-rest = 😌 Rest day
status-moon = 🌙 Moon day
status-ladies = 🌸 Ladies' holiday
status-sick = 🤒 Sick / injury
status-travel = ✈️ Travel
status-skipped = 🌱 No practice
today-private-note = Only you see this. Others see “Rest day”.
today-clear = Clear
today-save-failed = Couldn't save. Try again in a moment.
today-load-failed = Couldn't load today's status. Try again in a moment.

# Practice details on a practiced day (PR-02, PR-03, PR-05). Matches the bot's wording.
practice-title = Practice
practice-same-as-last = 🔁 Same as last time
context-mysore = Mysore
context-led = Led
context-private = 1:1
context-self = Self-practice
practice-online = 🌐 Online
practice-length = Length
practice-duration = Duration
preset-short = ☀️ Short: sun salutations, standing, finishing
preset-half-primary = ½ Primary → Navasana
preset-full-primary = Full Primary
preset-other = 🎯 Other…
length-pick-range = Series
length-pick-end = Last asana
length-full-series = Full series
duration-min = { $min } min
duration-none = No duration
practice-start-time = Start time
practice-clear = Remove details
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
length-only = Only { $series }
length-summary =
    { $kind ->
        [short] Short practice
        [full-one] Full { $range }
        [full] { $range } (full)
       *[to] { $range } → { $asana }
    }

# Moon days (MD-03). Matches the bot's wording; city names come from the server.
moon-title = 🌙 Moon days · 📍 { $city }
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
moon-city = City for the calendar
moon-reminders-label = Remind me before
moon-offset =
    { $n ->
        [one] { $n } day
       *[other] { $n } days
    }
moon-zone-needed-app = Reminders start once your time zone is known. It's set automatically when you open the app on your phone.
moon-today =
    { $phase ->
        [purnima] 🌕 Full moon today · 📍 { $city }
       *[amavasya] 🌑 New moon today · 📍 { $city }
    }
moon-save-failed = Couldn't save. Try again in a moment.

## Practice reminder (PR-10). { $d } is an ISO weekday (1 = Monday).
remind-card-title = 🧘 Practice reminder
remind-switch = 🔔 Ask me once a day
remind-explain-app = Once a day I'll ask in the bot how it went, with one-tap buttons. Not on moon days or days you've already logged.
remind-time-label = Time · { $zone }
remind-day-off = Day off: { remind-weekday }
remind-days-label = Days
remind-weekday = { $d ->
        [1] Mon
        [2] Tue
        [3] Wed
        [4] Thu
        [5] Fri
        [6] Sat
       *[7] Sun
    }

## Stats (ST-01..03). Runs say "in a row", never "streak"/"broken"/"missed".
stats-open = 📊 My practice
stats-title = My practice
stats-year-total = { $n ->
        [one] { $n } practice in { $year }
       *[other] { $n } practices in { $year }
    }
stats-consistency = This month: practice on { $x } of { $y } days
stats-consistency-count = { $n ->
        [0] This month: no practice yet
        [one] This month: { $n } practice
       *[other] This month: { $n } practices
    }
# Shown only from 2, but kept plural-safe.
stats-run-current = { $n ->
        [one] 🌿 { $n } practice in a row
       *[other] 🌿 { $n } practices in a row
    }
stats-run-longest = Most in a row this year: { $n }
stats-consistency-hint = Unmarked days aren't counted. Rest, moon, sick and travel days keep the run going: rest is part of the practice.
stats-legend-practiced = Practice
stats-legend-rest = Rest
stats-legend-moon = 🌙 Moon day (rest)
stats-legend-away = Sick or travelling
stats-legend-skipped = No practice
stats-legend-none = Not marked
stats-legend-moon-marker = Full or new moon · 📍 { $city }
stats-show-ladies = Show 🌸 days on this device
stats-cell-label = { $date }: { $status }{ $moon ->
        [yes] , full or new moon
       *[no] {""}
    }
stats-cell-future = { $date }{ $moon ->
        [yes] : full or new moon
       *[no] {""}
    }
stats-back = ‹ Back
stats-month-practices = { $n ->
        [one] { $n } practice
       *[other] { $n } practices
    }
stats-online = 🌐 online: { $n }
stats-by-series = By series
stats-series-short = ☀️ Short
stats-no-details = No details
# $th/$tm = total hours/minutes; zero parts are dropped ("45 min", "2 h").
stats-duration = ⏱ { $th ->
        [0] { $tm } min
       *[other] { $tm ->
            [0] { $th } h
           *[other] { $th } h { $tm } min
        }
    } in total · about { $avg } min per practice
stats-unlogged = { $n ->
        [one] { $n } unmarked day: tap a day to add it
       *[other] { $n } unmarked days: tap a day to add it
    }
stats-month-empty = Nothing marked this month yet. Days you mark will show up here.
stats-load-failed = Couldn't load your stats. Try again in a moment.
stats-editor-done = Done
stats-prev = ‹
    .aria-label = Previous year
stats-next = ›
    .aria-label = Next year

## Settings (ID-06).
settings-open = ⚙️ Settings
settings-title = Settings
settings-name = Name
settings-name-hint = How I greet you. Leave it empty to use your Telegram name.
settings-language = Language
language-auto = As in Telegram
language-en = English
language-ru = Русский
settings-zone = Time zone
settings-zone-now = { $time } { $zone }
settings-zone-unset = Not set yet. Reminders start once it's set.
settings-zone-use-device = Use this phone's zone: { $zone }
settings-zone-pick = Pick a city
settings-zone-utc = UTC (no daylight saving)
settings-zone-hint = Reminders follow this zone. Days you've already logged keep their dates.
zone-travel = Your phone is on { $device } time. Reminders use { $current }.
zone-travel-switch = Switch to { $city }
zone-travel-keep = Keep { $city }
settings-moon-time = Send at
settings-quiet = Quiet hours
settings-quiet-from = Quiet from
settings-quiet-to = Quiet until
settings-quiet-off = No quiet hours
settings-quiet-conflict = A reminder falls in these hours. Move it first.
settings-cap = { $n ->
        [one] At most { $n } message a day
       *[other] At most { $n } messages a day
    }
settings-privacy = Privacy
settings-privacy-ladies = 🌸 Ladies' holiday is stored encrypted. Others only ever see “Rest day”.
settings-privacy-sharing = For now, only you see what you log. When teachers join, you choose what they see.
settings-save-failed = Couldn't save. Try again in a moment.
