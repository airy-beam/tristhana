## Settings (UI-06 stage 3): copy that loads with the Settings chunk, not with the first one.
## The first screen is the bot's five rows. These fifteen messages are the bot's own, word for
## word, under the bot's keys (`bot.ftl`); `site/src/lib/guide.test.mjs` keeps the two in step.
settings-language-line = 🗣 Language: { $language }
# $zone = "Astana" for the person's own city (no offset, ADR-0044), "Almaty (UTC+5)" otherwise.
settings-city-line = 🏙 My city: { $zone }
settings-city-unset-line = 🏙 My city? 🕐 { $zone }
settings-city-unlisted-line = 🕐 My time: { $zone }
settings-city-no-zone-line = 🏙 My city? 🕐 not known yet
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
settings-reminders-button = 🔔 Reminders
settings-more-button = More…
settings-reminders-title = 🔔 Reminders
settings-more-title = ⚙️ More settings
settings-quiet-line = 🔕 Quiet hours { $start }–{ $end } · { $n ->
        [one] at most { $n } message a day
       *[other] at most { $n } messages a day
    }
settings-quiet-off-line = 🔕 No quiet hours · { $n ->
        [one] at most { $n } message a day
       *[other] at most { $n } messages a day
    }

## The app's own.
# Reminders: the place, once, for every time on the page (ADR-0044). $zone = "Almaty".
settings-times-place = 🕐 Times: { $zone }
settings-log-title = Your log
settings-privacy-open = 🔒 What others see
