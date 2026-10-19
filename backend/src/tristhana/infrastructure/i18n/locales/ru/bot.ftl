# Сообщения Telegram-бота (ru). Ключи должны совпадать с locales/en/bot.ftl.

start-greeting =
    Намасте 🙏
    Я Тристхана, твой спутник в практике аштанги. Хорошо, что ты здесь.

# Кнопка под приветствием /start, открывает Mini App.
start-open-app = Открыть приложение

help-text =
    Я Тристхана, спутник твоей практики аштанги: дыхание, бандха, дришти.
    /log: отметь, каким был день (практика, отдых, лунный день…) — сегодня или любой прошедший.
    /moon: ближайшие лунные дни и напоминания.

fallback-text = Я пока не умею отвечать на сообщения. Попробуй /start или /help 🙏

# База данных недоступна; человеку достаточно попробовать ещё раз.
error-temporary = Прости, у меня небольшая заминка. Попробуй ещё раз через минуту 🙏

## Статус дня (PR-01). Даты приходят уже отформатированными («вс, 18 окт.»).

# Кнопка под приветствием /start.
start-log-today = 📝 Отметить сегодня

day-label =
    { $rel ->
        [today] Сегодня, { $date }
        [yesterday] Вчера, { $date }
       *[other] { $date }
    }

log-prompt =
    { $day }
    Как прошёл твой день?

status-practiced = 🧘 Практика
status-rest = 😌 День отдыха
status-moon = 🌙 Лунный день
status-ladies = 🌸 Женские дни
status-sick = 🤒 Болезнь / травма
status-travel = ✈️ В дороге
status-skipped = 🌱 Без практики

log-saved =
    ✓ { $day }: { $label }
    { $status ->
        [practiced] Практика сделана 🙏
        [sick] Выздоравливай 🌿
        [travel] Хорошей дороги ✈️
        [skipped] Каждый день разный 🌱
       *[other] Отдых — тоже часть практики 🌿
    }
log-private-note = Это видишь только ты. Остальные видят «День отдыха».
log-zone-hint = Совет: открой приложение один раз — так я узнаю твой часовой пояс, и отметки встанут на верные даты.
log-cleared = Отметка убрана: { $day }.
log-date-future = В твоём часовом поясе этот день ещё не наступил.
log-date-too-early = Я храню дни начиная с 2000 года.

log-another-day = 📅 Другой день
log-change = ✏️ Изменить
log-clear = Убрать отметку
log-pick-day = Какой день?
log-earlier = ‹ Раньше
log-later = Позже ›

## Меню команд бота (setMyCommands, через tools/telegram/set_webhook.py). По одной строке.
command-log = Отметить сегодня или прошедший день
command-help = Что я умею
command-start = Начать

## Детали практики (PR-02, PR-03, PR-05). Названия асан берутся из каталога.

practice-details-prompt = Добавишь детали? Это необязательно, хватит одного нажатия.
practice-last-time = В прошлый раз: { $summary }
practice-same-as-last = 🔁 Как в прошлый раз
context-mysore = Майсор
context-led = Лед-класс
context-private = Индивидуально
context-self = Самостоятельно
practice-online = 🌐 Онлайн
practice-online-suffix = онлайн
practice-length = 📏 Объём практики
practice-duration = ⏱ Длительность
practice-done = ✓ Готово
practice-details = 📝 Детали
practice-clear = Убрать детали
practice-day-not-practiced = Этот день больше не отмечен как практика.
practice-no-previous = Пока нечего копировать: это первая практика с деталями.

length-pick = Где закончилась практика?
preset-short = ☀️ Короткая: приветствия солнцу, стоячие, завершающие
preset-half-primary = ½ первой → Навасана
preset-full-primary = Первая серия целиком
preset-other = 🎯 Другое…
length-pick-series = Какой серией закончилась практика?
length-pick-range = Что было в практике?
length-only = Только { $series }
length-pick-asana = Последняя асана ({ $series }):
length-full-series = Вся серия
log-back = ‹ Назад

duration-pick = Сколько длилась практика?
duration-min = { $min } мин
duration-none = Без длительности

# Названия серий: `series-name` в начале фразы, `series-lower` внутри,
# `series-half` после «½» (родительный падеж).
series-name =
    { $n ->
        [1] Первая
        [2] Вторая
        [3] Третья
        [4] Четвертая
        [5] Пятая
       *[6] Шестая
    }
series-lower =
    { $n ->
        [1] первая
        [2] вторая
        [3] третья
        [4] четвертая
        [5] пятая
       *[6] шестая
    }
series-half =
    { $n ->
        [1] первой
        [2] второй
        [3] третьей
        [4] четвертой
        [5] пятой
       *[6] шестой
    }
half-first = 1-я половина { $series }
half-second = 2-я половина { $series }

length-summary =
    { $kind ->
        [short] Короткая практика
        [full-one] { $range } серия целиком
        [full] { $range } (полностью)
       *[to] { $range } → { $asana }
    }

time-label = { $time }

# Paging in the asana grid.
page-prev = ◀
page-next = ▶

## Лунные дни и напоминания (MD-03). Названия городов берутся из data/seed/cities.yaml.

command-moon = Лунные дни и напоминания
moon-title = 🌙 Лунные дни · 📍 { $city }
moon-phase =
    { $phase ->
        [purnima] 🌕 Полнолуние
       *[amavasya] 🌑 Новолуние
    }
moon-phase-lower =
    { $phase ->
        [purnima] 🌕 полнолуние
       *[amavasya] 🌑 новолуние
    }
moon-phase-long =
    { $phase ->
        [purnima] 🌕 Полнолуние (Пурнима)
       *[amavasya] 🌑 Новолуние (Амавасья)
    }
moon-in-days =
    { $n ->
        [0] сегодня
        [1] завтра
        [one] через { $n } день
        [few] через { $n } дня
       *[other] через { $n } дней
    }
moon-day-line = { $phase } · { $date } · { $in }
moon-none = В ближайшие два месяца лунных дней пока нет: календарь готовится.
moon-calc-note = Даты рассчитаны для 📍 { $city } (лунный день на восходе). Календарь твоей шалы может отличаться на день, ориентируйся на своего учителя.
moon-offsets =
    { $code ->
        [731] за 7, 3 и 1 день
        [71] за неделю и за день
        [73] за 7 и 3 дня
        [31] за 3 дня и за день
        [7] за неделю
        [3] за 3 дня
       *[1] за день
    }
moon-reminders-on = 🔔 Напоминания: { $offsets }, в { $time }
moon-reminders-off = 🔕 Напоминания выключены
moon-zone-needed = Чтобы напоминать в нужный час, мне нужен твой часовой пояс: выбери свой город или открой приложение один раз.
moon-change-city = 📍 Сменить город
moon-reminders = 🔔 Напоминания
moon-pick-city = По какому городу считать лунные дни?
# Кнопка во всю ширину: ставит часовой пояс города (только если пояс неизвестен).
moon-use-city-zone = 🕒 Часовой пояс: 📍 { $city }
moon-offset =
    { $n ->
        [one] за { $n } день
        [few] за { $n } дня
       *[other] за { $n } дней
    }
moon-turn-on = 🔔 Включить
moon-turn-off = 🔕 Выключить
moon-only-day-before = Только накануне
moon-all-days = 🌙 Все лунные дни
moon-turn-back-on = 🔔 Включить снова
moon-reminder =
    { $days ->
        [7] { $phase } через неделю: { $date } · 📍 { $city }
        [3] { $phase } через 3 дня: { $date } · 📍 { $city }. Традиционный день отдыха.
       *[1] Завтра { $phase-lower }, { $date } · 📍 { $city }. Хорошего отдыха 🌿
    }
moon-reminder-intro = В аштанге в полнолуние и новолуние традиционно не практикуют. Я напомню { $offsets }, изменить можно одной кнопкой ниже.
moon-reminder-only-1 = ✓ Буду напоминать только накануне.
moon-reminder-off = 🔕 Напоминания о лунных днях выключены. Включить снова можно в /moon.
moon-reminder-on = 🔔 Напоминания о лунных днях снова включены.
