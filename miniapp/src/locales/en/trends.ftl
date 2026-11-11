## ST-05: check-ins over time. Loaded with the lazy Trends screen (`trends-open` is in app.ftl).
## Figures only: no comparison, explanation or advice in words.
trends-title = Check-ins over time
trends-window = The last 12 months, from the check-ins you add after practice.
trends-by-month = By month
trends-by-weekday = By weekday
trends-by-moon = Near full and new moon
# Read aloud, so no emoji here: a screen reader would spell the emoji out.
trends-scale = { $scale ->
        [mood] Mood
        [energy] Energy
       *[effort] Effort
    }
# The row label in the narrow tables; the name above is read aloud.
trends-scale-icon = { $scale ->
        [mood] 💭
        [energy] ⚡
       *[effort] 🔥
    }
# Above the mood strip: the ends of its axis (energy and effort reuse checkin-energy / checkin-effort).
trends-mood-ends = 💭 Mood: 1 😔 → 5 😊
trends-moon-full = 🌕 Near full moon
trends-moon-new = 🌑 Near new moon
trends-moon-other = Other days
# The same three columns as read aloud: no emoji.
trends-moon-spoken = { $bucket ->
        [full] Near full moon
        [new] Near new moon
       *[other] Other days
    }
trends-moon-note = "Near" is the day of the full or new moon, the day before and the day after. Dates for 📍 { $city }.
trends-count-hint = The small number under each average is how many check-ins it comes from.
# Read aloud for one figure. { $where } is a month, a weekday or a moon column.
trends-cell-label = { $n ->
        [one] { $scale }, { $where }: { $mean } on average, { $n } check-in
       *[other] { $scale }, { $where }: { $mean } on average, { $n } check-ins
    }
# A cell with too few check-ins behind it.
trends-none = —
trends-cell-none = { $scale }, { $where }: no average
trends-gap-note = "—" means fewer than { $min } check-ins there.
trends-empty = Nothing here yet. Averages of the check-ins you add after practice will show up on this screen.
trends-too-few = Averages appear here from { $min } check-ins.
trends-note = These are averages of your own check-ins. The app draws no conclusions from them. Teachers and shalas don't see them.
trends-load-failed = Couldn't load this. Try again in a moment.
