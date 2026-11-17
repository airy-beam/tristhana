## Настройки (UI-06, этап 3): тексты загружаются вместе с экраном настроек, не с первым экраном.
## Первый экран — пять строк бота. Эти пятнадцать сообщений взяты из бота слово в слово, под
## его же ключами (`bot.ftl`); за совпадением следит `site/src/lib/guide.test.mjs`.
settings-language-line = 🗣 Язык: { $language }
# $zone = «Астана» для своего города (без смещения, ADR-0044), иначе «Алматы (UTC+5)».
settings-city-line = 🏙 Мой город: { $zone }
settings-city-unset-line = 🏙 Мой город? 🕐 { $zone }
settings-city-unlisted-line = 🕐 Моё время: { $zone }
settings-city-no-zone-line = 🏙 Мой город? 🕐 пока неизвестно
settings-day-off-line = 😌 Выходной: { day-off-weekday }
settings-days-off-line = 😌 Выходные: { day-off-weekday }, { $e ->
        [1] понедельник
        [2] вторник
        [3] среда
        [4] четверг
        [5] пятница
        [6] суббота
       *[7] воскресенье
    }
settings-day-off-none-line = 😌 Без постоянного выходного
settings-day-off-unset-line = 😌 Выходной: не выбран
settings-reminders-button = 🔔 Напоминания
settings-more-button = Ещё…
settings-reminders-title = 🔔 Напоминания
settings-more-title = ⚙️ Ещё настройки
settings-quiet-line = 🔕 Тихие часы { $start }–{ $end } · { $n ->
        [one] не больше { $n } сообщения в день
       *[other] не больше { $n } сообщений в день
    }
settings-quiet-off-line = 🔕 Без тихих часов · { $n ->
        [one] не больше { $n } сообщения в день
       *[other] не больше { $n } сообщений в день
    }

## Только в приложении.
# Напоминания: место названо один раз для всех времён на странице (ADR-0044). $zone = «Алматы».
settings-times-place = 🕐 Время: { $zone }
settings-log-title = Твой журнал
# Reminders: the heading of the moon reminders' card.
remind-moon-title = 🌙 Лунные напоминания
settings-privacy-open = 🔒 Что видят другие
