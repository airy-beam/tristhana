## Вкладка «Практика» (UI-06, этап 3): тексты, которые грузятся вместе с ней, а не с первым чанком.
## Только «подряд», никогда «серия», «полоса», «пропуск».
stats-month-prev = ‹
    .aria-label = Предыдущий месяц
stats-month-next = ›
    .aria-label = Следующий месяц
stats-more = Месяц в цифрах
# Вместо числа практик, когда в месяце отмечен отдых (или «Без практики»), а практик нет.
stats-month-rest = Отдых тоже часть практики.
# The row that opens the year; $year is text ("2026"), $n the year's practices.
stats-year-open = { $n ->
        [0] 📅 { $year } · весь год
        [one] 📅 { $year } · { $n } практика
        [few] 📅 { $year } · { $n } практики
       *[many] 📅 { $year } · { $n } практик
    }
# On the card of a day that is a moon day in the followed city.
stats-day-moon = { $phase ->
        [purnima] 🌕 Полнолуние · 📍 { $city }
       *[amavasya] 🌑 Новолуние · 📍 { $city }
    }
# The legend's accessible name.
stats-legend-label = Что означают отметки
# Under the device-only 🌸 switch (Settings → More).
stats-show-ladies-hint = Только на этом телефоне. Пока выключено, эти дни выглядят как отдых.
