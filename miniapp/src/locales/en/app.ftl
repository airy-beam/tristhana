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
