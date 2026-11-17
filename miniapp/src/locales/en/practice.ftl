## The Practice tab (UI-06 stage 3): copy that loads with its chunk, not with the first one.
## Runs say "in a row", never "streak"/"broken"/"missed".
stats-month-prev = ‹
    .aria-label = Previous month
stats-month-next = ›
    .aria-label = Next month
stats-more = The month in numbers
# The row that opens the year; $year is text ("2026"), $n the year's practices.
stats-year-open = { $n ->
        [0] 📅 { $year } · the whole year
        [one] 📅 { $year } · { $n } practice
       *[other] 📅 { $year } · { $n } practices
    }
# On the card of a day that is a moon day in the followed city.
stats-day-moon = { $phase ->
        [purnima] 🌕 Full moon · 📍 { $city }
       *[amavasya] 🌑 New moon · 📍 { $city }
    }
# The legend's accessible name.
stats-legend-label = What the marks mean
# Under the device-only 🌸 switch (Settings → More).
stats-show-ladies-hint = On this phone only. While it's off, these days look like rest.
