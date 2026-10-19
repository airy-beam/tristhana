# Сообщения Telegram-бота (ru). Ключи должны совпадать с locales/en/bot.ftl.

start-greeting =
    Намасте 🙏
    Я Тристхана, твой спутник в практике аштанги. Хорошо, что ты здесь.

start-prompt =
    { $day }
    Практика или отдых? В журнал идёт и то, и другое.
# Кнопка другого языка; $language — название языка на нём самом («English»).
start-switch-language = 🗣 { $language }
# Кнопка Mini App: под /start и под сохранённым днём, пока часовой пояс неизвестен.
start-open-app = Открыть приложение

help-text =
    Я Тристхана, спутник твоей практики аштанги.
    📝 /log: сегодня или прошедший день
    🔔 /remind: ежедневное напоминание о практике
    🌙 /moon: ближайшие лунные дни и напоминания
    ⚙️ /settings: язык, часовой пояс, напоминания
    📊 Журнал практики и статистика — в приложении (кнопка рядом с полем ввода).

fallback-text = Я пока не умею отвечать на сообщения. Попробуй /start или /help 🙏

# База данных недоступна; человеку достаточно попробовать ещё раз.
error-temporary = Прости, у меня небольшая заминка. Попробуй ещё раз через минуту.

## Статус дня (PR-01). Даты приходят уже отформатированными («вс, 18 окт.»).


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
log-cleared = Отметка убрана.
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

length-pick =
    Где закончилась практика?
    ☀️ Короткая: Сурья Намаскар, стоячие и завершающие.
preset-short = ☀️ Короткая → стоячие
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
        [4] Четвёртая
        [5] Пятая
       *[6] Шестая
    }
series-lower =
    { $n ->
        [1] первая
        [2] вторая
        [3] третья
        [4] четвёртая
        [5] пятая
       *[6] шестая
    }
series-half =
    { $n ->
        [1] первой
        [2] второй
        [3] третьей
        [4] четвёртой
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
moon-calc-note = Даты рассчитаны по городу 📍 { $city } (лунный день на восходе). Календарь твоей шалы может отличаться на день: ориентируйся на своего учителя.
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
moon-reminders-on = 🔔 Напоминания: { $offsets } в { $time }
moon-reminders-off = 🔕 Напоминания выключены
moon-zone-needed = Чтобы напоминать в нужный час, мне нужен твой часовой пояс: выбери свой город или открой приложение один раз.
moon-change-city = 📍 Сменить город
moon-reminders = 🔔 Напоминания
moon-pick-city = По какому городу считать лунные дни?
# Кнопка во всю ширину: ставит часовой пояс города (только если пояс неизвестен).
moon-use-city-zone = 🕐 Часовой пояс: 📍 { $city }
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
moon-reminder-intro = В аштанге в полнолуние и новолуние традиционно отдыхают. Я напомню { $offsets }. Изменить можно одной кнопкой ниже.
moon-reminder-only-1 = ✓ Буду напоминать только накануне.
moon-reminder-off = 🔕 Напоминания о лунных днях выключены. Включить снова можно в /moon.
moon-reminder-on = 🔔 Напоминания о лунных днях снова включены.

## Напоминание о практике (PR-10). { $day } и { $date } приходят отформатированными («пн, 19 окт.»); { $d } — день недели по ISO (1 = понедельник).
command-remind = Ежедневное напоминание о практике
remind-practice = 🌿 { $day }: практика или отдых? Отметить можно одним нажатием.
remind-same = ✅ Практика, как в прошлый раз
remind-practiced = 🧘 Практика…
remind-other = 📅 Другое…
remind-turn-off = 🔕 Выключить
remind-turn-on = 🔔 Включить
remind-turn-back-on = 🔔 Включить снова
remind-off-note = 🔕 Напоминания о практике выключены. Включить снова можно в /remind.
remind-on-again = 🔔 Напоминания о практике снова включены.
# После 10 напоминаний подряд без отметок: одно сообщение, затем напоминания выключаются.
remind-paused = 🌿 Пока перестану спрашивать. Захочешь вернуть напоминание — нажми кнопку ниже или открой /remind.
# Без точки в конце: дата Babel уже заканчивается на «окт.» / «г.».
remind-copied-from = Скопировано из практики { $date }
remind-offer = 🔔 Спрашивать раз в день, чтобы отмечать одним нажатием?
remind-offer-yes = 🔔 Да, напоминай
remind-offer-no = Нет, спасибо
remind-explain = Раз в день спрошу, как прошёл день: ответить можно одним нажатием. В лунные дни и в уже отмеченные дни не пишу.
remind-status-on = 🔔 Напоминание о практике: { $days } в { $time }
remind-status-off = 🔕 Напоминание о практике выключено
remind-local-time = { $time } по твоему времени
remind-every-day = каждый день
remind-days-except = каждый день, кроме { remind-weekday-except }
remind-weekday-except = { $d ->
        [1] понедельника
        [2] вторника
        [3] среды
        [4] четверга
        [5] пятницы
        [6] субботы
       *[7] воскресенья
    }
remind-weekday = { $d ->
        [1] пн
        [2] вт
        [3] ср
        [4] чт
        [5] пт
        [6] сб
       *[7] вс
    }
remind-day-off = Выходной: { remind-weekday }
remind-moon-link = 🌙 Лунные напоминания
remind-practice-link = 🧘 Напоминание о практике

## Настройки (ID-06).
command-settings = Язык, часовой пояс, напоминания
settings-title = ⚙️ Настройки
language-auto = Как в Telegram
language-en = English
language-ru = Русский
settings-language-line = 🗣 Язык: { $language }
settings-zone-line = 🕐 Часовой пояс: { $zone }
settings-zone-unset-line = 🕐 Часовой пояс: пока не задан. Напоминания начнутся, как только он появится.
settings-moon-line = 🌙 Лунные дни: 📍 { $city }
settings-quiet-line = 🔕 Тихие часы { $start }–{ $end } · { $n ->
        [one] не больше { $n } сообщения в день
       *[other] не больше { $n } сообщений в день
    }
settings-quiet-off-line = 🔕 Без тихих часов · { $n ->
        [one] не больше { $n } сообщения в день
       *[other] не больше { $n } сообщений в день
    }
settings-zone-button = 🕐 Часовой пояс
settings-moon-link = 🌙 Лунные дни
settings-pick-zone = Выбери город, по времени которого живёшь. Нет в списке? Открой приложение: оно возьмёт пояс телефона.
settings-open-app = ⚙️ Ещё в приложении
settings-link = ⚙️ Настройки
