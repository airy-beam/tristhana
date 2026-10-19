# Mini App copy (en). Keys must match locales/ru/app.ftl. Keys are prefixed by screen.

# Home: greeting with the Telegram first name (display only).
home-greeting = Namaste, { $name } 🙏
home-greeting-anon = Namaste 🙏
home-subtitle = Your Ashtanga practice companion. Stats are coming soon.

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
