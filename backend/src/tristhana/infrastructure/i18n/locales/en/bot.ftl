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
    🔔 /remind: practice reminder
    🧘 /asanas: my asanas, mark a new one
    🌙 /moon: upcoming moon days and reminders
    👥 /teachers: your teachers and students
    🗓 /schedule: classes of all your shalas, in your time
    🧑‍🏫 /classes: the classes you teach this week
    ⚙️ /settings: language, city, reminders
    📊 Your practice log and stats live in the app (the button next to the message field).

# UI-05: a link under /help to the public guide site, in the person's language.
help-guide = 📖 Guide

## Quick tour (UI-02). Never names the ladies' holiday (a private topic in a tour for everyone).

tour-open = 🧭 Quick tour
tour-progress = { $n } of { $total }
tour-next = Next ›
tour-back = ‹ Back
tour-done = ✓ Done
tour-log =
    📝 Your log
    Practice or rest? Both go in your log. Mysore, led or on your own, short or full: it's all practice. After a practice you can add details, how it felt and a private note. An earlier day? /log takes you back.
tour-rest =
    🌿 Rest and moon days
    Rest is part of the practice. Full and new moon days are traditional rest days: they fill in on their own, and so does your weekly day off once you set it in /settings. If a day goes differently, just log it. Dates and moon reminders are in /moon.
tour-remind =
    🔔 Reminders
    If you'd like, /remind asks once a day how it went, with a one-tap log. It comes on your practice days, not on moon days. Out for a few days, say sick or traveling? Log the first day and I'll offer a pause.
tour-asanas =
    🧘 My asanas
    /asanas keeps your last asana, so logging a practice takes fewer taps. New asana from your teacher? Mark it there 🎉
tour-app =
    📊 The app
    Your year at a glance, month summaries and a calendar for earlier days. Everything you log here is there too. This tour stays in /help.

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

## The bot's profile (UI-05), set by tools/telegram/set_webhook.py --texts, not shown by
## the bot itself. Description: the empty chat above Start, up to 512 characters. About: the
## profile, one line, up to 120. Public texts: 🌸 is never named here.
bot-description =
    Tristhana is a companion for your Ashtanga practice.

    🧘 Log practice or rest in one tap
    🌙 Moon days for your city, with reminders
    📊 Your year, your month, your asanas
    👥 Teachers and shalas: schedule, attendance, announcements

    Your log is yours. A teacher sees only what you agree to.

    Guide: tristhana.app
bot-about = Your Ashtanga companion: a log for practice and rest, moon days, your asanas. Guide: tristhana.app

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
    ☀️ Short: Surya Namaskara, standing, optional backbends and finishing.
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
# MD-04: the person's own city, when it isn't the followed one.
moon-same-as-city = 📍 Same as my city ({ $city })
moon-home-fyi = ℹ In 📍 { $city } it falls on { $date }
# Full-width button: sets the account's time zone to the city's (only when unknown).
moon-use-city-zone = 🕐 Time zone: 📍 { $city }

## Moon calendar inheritance (MD-02). Names fall back to `link-no-name`.
moon-source-teacher = 👥 Same as your main teacher, { $name }. You can choose another city.
moon-source-teacher-none = 👥 { $name } hasn't chosen a city yet, so the dates are for 📍 { $city } for now.
moon-follow-teacher = 👥 Follow my teacher ({ $name })
moon-teacher-shared =
    { $chosen ->
        [yes] 👥 Students who haven't chosen a city follow yours: 📍 { $city }.
        [follow] 👥 Your students' moon days are for 📍 { $city }. You can keep it or choose your city in /moon.
        [shala] 👥 Students in your shala follow its moon calendar. Your other students get 📍 { $city } by default, or your city if you choose one in /moon.
       *[no] 👥 Your students' moon days are for 📍 { $city }, like yours. You can keep it or choose your city in /moon.
    }
moon-follow-changed = 🌙 Your moon days now follow { $name }: 📍 { $city }. You can change this in /moon.
moon-follow-ended = 🌙 Your moon days are now for 📍 { $city }. You can change this in /moon.
moon-teacher-own = 🌙 Now that you have students, your moon days follow your own setting: 📍 { $city }. To keep 📍 { $kept } (as with { $name }), tap below.
moon-keep-city = Keep 📍 { $city }
moon-kept = 🌙 Done: your moon days stay with 📍 { $city }. You can change this in /moon.
moon-keep-already = 🌙 Your moon city is already chosen: 📍 { $city }. You can change it in /moon.
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
command-remind = Practice reminder
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
remind-explain = Once a day I'll ask how it went, with one-tap buttons. Not on moon days, days you've already logged, or while a pause is on.
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
remind-moon-link = 🌙 Moon reminders
remind-days-follow = They come on your practice days. To change the days, tap 😌 Day off.
remind-practice-link = 🧘 Practice reminder

## Settings (ID-06).
command-settings = Language, city, reminders
settings-title = ⚙️ Settings
language-auto = As in Telegram
language-en = English
language-ru = Русский
settings-language-line = 🗣 Language: { $language }
# MD-04 (ADR-0029): the city sets the time zone. $zone = "Astana (UTC+5)".
settings-city-line = 🏙 My city: { $zone }
settings-city-unset-line = 🏙 My city: not chosen yet · 🕐 { $zone }
settings-city-unlisted-line = 🏙 My city: not chosen · 🕐 { $zone }
settings-city-no-zone-line = 🏙 My city: not chosen yet. Reminders start once it's set.
settings-city-nudge = Pick your city if you like: times will then show its name.
settings-city-not-now = Not now
settings-moon-line = 🌙 Moon days: 📍 { $city }
settings-moon-line-teacher = 🌙 Moon days: 📍 { $city } (as { $name })
settings-quiet-line = 🔕 Quiet hours { $start }–{ $end } · { $n ->
        [one] at most { $n } message a day
       *[other] at most { $n } messages a day
    }
settings-quiet-off-line = 🔕 No quiet hours · { $n ->
        [one] at most { $n } message a day
       *[other] at most { $n } messages a day
    }
settings-city-button = 🏙 My city
settings-moon-link = 🌙 Moon days
settings-pick-city = Which city do you live in? Reminders and times follow its clock.
settings-city-unlisted = 📍 My city isn't listed
settings-city-utc = 🌐 UTC
settings-share-location = Send your location once and I'll set your time zone from it. I use it only for that and don't store it. Can't send it from this device? Open the app: it can use your phone's time.
settings-share-location-button = 📍 Send my location
settings-location-zone = 🕐 Done: your time zone is { $zone }. You can change it in /settings.
settings-location-unknown = I couldn't find a time zone there. Pick a city in /settings, or open the app.
settings-open-app = ⚙️ More in the app
settings-link = ⚙️ Settings

## Weekly day off and auto-rest (PR-09).
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
day-off-button = { day-off-weekday }
settings-day-off-line = 😌 Day off: { day-off-weekday }
settings-days-off-line = 😌 Days off: { day-off-weekday }, { $e ->
        [1] Monday
        [2] Tuesday
        [3] Wednesday
        [4] Thursday
        [5] Friday
        [6] Saturday
       *[7] Sunday
    }
settings-day-off-none-line = 😌 No fixed day off
settings-day-off-unset-line = 😌 Day off: not chosen
settings-day-off-button = 😌 Day off
day-off-pick = 😌 Which day is your day off? Tap one or two; tap again to untick. The other days are your practice days.
day-off-none = No fixed day off
day-off-explain = Days off show as rest in your log and stats, and practice reminders come on practice days only. { $first ->
        [yes] Past weeks show them too.
       *[no] A change applies from today; earlier weeks stay as they were.
    } If a day goes differently, just log it. With no fixed day off, reminders come every day except moon days.
log-auto-moon = 🌙 Moon day (📍 { $city }), a traditional rest day{ $dayoff ->
        [yes] {" "}and your weekly day off too
       *[no] {""}
    }. If you practiced, log it below.
log-auto-day-off = 😌 Your weekly day off, shown as rest. If the day went differently, log it below.
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

## WH-01 part 2: multi-day 🌸 / sick / travel with a reminder pause (spec §7 draft copy)
# $label = the status-* label, $until = a date, $rel = today | yesterday, $reminders = on | off
pause-ask = { $reminders ->
        [on] ⏸ Pause practice reminders for how many days, including { $rel ->
            [yesterday] yesterday
           *[today] today
        }? Those days show as { $label } unless you log something else.
       *[off] How many days should show as { $label }, including { $rel ->
            [yesterday] yesterday
           *[today] today
        }?
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
pause-set = ⏸ { $reminders ->
        [on] Practice reminders are paused through { $until }.
       *[off] Set through { $until }.
    } Those days show as { $label }; you can log any day differently.
log-auto-period = { $label } through { $until }. If the day went differently, log it below.
pause-end = { $reminders ->
        [on] ⏹ End the pause
       *[off] ⏹ End early
    }
pause-ended = { $reminders ->
        [on] ▶️ Practice reminders are back from today.
       *[off] ⏹ Done: from today on, days no longer show as { $label }.
    }
pause-cut = ⏸ Practice logged for { $rel ->
        [yesterday] yesterday
        [other] that day
       *[today] today
    }, so the following days, through { $until }, no longer show as { $label }. Keep them as they were?
pause-keep = ⏸ Keep the pause
pause-kept = ⏸ Pause kept: { $label } through { $until }.
remind-paused-until = ⏸ Paused through { $until }
remind-resume = ▶️ Resume now
settings-ladies-line = 🌸 Ladies' holiday button: { $shown ->
        [yes] shown
       *[no] hidden
    }
settings-ladies-hide = 🌸 Hide the button
settings-ladies-show = 🌸 Show the button

## After-practice check-in (PR-06). Always optional: never "you haven't checked in".
# Mood is stored as 1–5; the emoji are presentation only. Tags are domain keys.
checkin-prompt = How do you feel after practice? Optional.
checkin-explain = ⚡ Energy: 1 low → 5 high · 🔥 Effort: 1 easy → 5 hard. Tap what fits, all optional.
checkin-mood-chip = { $n ->
        [1] 😔
        [2] 😕
        [3] 😐
        [4] 🙂
       *[5] 😊
    }
checkin-energy-chip = ⚡{ $n }
checkin-effort-chip = 🔥{ $n }
checkin-summary-energy = ⚡ energy { $n }/5
checkin-summary-effort = 🔥 effort { $n }/5
checkin-edit = ✨ Check-in
checkin-tags-open = 🏷 Body and mind…
checkin-tags-pick = How did body and mind feel? Pick any.
checkin-clear = Remove check-in
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
settings-checkin-line = ✨ Check-in after practice: { $offered ->
        [yes] offered
       *[no] not offered
    }
settings-checkin-off = ✨ Don't offer
settings-checkin-on = ✨ Offer

## Diary note (PR-07). Private, per day, any status. Never asked for; never echoed back.
# $rel = today | yesterday | other, $date = a formatted date (as in day-label).
diary-button = 📓 Note
diary-preview = 📓 { $text }
diary-empty = No note for this day. Write anything you'd like to keep: how the practice felt, what your teacher said, a new asana, or just a thought.
diary-unreadable = This note can't be read right now. You can write a new one or remove it.
diary-prompt = Write your note for { $rel ->
        [today] today
        [yesterday] yesterday
       *[other] { $date }
    } as a reply to this message. It's private, just for you.
diary-prompt-replace = It will replace the current note. Copy the note above to edit it.
diary-placeholder = Your note…
diary-saved = 📓 Saved to your diary.
diary-write = ✏️ Write
diary-rewrite = ✏️ Rewrite
diary-clear = Remove note
diary-clear-confirm = Remove this note?
diary-clear-yes = Remove
diary-removed = Removed from your diary. Earlier messages in this chat stay until you delete them.
diary-too-long = That's a bit long for one note: up to { $max } characters. Your text is still above, so you can shorten it and resend.
diary-text-only = Notes are text for now. Type your note as a reply to the prompt above.

## Progression (PR-08) and its celebrations (GM-01). Asana, item and series names come from
## the catalog; $series is a `series-name`, $traditional a traditional name or "none".

command-asanas = My asanas: where my practice ends
progression-title = 🧘 My asanas
progression-unset = Where does your practice end now? Set it once, then mark it here when you get a new asana.
progression-suggest = From your log: { $length }
progression-choose = Choose…
progression-standing-only = Sun salutations and standing
progression-current = Your practice: { $length }
progression-items = Backbends: { $items }
progression-new = 🎉 New asana: { $asana }
progression-new-other = 🎉 Another new asana…
progression-item-new = 🎉 { $item }
progression-change = ✏️ Change
progression-change-explain = Pick where your practice ends now. Your history stays.
progression-pick-series = Which series does your practice end with?
progression-pick-asana = Your last asana in { $series }:
progression-series-button = { $series }
progression-pick-new = Which new asana?
progression-saved = Saved: your practice ends at { $asana }.
progression-saved-standing = Saved: sun salutations and standing.
progression-back = { $asana } is in your practice.
progression-already = That's already in your practice.
progression-undo = ↩︎ Undo
progression-undone = Undone.
progression-ask-new = { $asana } goes beyond your last asana. New asana? 🎉
progression-ask-yes = 🎉 Yes, new
progression-ask-no = Not new
progression-open = 🧘 My asanas

## PR-08 Phase 3: the student's message about a teacher's mark (in the student's language),
## and who marked it in My asanas. $teacher falls back to `progression-by-teacher`.
mark-received = 🎉 New asana: { $asana }. Enjoy it! Marked by { $teacher }.
mark-received-range = 🎉 New asanas: { $from } → { $asana }. Enjoy them! Marked by { $teacher }.
mark-received-back = { $asana } is in your practice. Marked by { $teacher }.
mark-received-undo-hint = If this doesn't match your practice, you can undo it.
progression-marked-by = Marked by { $teacher }
progression-by-teacher = a teacher
progression-mark-moved-on = Your practice has changed since this mark, so nothing was undone. To set where it ends now, use ✏️ Change.
# A teacher's mark's Undo on My asanas: never two identical "↩︎ Undo" buttons.
progression-undo-mark = ↩︎ Undo the mark
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

## My data: export and account deletion (ST-09). "📦 My data" under /settings.

settings-data-button = 📦 My data
data-title = 📦 My data
data-intro = Download everything you've logged here, or delete your account.
export-button = ⬇️ Download my data
export-preparing = Preparing your file…
# $date = the local date, pre-formatted
export-caption = Your Tristhana data as of { $date }: data.json for apps, CSV files for spreadsheets.
export-sent = 📦 Sent below. The file includes your private entries (diary notes, all day statuses): once it's saved, you can delete it from this chat.
# $minutes = whole minutes until the next export (1–10)
export-too-soon = A file was sent a moment ago. Again in { $minutes } min.
export-unreachable = Couldn't send the file to your chat. Open the bot, tap Start, then try again.
export-too-large = This file is too big for Telegram, so it couldn't be sent. Your data is safe here, nothing has changed.
delete-button = Delete my account…
delete-export-first = ⬇️ Download my data first
delete-confirm = Delete everything
delete-explain =
    This deletes your account and everything in it, right away: days and rest pauses, practices, check-ins, diary notes, your asana progress, teacher and student lists and settings. It can't be undone.
    • Messages in this chat stay; you can clear the chat in Telegram.
    • Copies in our backups disappear within 30 days.
    • If you write to the bot again, it starts fresh.
    • Shalas you own are deleted for everyone in them. Their own logs stay.
delete-expired = This button is out of date. Here it is again.
delete-done = Your account and data are deleted. Wishing you good practice 🙏 Send /start any time to begin fresh.

## Export file labels and README (ST-09): in the account's language.

export-rest-unreadable = Rest (details couldn't be read)
export-kind-start = Starting point
export-kind-given = New asana
export-kind-changed = Correction
# $item = the milestone name (drop-backs, standing up, tic-tacs)
export-kind-item-given = Marked: { $item }
export-kind-item-removed = Unmarked: { $item }
export-readme-title = Your Tristhana data
export-readme-files =
    data.json: everything, for apps (format "tristhana.export/1").
    days.csv: one row per day you logged, with the practice, check-in and diary note.
    rest_periods.csv: pauses (🌸, sick, travel), end date included.
    progression.csv: your asana history.
    CSV files open in any spreadsheet (UTF-8).
# $city = the moon-day city
export-readme-days = Only days you logged are listed. Your day off, moon days (by your city 📍 { $city }) and pause days are filled in by the app, so they aren't in the day list; pauses are in rest_periods.csv. Rest days are part of the practice.
export-readme-moon-logged = "moon" in days.csv means you logged that day as a moon day.
export-readme-moon-city = Moon days follow your city's calendar (📍 { $city }); ask your teacher if your shala uses different dates.
export-readme-ladies = 🌸 days are listed here as they are (teachers see them as rest). Keep this in mind before sharing the file.
# $statuses = one "code: label" line per status
export-readme-statuses =
    Day statuses:
    { $statuses }
export-readme-length = An empty "series" means a short practice: sun salutations, standing, backbends if you like, finishing.
export-readme-halves = first_part: "first_half" = Primary, 1st half (up to Navasana); "second_half" = Primary, 2nd half (Bhujapidasana to the end), only together with Intermediate. Half Primary on its own is stored as series "primary", end "navasana".
# $contexts = one "code: label" line per practice context
export-readme-contexts =
    Practice context:
    { $contexts }
# $series = one "slug: name" line per series
# $series = one "code: name" line per series, each from export-readme-series-name
export-readme-series =
    Series (code: name):
    { $series }
export-readme-series-name =
    { $n ->
        [1] Primary (1st)
        [2] Intermediate (2nd)
        [3] Advanced A (3rd)
        [4] Advanced B (4th)
        [5] Advanced C (5th)
       *[6] Advanced D (6th)
    }
export-readme-day-off = day_off.days: 1 = Monday, 2 = Tuesday, 3 = Wednesday, 4 = Thursday, 5 = Friday, 6 = Saturday, 7 = Sunday.
export-readme-hide-ladies = hide_ladies: hide the 🌸 button (your 🌸 days are still in this file).
export-readme-standing = In progression.csv, "standing" means sun salutations and standing only.
export-readme-marked-by = marked_by: "self" = you, "teacher" = a teacher, "unknown" = an account that no longer exists.
export-readme-unreadable = unreadable = yes: this entry was saved, but a private part couldn't be read. An unreadable day status is shown as rest (never 🌸); an unreadable diary note is left empty.

invite-ask = 🤝 { $name } sent you an invite. Add them to your teachers?
invite-consent =
    If you confirm:
    • { $name } sees your name{ $me } and what you log from today on: practice or rest and your practice length.
    • { $name } also sees your last asana as marked in your log.
    • All rest you log looks the same, whatever the reason.
    • If nothing shows for a while, { $name } sees a short note saying just that.
    • Any teacher on your list can also mark a new asana for you. You get a message and can undo it.
    • Check-ins, diary notes and the reason for a rest stay private.
    • { $name } can send announcements to all their students through the bot. You can mute them.
    • You can remove { $name } from your list any time in /teachers. No one gets a message.
invite-know-them = Anyone can choose any name here, so confirm only if you know this person.
invite-not-told = If you tap Not now, { $name } isn't told.
invite-accept = ✅ Confirm
invite-decline = Not now
invite-linked = ✅ { $name } is on your list of teachers now.
invite-already = { $name } is already on your list of teachers.
invite-own = This is your own invite link: share it with your students.
invite-invalid = This invite link no longer works. The person who shared it can send a new one.
invite-full = This link can't add a teacher right now.
link-student-joined = 👥 { $name } is on your list of students now.
link-students-open = 👥 My students
invite-hint = Share this link or QR code. Each student confirms for themselves.
invite-moon-hint = Students who haven't chosen a moon city will follow the city you choose in /moon.
invite-share-text = My link to add me as your teacher in Tristhana. The bot shows what I'd see before you confirm.
invite-new-ask = Get a new link? The old link and QR stop working. People already on your list stay.
invite-qr-caption = Scan to add me as your teacher in Tristhana.
link-unlink-ask = Remove { $name } from your teachers? They won't get a message, but you'll no longer be on their list.
link-next-main = { $name } becomes your main teacher.
link-remove-ask = Remove { $name } from your students? They won't get a message.
links-empty = No teachers on your list. Your log works the same either way.
links-no-students = No students on your list.
links-primary-hint = ⭐ marks your main teacher. You can change it any time.
links-main-chosen = ⭐ Main teacher: { $name }
links-main-auto = ⭐ Main teacher: { $name } (first on your list)
links-title = 👥 Teachers and students
command-teachers = My teachers and students
link-no-name = (no name)
export-readme-links = teacher_links in data.json: your teachers and students, without names, so this list holds no one else's details.
export-readme-shalas = shalas in data.json: the shalas you're in. side: "staff" or "student"; owner: the shala is yours; roles: your roles there ("admin" = manager, "office" = front desk). No one else's names.
links-make-main = ⭐ Make main
links-remove = Remove…
links-invite-first = I teach: invite students
links-students = 👥 My students ({ $count })
links-invite = ➕ Invite students
links-remove-yes = Remove
invite-share = 📤 Share
invite-qr = 🔳 QR code
invite-new = 🔄 New link…
invite-new-yes = 🔄 Yes, new link

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
students-day-blank = { $date }: ·

## PR-08 Phase 3: a linked teacher marks a new asana for a student (spec §8). The teacher's
## screens are in the teacher's language; $series is a `series-lower`, the target's series.
students-give = 🎉 Mark new asana
students-give-pick = { $name }: which new asana? { $name } gets one message, even for a few.
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

## Shalas (SC-01, ADR-0033). Shala and people names are plain text, never declined.
shala-join-ask = 🏛 Join { $shala } (📍 { $city })?
shala-join-consent =
    If you join:
    • The shala's teachers and staff see your name{ $me }. Nothing from your log.
    • The shala's staff can send announcements to members through the bot. You can mute them.
    • Your moon days follow the shala's calendar, unless you've chosen a city, or your teacher has. If your teacher teaches here, the shala's calendar comes first.
    • The shala's staff can mark that you came to a class, and so can you. You see these marks and can remove them any time.
    • You can leave any time in /teachers. No one gets a message.
shala-know-them = Join only a shala you know: anyone can create one with any name.
shala-join-yes = ✅ Join
shala-staff-ask = 🏛 { $name } invites you to { $shala } as { $role }.
shala-staff-consent =
    If you confirm:
    • Everyone in the shala, students included, sees your name{ $me } and role.
    • You'll see the names of its students and staff, not their logs.
    • The shala's announcements come to you through the bot too. You can mute them.
    • You can mark who came to its classes.
    • You can leave any time in /teachers.
shala-staff-yes = ✅ Confirm
shala-staff-joined = 🏛 { $name } joined { $shala } as { $role }.
shala-staff-link-hint = This link adds one person as { $role }. It works once, for 7 days.
shala-staff-pick = Choose a role. The link adds one person with that role.
shala-role =
    { $role ->
        [owner] Owner
        [admin] Manager
        [teacher] Teacher
        [assistant] Assistant
       *[office] Front desk
    }
shala-role-in-list =
    { $role ->
        [owner] owner
        [admin] manager
        [teacher] teacher
        [assistant] assistant
       *[office] front desk
    }
shala-moon-shared = 🌙 Staff, and members whose teacher works here, follow this calendar unless they chose a city. Other members follow it unless they or their teacher chose one.
shala-invalid = This shala link no longer works. The person who shared it can send a new one.
shala-already = You're already in { $shala }.
shala-already-staff = You're already on the staff of { $shala }, so you don't need a student link.
shala-full = This link can't add you to the shala right now.
shala-joined = ✅ You're in { $shala }. Welcome 🙏
shala-leave = Leave…
shala-leave-ask = Leave { $shala }? No one gets a message, and your log stays as it is.
shala-leave-yes = Leave
shala-remove-ask = Remove { $name } from the shala? No one gets a message.
shala-remove-yes = Remove
shala-students = 👥 Students ({ $n })
shala-no-students = No students in this shala yet.
shala-staff-title = Teachers and staff: { $people }
shala-invite-students = ➕ Invite students
shala-invite-staff = ➕ Invite staff
shala-join-hint = Share this link or QR code. Each student confirms for themselves.
shala-share-text = Join { $shala } in Tristhana. Before you confirm, the bot shows who sees what.
shala-qr-caption = Scan to join { $shala } in Tristhana.
shala-create = 🏛 Create a shala
shala-online = 🌐 Online
shala-place = 📍 { $city }
shala-time = { $place } · shala time: { $zone }
shala-moon-line = 🌙 Moon days: 📍 { $city }
shala-delete-ask = Delete { $shala } for everyone in it? Everyone's own logs stay. No one gets a message. This can't be undone.
shala-name-invalid = The shala needs a name, up to 64 characters.
shala-caps = No more shalas or staff links for now: that's the limit.
moon-source-shala = 🏛 Same as your shala, { $shala }. You can choose another city.
moon-follow-shala = 🏛 Follow my shala ({ $shala })
settings-moon-line-shala = 🌙 Moon days: 📍 { $city } (as { $shala })

## Shala classes (SC-02). Times are wall clock in the shala's zone; { $zone } is "Almaty (UTC+5)".
## { $day } arrives formatted ("Fri, Nov 13"). No one gets a message about a change (Q122).
class-type = { $type ->
        [conference] Conference
        [pranayama] Pranayama
        [chanting] Chanting
       *[workshop] Workshop
    }
class-led-hint = Often Friday or Sunday
schedule-open = 🗓 Schedule
schedule-title = 🗓 { $shala }: schedule, { $range }
schedule-zone = Times: { $zone }
schedule-your-time = ({ $time } your time)
schedule-moon-day = 🌙 Moon day
schedule-reason = { $reason ->
        [moon] moon day
        [closure] shala closed
       *[cancelled] cancelled
    }
schedule-swap = 🔁 Instead of { $day }
schedule-swapped-to = 🔁 { $class }: moved to { $day } ({ $reason })
schedule-moved = ↪ moved from { $day } { $time }
schedule-substitute = { $name } (substitute)
schedule-day-off = 😌 Shala day off
schedule-empty = No classes these days.
shala-moon-policy = { $p ->
        [pranayama] 🌙 Moon days: pranayama, chanting and talks only
        [open] 🌙 Moon days: classes as usual
       *[closed] 🌙 Moon days: the shala is closed
    }
shala-moon-policy-note = Dates follow the shala's moon city (lunar day at sunrise). If your shala observes another day, use Hold anyway or Cancel.
shala-day-off-line = 😌 Day off: { $days }
shala-day-off-adopt = 😌 Make { $days } my day off too
class-cancel-ask = Cancel { $class } on { $day }? It shows on the schedule. No one gets a message.
class-cancel = ❌ Cancel this class
class-restore = ↩ Restore
class-hold = ✅ Hold anyway
class-cancel-pick = ❌ Cancel a class…
class-pick-title = Which class? The next 48 hours:
class-pick-empty = No classes in the next 48 hours.
class-gone = This class has just changed. Here's the current schedule.
class-caps = That's the limit for this shala for now.
class-invalid = That change doesn't fit the schedule.
# A teacher's own week (/classes), every shala where they're on the staff. Times in each shala's zone.
command-classes = The classes I teach this week
my-classes-covered = { $name } is covering
my-classes-covering = you're covering for { $name }

## My schedule (SC-03): every shala I'm in, in my zone. { $zone } is "Almaty (UTC+5)".
command-schedule = My schedule: classes of all my shalas
my-schedule-open = 🗓 My schedule
my-schedule-title = 🗓 My schedule, { $range }
my-schedule-filter = { $f ->
        [teachers] 👤 My teachers
        [mine] 🧑‍🏫 I teach
       *[all] All
    }
# After the date on a day row: a moon day of my own moon calendar.
my-schedule-my-moon = 🌙
my-schedule-teacher-mark = 👤
schedule-held-moon = · 🌙
schedule-swapped-from = 🔁 instead of { $day }
schedule-swapped-inline = 🔁 { $day }
schedule-covering-for = { $name } (for { $teacher })
# $weekday: ISO 1-7 (Russian needs it in the genitive); $date: "15 November".
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
my-schedule-none = Your schedule shows the classes of the shalas you join. Ask your shala for its link.
my-schedule-zone-unknown = Times are in { $zone }. Set your city to see your own time.
my-schedule-more = The full week is in the app.

## Calendar subscription (SC-06): a personal ICS link for Google, Apple or Outlook.
feed-open = 📅 Add to calendar
feed-title = 📅 Calendar subscription
feed-explain = Your classes and moon days in Google, Apple or Outlook Calendar. It updates by itself (Google can take up to a day).
feed-moon-only = Join a shala to see its classes here too.
feed-create = 📅 Create my link
feed-google = Add to Google Calendar
feed-google-phone = On a phone the Google button may not add it. Do it once on a computer: calendar.google.com → Other calendars + → From URL, and paste the link. Then it shows on your phone too.
feed-apple = Add to Apple / Outlook
feed-copy = 📋 Copy link
feed-private = 🔒 Anyone with this link sees your schedule. Don't share it; if it got out, make a new one.
feed-checked = { $day ->
        [none] Not used by a calendar yet
       *[other] Last checked by a calendar: { $day }
    }
feed-rotate = 🔄 New link
feed-rotate-confirm = The old link stops working. Calendars that use it need the new one.
feed-off = Turn off
feed-off-confirm = Your calendar apps will stop updating. Events already there stay until you remove the calendar.
feed-off-done = Turned off.
feed-confirm = ✅ Yes
feed-cancel = ‹ Back
# The feed's own text (event titles and descriptions), in the account's language at poll time.
ics-calendar-name = Tristhana: my schedule
ics-class = { $what } · { $teacher }
ics-desc-online = 🌐 Online
ics-desc-time = Shala time: { $time }
ics-desc-held-moon = 🌙 Held on a moon day (by the shala's calendar)

## NT-03: announcements from a teacher or a shala (plain text, relayed as written)
ann-head-teacher = 📣 { $name } · your teacher
ann-head-shala = 📣 { $shala } · { $name }
ann-head-shala-only = 📣 { $shala }
ann-mute = 🔕 Mute
ann-unmute = 🔔 Unmute
ann-muted = Muted. You'll still find them under 📣 Announcements. No one is told.
ann-unmuted = Announcements will come here again.
ann-list = 📣 Announcements
ann-list-title = 📣 Announcements: { $source }
ann-list-empty = No announcements in the last 30 days.
ann-item = 📅 { $date } · { $name }
ann-pinned-until = 📌 Pinned until { $date }
ann-announce = 📣 Announce

## SC-05: class attendance (presence only; never a log entry, never an absence)
attend-me-open = 🙋 I was there…
attend-me-title = 🙋 Mark a class you came to (today and the 6 days before)
attend-me-none = No classes to mark in the last 7 days.
attend-claimed = { $state ->
        [confirmed] ✅ Marked: { $what }.
       *[claimed] 🙋 Marked: { $what }. The shala's staff can confirm it.
    }
attend-removed = Mark removed: { $what }.
attend-state = { $s ->
        [confirmed] ✅ confirmed
       *[claimed] 🙋 your mark
    }
# My schedule: a row I marked (SC-05), after the row text.
attend-row-mark = { $state ->
        [confirmed] · ✅
       *[claimed] · 🙋
    }
attend-log-day = 🧘 Log this day
attend-staff-open = 📋 Attendance…
attend-roster-title = 📋 { $class } · { $day }, { $time }
attend-staff-pick = 📋 Which class? Last 7 days.
attend-staff-none = No classes in the last 7 days.
attend-row-counts = ✅ { $confirmed } · 🙋 { $claimed }
attend-roster-counts = ✅ { $confirmed } · { $claimed ->
        [0] nothing to confirm
        [one] 🙋 1 to confirm
       *[other] 🙋 { $claimed } to confirm
    }
attend-roster-hint = Tap a name to mark who came. 🙋 = their own mark.
attend-confirm-all = ✅ Confirm all 🙋 ({ $n })
attend-staff-tag = · staff
attend-empty = No one on the list yet. Students appear here once they join the shala.
attend-not-open = This class can't be marked now: it hasn't started, it was cancelled, or it was more than 7 days ago.

# ST-07: a share card sent to the person's own chat from the Mini App ("Send to my chat").
share-card-caption = Your Tristhana card: forward it or save it to share.

# ID-05 (ADR-0042): the directory listing. One checked, dated fact; never "badge", "verified"
# or an endorsement. $listed = the name as it stands in the directory; $when = month and year.
listing-mark = ✔ Listed in the Sharath Yoga Centre teachers directory as { $listed } (checked: { $when })
listing-level = Level (in the teacher's own words): { $level }
listing-level-name =
    { $level ->
       *[authorised] Authorised
        [authorised-1] Authorised Level 1
        [authorised-2] Authorised Level 2
        [certified] Certified
    }
listing-about = The name is in the public teachers directory of Sharath Yoga Centre (SYC); it was looked up by hand on that date. This is not an endorsement by SYC, and Tristhana has no connection with SYC. The level is the teacher's own words: the directory shows no levels. Many experienced teachers are not in this directory; the line says nothing about a teacher who doesn't have it.
listing-open = SYC directory listing
listing-title = SYC directory listing
listing-intro = If your name is in the Sharath Yoga Centre teachers directory, I can show that to your students next to your name. A person checks it by hand, so it can take a few days. Many experienced teachers are not in this directory, and everything here works the same without the line.
listing-how = The form is in the app. It asks for your name, exactly as in the directory, and the country or region.
listing-pending = Sent: «{ $listed }». A person will look it up by hand.
listing-listed-hint = Your students see this line on your invite and next to your name.
listing-not-found = I couldn't confirm the entry «{ $listed }» for this account yet. The name may be spelled differently, or the directory may have changed. You can look over the details and send them again.
listing-app = ✏️ Open the form
listing-remove = Remove…
listing-remove-ask = Remove the directory line? Students will no longer see it. You can ask again later.
listing-remove-yes = Remove
listing-removed = Removed. Students don't see the line.
listing-note-listed = ✔ «{ $listed }» is in the Sharath Yoga Centre teachers directory. Your students now see this next to your name.
listing-note-not-found = I couldn't confirm the directory entry «{ $listed }» for this account yet. The name may be spelled differently, or the directory may have changed. You can look over the details and send them again.
listing-note-ended = At today's check I couldn't find «{ $listed }» in the Sharath Yoga Centre teachers directory, so that line is no longer shown. The directory changes, and this says nothing about your teaching. Everything else stays as it is: your students, your link, your lists. If the directory shows the name again, or under another spelling, send the details any time.
export-readme-listing = directory_listing in data.json: your request for the Sharath Yoga Centre teachers directory line, if you sent one. status: "pending" = waiting for the check, "listed" = the line is shown, "not_found" = the entry couldn't be confirmed for this account, "withdrawn" = you removed it.
admin-listing-title = Directory requests: { $waiting } waiting · { $listed } listed
admin-listing-oldest = Oldest check: { $when }
admin-listing-listed-title = Listed, oldest check first. Go through the list about twice a year.
admin-listing-empty = Nothing here.
admin-listing-recheck = Listed: re-check
admin-listing-waiting = Waiting requests
admin-listing-card-name = Account name: { $name }
admin-listing-card-listed = Name as listed: { $listed }
admin-listing-card-region = Country or region: { $region }
admin-listing-card-level = Level (their own words): { $level }
admin-listing-card-note = Their note: { $note }
admin-listing-card-requested = Sent: { $date }
admin-listing-card-checked = Last check: { $when }
admin-listing-open-directory = 🌐 Open the directory
admin-listing-listed = ✔ Listed
admin-listing-still-listed = ✔ Still listed
admin-listing-not-found = Can't confirm…
admin-listing-ended = No longer listed…
admin-listing-not-found-ask = Answer «{ $listed }» as not confirmed? The teacher gets one message and can send the details again.
admin-listing-ended-ask = Remove the line for «{ $listed }»? It hides at once and the teacher gets one message. Students are told nothing.
admin-listing-yes = Yes
admin-listing-stale = This request has changed. Here is the current list.
admin-listing-done-listed = ✔ Listed: «{ $listed }».
admin-listing-done-not-found = Done: no line for «{ $listed }». The teacher gets one message.
admin-listing-new = A directory request is waiting: /admin
