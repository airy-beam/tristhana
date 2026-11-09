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
home-first-hint = Start by logging today: practice or rest.
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
preset-short = ☀️ Short → standing
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
# MD-04: the person's own city, when it isn't the followed one.
moon-same-as-city = Same as my city ({ $city })
moon-home-fyi = ℹ In 📍 { $city } it falls on { $date }
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

## Moon calendar inheritance (MD-02). Names fall back to `link-no-name`.
moon-source-teacher = 👥 Same as your main teacher, { $name }. You can choose another city.
moon-source-teacher-none = 👥 { $name } hasn't chosen a city yet, so the dates are for 📍 { $city } for now.
moon-follow-teacher = 👥 Follow my teacher ({ $name })
moon-teacher-shared =
    { $chosen ->
        [yes] 👥 Students who haven't chosen a city follow yours: 📍 { $city }.
        [follow] 👥 Your students' moon days are for 📍 { $city }. You can keep it or choose your own city.
       *[no] 👥 Your students' moon days are for 📍 { $city }, like yours. You can keep it or choose your own city.
    }

## Practice reminder (PR-10). { $d } is an ISO weekday (1 = Monday).
remind-card-title = 🧘 Practice reminder
remind-switch = 🔔 Ask me once a day
remind-explain-app = Once a day I'll ask in the bot how it went, with one-tap buttons. Not on moon days, days you've already logged, or while a pause is on.
remind-time-label = Time · { $zone }
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
stats-consistency-hint = Days you haven't logged are left out. Rest, moon, sick and travel days don't reset the count: rest is part of the practice.
stats-legend-practiced = Practice
stats-legend-rest = Rest
stats-legend-moon = 🌙 Moon day (rest)
stats-legend-away = Sick or traveling
stats-legend-skipped = No practice
stats-legend-none = Not logged
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
stats-online = 🌐 Online: { $n }
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
        [one] { $n } day not logged: tap a day to add it
       *[other] { $n } days not logged: tap a day to add it
    }
stats-month-empty = Nothing logged this month yet. Days you log will show up here.
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
settings-name-hint = How I greet you, and the name your teachers and students here see. Leave it empty to use your Telegram name.
settings-language = Language
language-auto = As in Telegram
language-en = English
language-ru = Русский
# MD-04 (ADR-0029): the city sets the time zone. $zone = "Astana (UTC+5)".
settings-city = 🏙 My city
settings-zone-now = { $time } { $zone }
settings-zone-unset = Not set yet. Reminders start once it's set.
settings-city-nudge = Pick your city if you like: times will then show its name.
settings-city-not-now = Not now
settings-city-pick = Which city do you live in?
settings-city-unlisted-option = My city isn't listed
settings-city-use-device = Use my phone's time: { $zone }
settings-zone-utc = UTC (no daylight saving)
settings-zone-hint = Reminders and times follow your city's clock. Days you've already logged keep their dates.
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
settings-privacy-sharing = Your log is yours. A teacher on your list sees your name, your last asana and what you log from the day you added them: practice or rest and your practice length. All rest you log looks the same, whatever the reason. If nothing shows for a while, your teacher sees a short note saying just that. A teacher on your list can also mark a new asana for you: you get a message and can undo it. Check-ins, diary notes and the reason for a rest stay private. You can remove a teacher from your list any time. Teachers on your list and your shalas can send you announcements; you can mute each one.
# MD-04: tzfpy's zone data is ODbL (ADR-0029), so it is credited here and in the README.
settings-privacy-location = 📍 A location you send the bot is used only to find your time zone and isn't stored. The lookup runs on our server with tzfpy; its map data is © OpenStreetMap contributors (ODbL).
settings-save-failed = Couldn't save. Try again in a moment.

## Weekly day off and auto-rest (PR-09). { $d } is an ISO weekday (1 = Monday).
settings-day-off = Day off
settings-day-off-hint = Pick one or two; the other days are your practice days. Days off show as rest in your log and stats, and practice reminders come on practice days only. { $first ->
        [yes] Past weeks show them too.
       *[no] A change applies from today; earlier weeks stay as they were.
    } If a day goes differently, just log it. With no fixed day off, reminders come every day except moon days.
day-off-none = No fixed day off
remind-days-follow = On your practice days: { $days }. Change them under Day off.
remind-every-day = every day
day-off-weekday = { $d ->
        [1] Monday
        [2] Tuesday
        [3] Wednesday
        [4] Thursday
        [5] Friday
        [6] Saturday
       *[7] Sunday
    }
day-off-weekly = { $d ->
        [1] on Mondays
        [2] on Tuesdays
        [3] on Wednesdays
        [4] on Thursdays
        [5] on Fridays
        [6] on Saturdays
       *[7] on Sundays
    }
today-auto-moon = 🌙 Moon day (📍 { $city }), a traditional rest day{ $dayoff ->
        [yes] {" "}and your weekly day off too
       *[no] {""}
    }. If you practiced, log it below.
today-auto-day-off = 😌 Your weekly day off, shown as rest. If the day went differently, log it below.
day-off-ask = { $reminders ->
        [on] 😌 Practice reminders don't come { day-off-weekly }. Is that your weekly day off?
       *[off] 😌 Is { day-off-weekday } your weekly day off?
    }
day-off-ask-yes = Yes
day-off-ask-instead = { $d ->
        [6] Saturday
       *[7] Sunday
    }
day-off-ask-other = Other…
day-off-ask-later = Not now
stats-legend-auto = Day off or moon day (not logged)
stats-cell-auto = { $date }: { $kind ->
        [moon] 🌙 moon day (📍 { $city })
       *[day_off] 😌 day off
    }{ $dayoff ->
        [yes] , also your day off
       *[no] {""}
    }, not logged
stats-day-off-link = 😌 Set your weekly day off

## WH-01 part 2: multi-day 🌸 / sick / travel with a reminder pause (spec §7 draft copy)
pause-ask = { $reminders ->
        [on] { $rel ->
            [yesterday] ⏸ Pause practice reminders for how many days, including yesterday? Those days show as { $label } unless you log something else.
           *[today] ⏸ Pause practice reminders for how many days, including today? Those days show as { $label } unless you log something else.
        }
       *[off] { $rel ->
            [yesterday] How many days should show as { $label }, including yesterday?
           *[today] How many days should show as { $label }, including today?
        }
    }
pause-days = { $n ->
        [one] { $n } day
       *[other] { $n } days
    }
pause-other = Other…
pause-back = ‹ Back
pause-only = { $rel ->
        [yesterday] Just yesterday
       *[today] Just today
    }
pause-set = { $reminders ->
        [on] ⏸ Practice reminders are paused through { $until }. Those days show as { $label }; you can log any day differently.
       *[off] ⏸ Set through { $until }. Those days show as { $label }; you can log any day differently.
    }
today-period = { $label } through { $until }. If the day went differently, log it below.
pause-end = { $reminders ->
        [on] ⏹ End the pause
       *[off] ⏹ End early
    }
pause-ended = { $reminders ->
        [on] ▶️ Practice reminders are back from today.
       *[off] ⏹ Done: from today on, days no longer show as { $label }.
    }
pause-cut = { $rel ->
        [yesterday] ⏸ Practice logged for yesterday, so the following days, through { $until }, no longer show as { $label }. Keep them as they were?
        [other] ⏸ Practice logged for that day, so the following days, through { $until }, no longer show as { $label }. Keep them as they were?
       *[today] ⏸ Practice logged for today, so the following days, through { $until }, no longer show as { $label }. Keep them as they were?
    }
pause-keep = ⏸ Keep the pause
pause-kept = ⏸ Pause kept: { $label } through { $until }.
remind-paused-until = ⏸ Paused through { $until }
remind-resume = ▶️ Resume now
settings-ladies-button = Show the 🌸 Ladies' holiday button
settings-ladies-button-hint = In the bot and here. Days you already logged stay as they are.

## After-practice check-in (PR-06). Always optional; describes, never advises.
checkin-title = How do you feel?
checkin-mood = Mood
checkin-energy = ⚡ Energy: 1 low → 5 high
checkin-effort = 🔥 Effort: 1 easy → 5 hard
checkin-body = Body
checkin-mind = Mind
# Screen readers: the mood chips are emoji.
checkin-mood-label = Mood { $n } of 5
checkin-mood-chip = { $n ->
        [1] 😔
        [2] 😕
        [3] 😐
        [4] 🙂
       *[5] 😊
    }
checkin-tag = { $tag ->
        [stiff] Stiff
        [open] Open
        [strong] Strong
        [light] Light
        [heavy] Heavy
        [sore] Sore muscles
        [focused] Focused
        [calm] Calm
        [scattered] Scattered
       *[steady_breath] Steady breath
    }
checkin-edit = ✨ Check-in
checkin-clear = Remove check-in
checkin-save-failed = Couldn't save the check-in. Try once more in a moment.
settings-checkin = Offer a check-in after practice
settings-checkin-hint = Mood, energy and effort right after logging today's practice. You can always add one from the day.

## Diary note (PR-07). Private, per day, any status; never asked for.
diary-title = Diary
diary-add = Add a note
diary-edit = Edit
diary-save = Save
diary-cancel = Cancel
diary-placeholder = Your note…
# Shown from 1800 characters; numbers only, so no plural forms.
diary-counter = { $n } / { $max }
diary-save-failed = Couldn't save the note. Your text is still here, so you can try once more.
diary-private-hint = Your diary is private: teachers don't see it.
diary-unreadable = This note can't be read right now. You can write a new one or remove it.
diary-clear = Remove note
diary-clear-confirm = Remove this note?
diary-clear-yes = Remove
diary-removed = Removed from your diary.
diary-discard-confirm = Leave without saving your note?
diary-discard-yes = Don't save
diary-discard-no = Keep writing

## Progression (PR-08) and its celebrations (GM-01). Same wording as the bot; asana, item
## and series names come from the catalog. $series is a `series-name`, $traditional a
## traditional name or "none".
progression-open = 🧘 My asanas
progression-title = My asanas
progression-unset = Where does your practice end now? Set it once, then mark it here when you get a new asana.
progression-suggest = From your log: { $length }
progression-standing-only = Sun salutations and standing
progression-current = Your practice: { $length }
progression-items = Backbends: { $items }
progression-new = 🎉 New asana: { $asana }
progression-item-new = 🎉 { $item }
progression-new-other = 🎉 Another new asana…
progression-change = ✏️ Change
progression-change-explain = Pick where your practice ends now. Your history stays.
progression-pick-series = Series
progression-pick-asana = Last asana
progression-save = Save
progression-cancel = Cancel
progression-date = Date
progression-history = History
progression-undo = ↩︎ Undo
progression-undo-entry = ↩︎ Undo: { $entry }
progression-back = { $asana } is in your practice.
progression-changed = This changed on another device. Here's the latest.
progression-save-failed = Couldn't save. Please try once more.
progression-event =
    { $kind ->
        [start] Started at { $asana }
        [given] 🎉 { $asana }
        [changed] Changed to { $asana }
        [item_given] 🎉 { $item }
       *[item_removed] { $item }: removed
    }
progression-ask-new = { $asana } goes beyond your last asana. New asana? 🎉
progression-ask-yes = 🎉 Yes, new
progression-ask-no = Not new
## PR-08 Phase 3: who marked it; $teacher falls back to `progression-by-teacher`.
progression-marked-by = Marked by { $teacher }
progression-event-by = · { $teacher }
progression-by-teacher = a teacher
progression-mark-moved-on = Your practice has changed since this mark, so nothing was undone. To set where it ends now, use ✏️ Change.
celebrate-new-asana = 🎉 New asana: { $asana }. Enjoy it!
celebrate-new-asanas = 🎉 New asanas: { $from } → { $asana }
celebrate-series-complete =
    { $traditional ->
        [none] 🎉 Full { $series }.
       *[other] 🎉 Full { $series }: { $traditional }.
    }
celebrate-series-begins =
    { $traditional ->
        [none] 🎉 { $series } begins.
       *[other] 🎉 { $series } begins: { $traditional }.
    }
celebrate-item = 🎉 { $item }: a lovely step.
celebrate-practice-count = 🎉 { $count } { $count ->
        [one] practice
       *[other] practices
    } in your log. Thank you for coming to the mat.
preset-mine = 🧘 My practice: { $length }
# Milestone item names: the catalog name, plus the everyday name where people use one.
milestone-label =
    { $slug ->
        [viparita-chakrasana] { $name } (tic-tacs)
       *[other] { $name }
    }

## My data: export and account deletion (ST-09). The file is sent by the bot to the chat.

data-title = 📦 My data
data-intro = Download everything you've logged here, or delete your account.
export-button = ⬇️ Download my data
export-sending = Sending…
export-sent-app = Sent to your chat with the bot. The file includes your private entries: once it's saved, you can delete it from the chat.
# $minutes = whole minutes until the next export (1–10)
export-too-soon = A file was sent a moment ago. Again in { $minutes } min.
export-unreachable = Couldn't send the file to your chat. Open the bot, tap Start, then try again.
export-too-large = This file is too big for Telegram, so it couldn't be sent. Your data is safe here, nothing has changed.
export-failed = Couldn't send the file. Try again in a moment.
delete-button = Delete my account…
delete-explain = This deletes your account and everything in it, right away: days and rest pauses, practices, check-ins, diary notes, your asana progress, teacher and student lists and settings. It can't be undone.
delete-explain-chat = Messages in the bot's chat stay; you can clear the chat in Telegram.
delete-explain-backups = Copies in our backups disappear within 30 days.
delete-explain-fresh = If you write to the bot again, it starts fresh.
delete-explain-shalas = Shalas you own are deleted for everyone in them. Their own logs stay.
delete-export-first = ⬇️ Download my data first
delete-confirm = Delete everything
delete-confirm-popup = Delete your account and all data? This can't be undone.
delete-cancel = Cancel
delete-failed = Couldn't delete. Try again in a moment.
delete-done-app = Your account and data are deleted. Wishing you good practice 🙏 Open the bot any time to start fresh.
delete-close = Close

students-days-note = Days follow each student's own time zone.
students-week = Last 7 days
students-last-asana = Last asana, as marked in their log: { $asana } ({ $series })
students-last-standing = As marked in their log: sun salutations and standing
students-blank-note = Not every day gets logged, rest days included. A blank says nothing about the practice.
students-quiet = Nothing shared for a while
students-mark =
    { $state ->
        [practiced] 🧘
       *[rest] 😌
    }
students-day = { $date }: { $state }
students-day-length = { $date }: { $state }, { $length }
students-day-blank-mark = { $date }: ·
students-day-blank = { $date }: nothing to show
students-more = Show more
students-card-load-failed = Couldn't load this page. Try again in a moment.
students-load-failed = Couldn't load your students. Try again in a moment.
## PR-08 Phase 3: a teacher marks a new asana (same wording as the bot).
students-give = 🎉 Mark new asana
students-give-option = { $asana }
students-give-range = → { $asana }
students-give-ask = { $name }: the next asana is { $asana } ({ $series }). Mark it as new? { $name } gets a message from the bot and can undo it.
students-give-ask-range = { $name }: new asanas { $from } → { $asana } ({ $series }). Mark them? { $name } gets one message from the bot and can undo it.
students-give-ask-across = { $name }: new asanas { $from } ({ $from_series }) → { $asana } ({ $series }). Mark them? { $name } gets one message from the bot and can undo it.
students-give-yes = 🎉 Yes, mark
students-given = ✅ Marked: { $asana }.
students-given-range = ✅ Marked: { $from } → { $asana }.
students-give-stale = This card was out of date, so nothing was marked. Here it is now.
students-give-unset = No last asana set yet. Once they set it in My asanas, you can mark new ones here.
links-students = 👥 My students ({ $count })
link-students-open = 👥 My students
day-label =
    { $rel ->
        [today] Today, { $date }
        [yesterday] Yesterday, { $date }
       *[other] { $date }
    }

## Shalas (SC-01, ADR-0033). Shala and people names are plain text.
moon-source-shala = 🏛 Same as your shala, { $shala }. You can choose another city.
moon-follow-shala = 🏛 Follow my shala ({ $shala })
links-shalas-title = 🏛 Shalas
shala-create = 🏛 Create a shala
shala-name-label = Name
shala-city-label = City
shala-online-only = 🌐 Online classes only
shala-my-roles = My roles in the shala
shala-create-submit = Create
shala-name-invalid = The shala needs a name, up to 64 characters.
shala-caps = No more shalas or staff links for now: that's the limit.
shala-save-failed = Couldn't save. Try again in a moment.
shala-load-failed = Couldn't load the shala. Try again in a moment.
shala-role =
    { $role ->
        [owner] Owner
        [admin] Manager
        [teacher] Teacher
        [assistant] Assistant
       *[office] Front desk
    }
shala-title = 🏛 { $shala }
shala-person = { $name } · { $roles }
shala-online = 🌐 Online
shala-place = 📍 { $city }
shala-time = { $place } · shala time: { $zone }
shala-moon-line = 🌙 Moon days: 📍 { $city }
shala-moon-city = City for the shala's moon days
shala-moon-same = Same as the shala's city
shala-moon-shared = 🌙 Staff, and members whose teacher works here, follow this calendar unless they chose a city. Other members follow it unless they or their teacher chose one.
shala-staff-title = Teachers and staff
shala-edit = ✏️ Edit the shala
shala-roles-save = Save
shala-students = 👥 Students ({ $n })
shala-no-students = No students in this shala yet.
shala-invite-students = ➕ Invite students
shala-invite-staff = ➕ Invite staff
shala-staff-pick = Choose a role. The link adds one person with that role.
shala-staff-link-hint = This link adds one person as { $role }. It works once, for 7 days.
shala-join-hint = Share this link or QR code. Each student confirms for themselves.
shala-share-text = Join { $shala } in Tristhana. Before you confirm, the bot shows who sees what.
shala-qr-alt = QR code for the shala's link
shala-remove = Remove…
shala-remove-ask = Remove { $name } from the shala? No one gets a message.
shala-remove-yes = Remove
shala-leave = Leave…
shala-leave-ask = Leave { $shala }? No one gets a message, and your log stays as it is.
shala-leave-yes = Leave
shala-delete = Delete the shala…
shala-delete-ask = Delete { $shala } for everyone in it? Everyone's own logs stay. No one gets a message. This can't be undone.
shala-delete-yes = Delete

## Shala classes (SC-02). Times are wall clock in the shala's zone; { $zone } is "Almaty (UTC+5)".
schedule-title = 🗓 Schedule
schedule-load-failed = Couldn't load the schedule. Try again in a moment.
schedule-moon-day = 🌙 Moon day
schedule-day-off = 😌 Shala day off
schedule-empty = No classes these days.
schedule-your-time = ({ $time } your time)
schedule-reason = { $reason ->
        [moon] moon day
        [closure] shala closed
       *[cancelled] cancelled
    }
schedule-swap = 🔁 Instead of { $day }
schedule-substitute = { $name } (substitute)
schedule-add-class = ➕ Add a class
class-type = { $type ->
        [conference] Conference
        [pranayama] Pranayama
        [chanting] Chanting
       *[workshop] Workshop
    }
class-led-hint = Often Friday or Sunday
class-form-type = Type
class-form-title = Title (optional)
class-form-teacher = Teacher
class-form-no-teacher = —
class-form-start = Start, { $zone }
class-form-until = Until
class-form-length = Length, minutes
class-form-days = Days (none: a single date)
class-form-every = Repeats
class-form-every-n = { $n ->
        [1] every week
       *[other] every { $n } weeks
    }
class-form-from = First date
class-form-end = Last date (optional)
class-form-online = 🌐 Online
class-form-zone = Times in
class-form-applies = Applies to
class-form-day-off-warning = One of the chosen days is the shala's day off.
class-form-window-invalid = The class needs to end after it starts, and by midnight.
class-form-save = Save the class
class-form-cancel = Cancel
class-form-failed = Couldn't save the class. Check the times and try again.
class-form-caps = That's the limit for this shala for now.
shala-moon-policy-label = 🌙 On moon days
shala-moon-policy = { $p ->
        [pranayama] 🌙 Moon days: pranayama, chanting and talks only
        [open] 🌙 Moon days: classes as usual
       *[closed] 🌙 Moon days: the shala is closed
    }
shala-moon-policy-option = { $p ->
        [pranayama] Pranayama, chanting and talks only
        [open] Classes as usual
       *[closed] The shala is closed
    }
shala-moon-policy-note = Dates follow the shala's moon city (lunar day at sunrise). If your shala observes another day, use Hold anyway or Cancel.
shala-day-off-label = 😌 Day off (up to two)
shala-day-off-line = 😌 Day off: { $days }
shala-day-off-adopt = 😌 Make { $days } my day off too
occurrence-cancel = ❌ Cancel this class
occurrence-hold = ✅ Hold anyway
occurrence-restore = ↩ Restore
occurrence-note = No one gets a message. The change shows on the schedule.
occurrence-failed = Couldn't change the class. Try again in a moment.
occurrence-delete = 🗑 Delete this class (all dates)…
occurrence-delete-ask = Delete this class on every date? It goes from the schedule. No one gets a message.
occurrence-delete-yes = Delete
occurrence-teacher = Teacher on this date
occurrence-usual-teacher = Usual teacher ({ $name })
closure-title = 🏖 Shala closed
closure-start = First day
closure-end = Last day
closure-add = ➕ Add closed days
closure-line = { $start } – { $end }
closure-remove = 🗑 Remove
closure-failed = Couldn't save the dates: up to 92 days in a row, from today on.
swap-title = 🔁 Swap a moon day
swap-from = Moon day
swap-to = Hold its classes on
swap-add = ➕ Add the swap
swap-remove = 🗑 Undo the swap
swap-hint = Only classes cancelled for the moon day or a closure move; the rest stay put. Pick the day off or a day without the same class, up to 6 days away.
swap-failed = That swap doesn't fit: pick the day off or a day without these classes, within 6 days, not a moon day or a closed day.
# My schedule (SC-03): every shala I'm in, a week at a time, in my zone. { $zone } is "Almaty (UTC+5)".
my-schedule-open = 🗓 My schedule
my-schedule-title = 🗓 My schedule, { $range }
my-schedule-filter = { $f ->
        [teachers] 👤 My teachers
        [mine] 🧑‍🏫 I teach
       *[all] All
    }
schedule-zone = Times: { $zone }
my-schedule-my-moon = 🌙
my-schedule-my-moon-label = your moon day
my-schedule-teacher-mark = 👤
schedule-held-moon = · 🌙
schedule-moved = ↪ moved from { $day } { $time }
schedule-swapped-from = 🔁 instead of { $day }
schedule-swapped-inline = 🔁 { $day }
schedule-covering-for = { $name } (for { $teacher })
schedule-shift = ⚠ From { $weekday ->
        [1] Monday
        [2] Tuesday
        [3] Wednesday
        [4] Thursday
        [5] Friday
        [6] Saturday
       *[7] Sunday
    }, { $date }, { $where } is { $hours } h { $dir ->
        [earlier] earlier
       *[later] later
    } for you
my-schedule-empty = { $f ->
        [teachers] No classes with your teachers this week.
        [mine] You teach no classes this week.
       *[all] No classes this week.
    }
my-schedule-zone-unknown = Times are in { $zone }. Set your city to see your own time.
my-schedule-load-failed = Couldn't load your schedule. Try again in a moment.
# Rows I teach (shown in My schedule with "I teach").
my-classes-covered = { $name } is covering
my-classes-covering = you're covering for { $name }

# Paging (shala students, SC-01; schedule weeks, SC-02).
page-prev = ◀
page-next = ▶

# Calendar subscription (SC-06): a personal ICS link for Google, Apple or Outlook.
feed-open = 📅 Add to calendar
feed-title = 📅 Calendar subscription
feed-explain = Your classes and moon days in Google, Apple or Outlook Calendar. It updates by itself (Google can take up to a day).
feed-moon-only = Join a shala to see its classes here too.
feed-create = 📅 Create my link
feed-copy = Copy link
feed-copied = ✓ Copied
feed-google = Add to Google Calendar
feed-google-phone = On a phone the Google button may not add it. Do it once on a computer: calendar.google.com → Other calendars + → From URL, and paste the link. Then it shows on your phone too.
feed-apple = Add to Apple / Outlook
feed-private = 🔒 Anyone with this link sees your schedule. Don't share it; if it got out, make a new one.
feed-checked = { $day ->
        [none] Not used by a calendar yet
       *[other] Last checked by a calendar: { $day }
    }
feed-rotate = 🔄 New link
feed-rotate-confirm = The old link stops working. Calendars that use it need the new one.
feed-off = Turn off
feed-off-confirm = Your calendar apps will stop updating. Events already there stay until you remove the calendar.
feed-failed = That didn't work. Try again in a moment.
feed-off-done = Turned off.

## Quick tour (UI-02). Never names the ladies' holiday (a private topic in a tour for everyone).

tour-open = 🧭 Quick tour
tour-offer = Want a quick look around? It takes a minute.
tour-offer-yes = Show me
tour-offer-no = Not now
tour-progress = { $n } of { $total }
tour-next = Next
tour-prev = ‹
    .aria-label = Previous step
tour-done = Done
tour-today = Log today: practice or rest. After a practice you can add details, how it felt and a private note.
tour-stats = Your year at a glance, plus a calendar for filling in earlier days.
tour-asanas = Your last asana. Log a new one here when your teacher gives it.
tour-moon = The next moon days: full and new moons, traditional rest days. You pick the city in Settings.
tour-settings = Your city, weekly day off, reminders and privacy. This tour lives here too.

links-title = 👥 Teachers and students
links-empty = No teachers on your list. Your log works the same either way.
links-no-students = No students on your list.
links-primary-hint = ⭐ marks your main teacher. You can change it any time.
links-main-chosen = ⭐ Main teacher: { $name }
links-main-auto = ⭐ Main teacher: { $name } (first on your list)
links-make-main = ⭐ Make main
links-remove = Remove…
links-remove-yes = Remove
links-invite = ➕ Invite students
links-invite-first = I teach: invite students
link-no-name = (no name)
link-unlink-ask = Remove { $name } from your teachers? They won't get a message, but you'll no longer be on their list.
link-next-main = { $name } becomes your main teacher.
link-remove-ask = Remove { $name } from your students? They won't get a message.
invite-hint = Share this link or QR code. Each student confirms for themselves.
invite-share = 📤 Share
invite-share-text = My link to add me as your teacher in Tristhana. The bot shows what I'd see before you confirm.
invite-copy = Copy link
invite-copied = Copied
invite-new = 🔄 New link…
invite-new-ask = Get a new link? The old link and QR stop working. People already on your list stay.
invite-new-yes = 🔄 Yes, new link
invite-qr-alt = QR code for your invite link
links-load-failed = Couldn't load your lists. Try again in a moment.

## NT-03: announcements from a teacher or a shala
ann-announce = 📣 Announce
ann-compose-title = 📣 Announcement
ann-to-students = To: all your students ({ $count })
ann-to-shala = To: everyone in { $shala } ({ $count })
ann-text-label = Text
ann-pin-label = Pin it in the app
ann-pin-none = No pin
ann-pin-week = 📌 1 week
ann-pin-month = 📌 1 month
ann-hint = Name the day and time (e.g. Mon 10 Nov, 6:00), not "tomorrow": people may read it later. Everyone it goes to sees this text and your name, so leave out other people's personal details. It can't be edited once sent.
ann-hint-shala = It goes to everyone in the shala: students and staff.
ann-send = Send
ann-send-ask =
    Send to { $count ->
        [one] { $count } person
       *[other] { $count } people
    }? It arrives within about 10 minutes.
ann-sent = ✅ Sent.
ann-sent-title = Sent
ann-sent-to =
    Sent to { $count ->
        [one] { $count } person
       *[other] { $count } people
    }
ann-limit = 3 announcements have already gone out here in the last 24 hours, the most for one day. Your text is still here: you can send it a little later.
ann-pinned-until = 📌 until { $date }
ann-unpin = Unpin
ann-delete = 🗑 Delete
ann-delete-ask = Delete this announcement? It leaves the app and won't go out to anyone else. Messages already delivered stay in people's chats.
ann-list = 📣 Announcements
ann-list-empty = No announcements in the last 30 days.
ann-all = All
ann-send-to-me = Send announcements from { $source } to me in the bot
settings-announcements = 📣 Announcements from teachers and shalas

## SC-05: class attendance (presence, not a log entry or an absence)
attend-me-button = 🙋 I was there
attend-state = { $s ->
        [confirmed] ✅ confirmed
       *[claimed] 🙋 your mark
    }
attend-remove-ask = Remove your mark?
attend-remove-yes = Remove
attend-claimed = { $state ->
        [confirmed] ✅ Marked: { $what }.
       *[claimed] 🙋 Marked: { $what }. The shala's staff can confirm it.
    }
attend-removed = Mark removed.
attend-log-day = 🧘 Log this day
attend-failed = Couldn't save the mark. Try again in a moment.
attend-staff-open = 📋 Attendance · ✅ { $confirmed } · 🙋 { $claimed }
attend-title = 📋 Attendance
attend-roster-counts = ✅ { $confirmed } · { $claimed ->
        [0] nothing to confirm
        [one] 🙋 1 to confirm
       *[other] 🙋 { $claimed } to confirm
    }
attend-roster-hint = Tick who came. 🙋 = their own mark.
attend-confirm-all = ✅ Confirm all 🙋 ({ $n })
attend-staff-tag = staff
attend-search = Search by name
attend-empty = No one on the list yet. Students appear here once they join the shala.
attend-not-open = This class can't be marked now: it hasn't started, it was cancelled, or it was more than 7 days ago.
attend-save = { $n ->
        [one] Save (1 change)
       *[other] Save ({ $n } changes)
    }
attend-save-first = Up to 100 changes at a time: save these first.
attend-load-failed = Couldn't load the list. Try again in a moment.
attend-close = Close

## ST-07: share cards
share-open = Share
share-title = Share a card
share-close = ✕
    .aria-label = Close
share-format-story = Story
share-format-square = Square
share-preview-alt = Card preview
share-loading = Drawing the card…
share-failed = Couldn't make the card. Try again a bit later.
share-rate-limited = That's a lot of cards today. Try again tomorrow.
share-privacy-note = The card shows your practice days: no name, notes or reasons for rest.
share-to-story = Share to story
share-save = Save image
share-saved = ✓ Saved
share-send-chat = Send to my chat
share-sent = ✓ Sent to your chat
share-send-unreachable = The bot can't write to you yet. Open @tristhana_bot, tap Start, then try again.
share-story-caption = My practice · @tristhana_bot
share-entry = Share: { $entry }
