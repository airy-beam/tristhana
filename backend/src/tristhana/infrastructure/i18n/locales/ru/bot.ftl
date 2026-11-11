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
    🔔 /remind: напоминание о практике
    🧘 /asanas: мои асаны, отметить новую
    🌙 /moon: ближайшие лунные дни и напоминания
    👥 /teachers: твои учителя и ученики
    🗓 /schedule: занятия всех твоих шал, по твоему времени
    🧑‍🏫 /classes: занятия, которые ты ведёшь на этой неделе
    ⚙️ /settings: язык, город, напоминания
    📊 Журнал практики и статистика — в приложении (кнопка рядом с полем ввода).

# UI-05: a link under /help to the public guide site, in the person's language.
help-guide = 📖 Справка

## Quick tour (UI-02). Never names the ladies' holiday (a private topic in a tour for everyone).

tour-open = 🧭 Знакомство
tour-progress = { $n } из { $total }
tour-next = Дальше ›
tour-back = ‹ Назад
tour-done = ✓ Готово
tour-log =
    📝 Журнал
    Практика или отдых? В журнал идёт и то, и другое. Майсор, лед-класс или самостоятельно, коротко или полностью: всё это практика. После практики можно добавить детали, самочувствие и личную заметку. Нужен прошлый день? Открой /log.
tour-rest =
    🌿 Отдых и лунные дни
    Отдых — часть практики. Полнолуние и новолуние — традиционные дни отдыха: они отмечаются сами, и твой выходной тоже, если выбрать его в /settings. Если день прошёл иначе, просто отметь его. Даты и лунные напоминания — в /moon.
tour-remind =
    🔔 Напоминания
    Если хочешь, /remind будет раз в день спрашивать, как всё прошло: ответить можно одним нажатием. Напоминание приходит в дни практики, но не в лунные дни. Несколько дней без практики, например болезнь или дорога? Отметь первый день, и я предложу паузу.
tour-asanas =
    🧘 Мои асаны
    /asanas помнит твою последнюю асану, и отмечать практику проще. Новая асана от учителя? Отметь её там 🎉
tour-app =
    📊 Приложение
    Весь твой год на одном экране, итоги месяца и календарь для прошлых дней. Всё, что ты отмечаешь здесь, есть и там. Знакомство всегда можно открыть в /help.

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

## The bot's profile (UI-05), set by tools/telegram/set_webhook.py --texts, not shown by
## the bot itself. Description: the empty chat above Start, up to 512 characters. About: the
## profile, one line, up to 120. Public texts: 🌸 is never named here.
bot-description =
    Тристхана — спутник твоей практики аштанги.

    🧘 Отмечай практику или отдых одним нажатием
    🌙 Лунные дни для твоего города, с напоминаниями
    📊 Твой год, твой месяц, твои асаны
    👥 Учителя и шалы: расписание, посещения, объявления

    Журнал — твой. Учитель видит только то, на что ты соглашаешься.

    Справка: tristhana.app/ru/
bot-about = Твой спутник в аштанге: журнал практики и отдыха, лунные дни, твои асаны. Справка: tristhana.app/ru/

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
    ☀️ Короткая: Сурья Намаскар, стоячие, прогибы по желанию и завершающие.
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
# MD-04: свой город, если это не тот, по которому считаются лунные дни. Город не склоняется.
moon-same-as-city = 📍 Как мой город ({ $city })
moon-home-fyi = ℹ 📍 { $city }: { $date }
# Кнопка во всю ширину: ставит часовой пояс города (только если пояс неизвестен).
moon-use-city-zone = 🕐 Часовой пояс: 📍 { $city }

## Лунный календарь учителя (MD-02). Имена в именительном падеже, без «у» перед ними; если имени нет, `link-no-name`.
moon-source-teacher = 👥 Как у основного учителя: { $name }. Можно выбрать другой город.
moon-source-teacher-none = 👥 У учителя ({ $name }) пока не выбран город, поэтому даты считаются по городу 📍 { $city }.
moon-follow-teacher = 👥 Как у учителя ({ $name })
moon-teacher-shared =
    { $chosen ->
        [yes] 👥 У учеников, которые не выбрали город, лунные дни как у тебя: 📍 { $city }.
        [follow] 👥 У учеников лунные дни считаются по городу 📍 { $city }. Можно оставить так или выбрать свой город в /moon.
       *[no] 👥 У учеников лунные дни считаются по городу 📍 { $city }, как и у тебя. Можно оставить так или выбрать свой город в /moon.
    }
moon-follow-changed = 🌙 Лунные дни теперь как у учителя ({ $name }): 📍 { $city }. Поменять можно в /moon.
moon-follow-ended = 🌙 Лунные дни теперь считаются по городу 📍 { $city }. Поменять можно в /moon.
moon-teacher-own = 🌙 Теперь, когда у тебя есть ученики, лунные дни считаются по твоей настройке: 📍 { $city }. Чтобы оставить 📍 { $kept }, как у учителя ({ $name }), нажми кнопку ниже.
moon-keep-city = Оставить 📍 { $city }
moon-kept = 🌙 Готово: лунные дни остаются по городу 📍 { $city }. Поменять можно в /moon.
moon-keep-already = 🌙 Город для лунных дней уже выбран: 📍 { $city }. Поменять можно в /moon.
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
command-remind = Напоминание о практике
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
remind-explain = Раз в день спрошу, как прошёл день: ответить можно одним нажатием. Не пишу в лунные дни, в уже отмеченные дни и пока стоит пауза.
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
remind-moon-link = 🌙 Лунные напоминания
remind-days-follow = Они приходят в дни практики. Поменять дни — кнопка «😌 Выходной».
remind-practice-link = 🧘 Напоминание о практике

## Настройки (ID-06).
command-settings = Язык, город, напоминания
settings-title = ⚙️ Настройки
language-auto = Как в Telegram
language-en = English
language-ru = Русский
settings-language-line = 🗣 Язык: { $language }
# MD-04 (ADR-0029): город задаёт часовой пояс. $zone = «Астана (UTC+5)».
settings-city-line = 🏙 Мой город: { $zone }
settings-city-unset-line = 🏙 Мой город: пока не выбран · 🕐 { $zone }
settings-city-unlisted-line = 🏙 Мой город: не выбран · 🕐 { $zone }
settings-city-no-zone-line = 🏙 Мой город: пока не выбран. Напоминания начнутся, когда ты его выберешь.
settings-city-nudge = Если хочешь, выбери свой город: рядом со временем будет его название.
settings-city-not-now = Не сейчас
settings-moon-line = 🌙 Лунные дни: 📍 { $city }
settings-moon-line-teacher = 🌙 Лунные дни: 📍 { $city } (как у учителя: { $name })
settings-quiet-line = 🔕 Тихие часы { $start }–{ $end } · { $n ->
        [one] не больше { $n } сообщения в день
       *[other] не больше { $n } сообщений в день
    }
settings-quiet-off-line = 🔕 Без тихих часов · { $n ->
        [one] не больше { $n } сообщения в день
       *[other] не больше { $n } сообщений в день
    }
settings-city-button = 🏙 Мой город
settings-moon-link = 🌙 Лунные дни
settings-pick-city = В каком городе ты живёшь? Напоминания и время идут по его часам.
settings-city-unlisted = 📍 Моего города нет в списке
settings-city-utc = 🌐 UTC
settings-share-location = Пришли геопозицию один раз, и я поставлю по ней часовой пояс. Она нужна только для этого, и я её не храню. Не получается отправить с этого устройства? Открой приложение: оно возьмёт время телефона.
settings-share-location-button = 📍 Отправить геопозицию
settings-location-zone = 🕐 Готово: часовой пояс теперь { $zone }. Изменить можно в /settings.
settings-location-unknown = Не удалось найти там часовой пояс. Выбери город в /settings или открой приложение.
settings-open-app = ⚙️ Ещё в приложении
settings-link = ⚙️ Настройки

## Выходной и автоотдых (PR-09).
day-off-weekday = { $d ->
        [1] понедельник
        [2] вторник
        [3] среда
        [4] четверг
        [5] пятница
        [6] суббота
       *[7] воскресенье
    }
day-off-weekly = { $d ->
        [1] по понедельникам
        [2] по вторникам
        [3] по средам
        [4] по четвергам
        [5] по пятницам
        [6] по субботам
       *[7] по воскресеньям
    }
day-off-button = { $d ->
        [1] Понедельник
        [2] Вторник
        [3] Среда
        [4] Четверг
        [5] Пятница
        [6] Суббота
       *[7] Воскресенье
    }
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
settings-day-off-button = 😌 Выходной
day-off-pick = 😌 Какой день у тебя выходной? Можно отметить один или два; нажми ещё раз, чтобы снять. Остальные дни — дни практики.
day-off-none = Без постоянного выходного
day-off-explain = Выходные отмечаются как отдых в журнале и статистике, а напоминания о практике приходят только в дни практики. { $first ->
        [yes] Прошлые недели тоже отметятся.
       *[no] Изменение действует с сегодняшнего дня, прошлые недели остаются как были.
    } Если день прошёл иначе, просто отметь его. Без постоянного выходного напоминания приходят каждый день, кроме лунных дней.
log-auto-moon = 🌙 Лунный день (📍 { $city }) — традиционно день отдыха{ $dayoff ->
        [yes] , к тому же твой выходной
       *[no] {""}
    }. Если была практика, отметь ниже.
log-auto-day-off = 😌 Твой выходной — отмечен как отдых. Если день прошёл иначе, отметь ниже.
day-off-ask = { $reminders ->
        [on] 😌 Напоминания о практике не приходят { day-off-weekly }. Это твой выходной?
       *[off] 😌 Твой выходной — { day-off-weekday }?
    }
day-off-ask-yes = Да
day-off-ask-instead = { $d ->
        [6] Суббота
       *[7] Воскресенье
    }
day-off-ask-other = Другой…
day-off-ask-later = Не сейчас

## WH-01 part 2: несколько дней 🌸 / болезни / поездки с паузой напоминаний (черновик спеки §7)
pause-ask = { $reminders ->
        [on] ⏸ На сколько дней приостановить напоминания о практике, включая { $rel ->
            [yesterday] вчерашний день
           *[today] сегодня
        }? Эти дни отметятся как „{ $label }“, если не отметишь иначе.
       *[off] Сколько дней отметить как „{ $label }“, включая { $rel ->
            [yesterday] вчерашний день
           *[today] сегодня
        }?
    }
pause-days = { $n ->
        [one] { $n } день
        [few] { $n } дня
       *[many] { $n } дней
    }
pause-other = Другое…
pause-back = ‹ Назад
pause-only = { $rel ->
        [yesterday] Только вчера
       *[today] Только сегодня
    }
pause-set = ⏸ { $reminders ->
        [on] Напоминания о практике на паузе по { $until } включительно.
       *[off] Готово, по { $until } включительно.
    } Эти дни отмечаются как „{ $label }“; любой день можно отметить иначе.
log-auto-period = „{ $label }“ по { $until } включительно. Если день прошёл иначе, отметь ниже.
pause-end = { $reminders ->
        [on] ⏹ Завершить паузу
       *[off] ⏹ Закончить раньше
    }
pause-ended = { $reminders ->
        [on] ▶️ Напоминания о практике снова приходят с сегодняшнего дня.
       *[off] ⏹ Готово: с сегодняшнего дня отметка „{ $label }“ снята.
    }
pause-cut = ⏸ Практика отмечена на { $rel ->
        [yesterday] вчера
        [other] этот день
       *[today] сегодня
    }, поэтому следующие дни, по { $until } включительно, больше не отмечены как „{ $label }“. Оставить как было?
pause-keep = ⏸ Оставить паузу
pause-kept = ⏸ Пауза сохранена: „{ $label }“ по { $until } включительно.
remind-paused-until = ⏸ На паузе по { $until } включительно
remind-resume = ▶️ Возобновить сейчас
settings-ladies-line = 🌸 Кнопка „Женские дни“: { $shown ->
        [yes] показана
       *[no] скрыта
    }
settings-ladies-hide = 🌸 Скрыть кнопку
settings-ladies-show = 🌸 Показать кнопку

## После практики: самочувствие (PR-06). Всегда по желанию, без упрёков.
# Настроение хранится как 1–5; эмодзи только для показа. Метки: ключи домена.
checkin-prompt = Как ты после практики? По желанию.
checkin-explain = ⚡ Энергия: 1 мало → 5 много · 🔥 Усилие: 1 легко → 5 тяжело. Отметь, что подходит, всё по желанию.
checkin-mood-chip = { $n ->
        [1] 😔
        [2] 😕
        [3] 😐
        [4] 🙂
       *[5] 😊
    }
checkin-energy-chip = ⚡{ $n }
checkin-effort-chip = 🔥{ $n }
checkin-summary-energy = ⚡ энергия { $n }/5
checkin-summary-effort = 🔥 усилие { $n }/5
checkin-edit = ✨ Самочувствие
checkin-tags-open = 🏷 Тело и ум…
checkin-tags-pick = Как тело и ум? Отметь, что подходит.
checkin-clear = Убрать самочувствие
checkin-tag = { $tag ->
        [stiff] Скованность
        [open] Раскрытость
        [strong] Сила
        [light] Лёгкость
        [heavy] Тяжесть
        [sore] Ноющие мышцы
        [focused] Собранность
        [calm] Спокойствие
        [scattered] Рассеянность
       *[steady_breath] Ровное дыхание
    }
settings-checkin-line = ✨ Самочувствие после практики: { $offered ->
        [yes] предлагаю
       *[no] не предлагаю
    }
settings-checkin-off = ✨ Не предлагать
settings-checkin-on = ✨ Предлагать

## Дневник (PR-07). Личная заметка на день, при любом статусе. Не просим и не повторяем текст.
# $rel = today | yesterday | other, $date = дата (как в day-label).
diary-button = 📓 Заметка
diary-preview = 📓 { $text }
diary-empty = Заметки за этот день нет. Можно записать что угодно: как прошла практика, что сказал учитель, новая асана или просто мысль.
diary-unreadable = Эту заметку сейчас не получается прочитать. Можно написать новую или удалить старую.
diary-prompt = Напиши заметку за { $rel ->
        [today] сегодня
        [yesterday] вчера
       *[other] { $date }
    } в ответ на это сообщение. Она личная, только для тебя.
diary-prompt-replace = Она заменит текущую. Текст заметки выше можно скопировать и поправить.
diary-placeholder = Твоя заметка…
diary-saved = 📓 Сохранено в дневнике.
diary-write = ✏️ Написать
diary-rewrite = ✏️ Переписать
diary-clear = Удалить заметку
diary-clear-confirm = Удалить заметку?
diary-clear-yes = Удалить
diary-removed = Заметка удалена из дневника. Сообщения выше в чате остаются, их можно удалить в Telegram.
diary-too-long = Для одной заметки длинновато: до { $max } символов. Текст остался выше, можно сократить и отправить снова.
diary-text-only = Пока заметки бывают только текстом. Напиши её ответом на сообщение выше.

## Прогресс (PR-08) и праздники (GM-01). Названия асан, элементов и серий — из каталога;
## $series — это `series-name`, $traditional — традиционное название или "none".

command-asanas = Мои асаны: где заканчивается практика
progression-title = 🧘 Мои асаны
progression-unset = Где сейчас заканчивается твоя практика? Укажи это один раз, а новые асаны потом отмечай здесь.
progression-suggest = По журналу: { $length }
progression-choose = Выбрать…
progression-standing-only = Сурья Намаскар и стоячие
progression-current = Твоя практика: { $length }
progression-items = Прогибы: { $items }
progression-new = 🎉 Новая асана: { $asana }
progression-new-other = 🎉 Другая новая асана…
progression-item-new = 🎉 { $item }
progression-change = ✏️ Изменить
progression-change-explain = Выбери, где сейчас заканчивается практика. История сохранится.
progression-pick-series = Какой серией заканчивается практика?
progression-pick-asana = Последняя асана, { $series } серия:
progression-series-button = { $series } серия
progression-pick-new = Какая новая асана?
progression-saved = Сохранено. Последняя асана: { $asana }.
progression-saved-standing = Сохранено: Сурья Намаскар и стоячие асаны.
progression-back = { $asana } — в твоей практике.
progression-already = Это уже есть в твоей практике.
progression-undo = ↩︎ Отменить
progression-undone = Отменено.
progression-ask-new = { $asana } — дальше твоей последней асаны. Новая асана? 🎉
progression-ask-yes = 🎉 Да, новая
progression-ask-no = Не новая
progression-open = 🧘 Мои асаны

## PR-08 Phase 3: сообщение ученику об отметке учителя (на языке ученика) и кто отметил.
mark-received = 🎉 Новая асана: { $asana }. Приятного знакомства! Отметка: { $teacher }.
mark-received-range = 🎉 Новые асаны: { $from } → { $asana }. Приятного знакомства! Отметка: { $teacher }.
mark-received-back = { $asana } — в твоей практике. Отметка: { $teacher }.
mark-received-undo-hint = Если это не совпадает с твоей практикой, отметку можно отменить.
progression-marked-by = Отметка: { $teacher }
progression-by-teacher = учитель
progression-mark-moved-on = С этой отметки практика уже изменилась, поэтому ничего не отменено. Чтобы указать, где она заканчивается сейчас, нажми ✏️ Изменить.
# Отмена отметки учителя в «Мои асаны»: не две одинаковые кнопки «↩︎ Отменить».
progression-undo-mark = ↩︎ Отменить отметку
celebrate-new-asana = 🎉 Новая асана: { $asana }. Приятного знакомства!
celebrate-new-asanas = 🎉 Новые асаны: { $from } → { $asana }
celebrate-series-complete =
    { $traditional ->
        [none] 🎉 { $series } серия целиком.
       *[other] 🎉 { $series } серия целиком: { $traditional }.
    }
celebrate-series-begins =
    { $traditional ->
        [none] 🎉 { $series } серия начинается.
       *[other] 🎉 { $series } серия начинается: { $traditional }.
    }
celebrate-item = 🎉 { $item }: прекрасный шаг.
celebrate-practice-count = 🎉 { $count } { $count ->
        [one] практика
        [few] практики
       *[many] практик
    } в журнале. Спасибо, что приходишь на коврик.
preset-mine = 🧘 Моя практика: { $length }
# Названия элементов-этапов: из каталога, плюс бытовое название, где оно в ходу.
milestone-label =
    { $slug ->
        [viparita-chakrasana] { $name } (тик-токи)
       *[other] { $name }
    }

## My data: export and account deletion (ST-09). "📦 My data" under /settings.

settings-data-button = 📦 Мои данные
data-title = 📦 Мои данные
data-intro = Здесь можно скачать все свои записи или удалить аккаунт.
export-button = ⬇️ Скачать мои данные
export-preparing = Готовлю файл…
# $date = the local date, pre-formatted
export-caption = Твои данные из Tristhana на { $date }: data.json для программ, CSV для таблиц.
export-sent = 📦 Файл ниже. В нём есть личные записи (заметки, все отметки дней): когда сохранишь его, файл можно удалить из чата.
# $minutes = whole minutes until the next export (1–10)
export-too-soon = Файл только что отправлен. Ещё раз — через { $minutes } мин.
export-unreachable = Не получилось отправить файл в чат. Открой бота, нажми «Старт» и попробуй снова.
export-too-large = Файл слишком большой для Telegram, отправить его не получилось. Твои данные на месте, ничего не изменилось.
delete-button = Удалить аккаунт…
delete-export-first = ⬇️ Сначала скачать данные
delete-confirm = Удалить всё
delete-explain =
    Аккаунт и всё, что в нём, удалятся сразу: дни и паузы, практики, самочувствие, заметки, прогресс в асанах, списки учителей и учеников и настройки. Отменить это нельзя.
    • Сообщения в этом чате останутся, их можно удалить в Telegram.
    • Из резервных копий данные исчезнут в течение 30 дней.
    • Если снова написать боту, всё начнётся с чистого листа.
    • Шалы, которыми ты владеешь, удалятся для всех участников. Их личные журналы останутся.
delete-expired = Кнопка устарела. Вот она снова.
delete-done = Аккаунт и данные удалены. Хорошей практики 🙏 /start — и всё начнётся заново.

## Export file labels and README (ST-09): in the account's language.

export-rest-unreadable = Отдых (подробности не удалось прочитать)
export-kind-start = Начальная точка
export-kind-given = Новая асана
export-kind-changed = Исправление
# $item = the milestone name (drop-backs, standing up, tic-tacs)
export-kind-item-given = Отмечено: { $item }
export-kind-item-removed = Отметка снята: { $item }
export-readme-title = Твои данные из Tristhana
export-readme-files =
    data.json: всё целиком, для программ (формат «tristhana.export/1»).
    days.csv: по строке на каждый отмеченный день, с практикой, самочувствием и заметкой.
    rest_periods.csv: паузы (🌸, болезнь, дорога), дата окончания включительно.
    progression.csv: история асан.
    CSV открываются в любой таблице (UTF-8).
# $city = the moon-day city
export-readme-days = Здесь только дни с записями. Выходной, лунные дни (по городу 📍 { $city }) и дни паузы приложение заполняет само, поэтому их нет в списке дней; паузы — в rest_periods.csv. Дни отдыха — часть практики.
export-readme-moon-logged = «moon» в days.csv значит, что этот день отмечен как лунный.
export-readme-moon-city = Лунные дни — по календарю города (📍 { $city }); если в твоей шале другие даты, спроси учителя.
export-readme-ladies = Дни 🌸 здесь указаны как есть (учителю они видны как отдых). Помни об этом, если будешь делиться файлом.
# $statuses = one "code: label" line per status
export-readme-statuses =
    Отметки дней:
    { $statuses }
export-readme-length = Пустое поле «series» — короткая практика: Сурья Намаскар, стоячие, прогибы по желанию, завершающие.
export-readme-halves = first_part: «first_half» — 1-я половина первой (до Навасаны); «second_half» — 2-я половина первой (от Бхуджапидасаны до конца), только вместе со второй серией. Половина первой без второй серии записана как series «primary», end «navasana».
# $contexts = one "code: label" line per practice context
export-readme-contexts =
    Формат практики:
    { $contexts }
# $series = one "slug: name" line per series
# $series = one "code: name" line per series, each from export-readme-series-name
export-readme-series =
    Серии (код: название):
    { $series }
export-readme-series-name =
    { $n ->
        [1] Первая серия (Primary)
        [2] Вторая серия (Intermediate)
        [3] Третья серия (Advanced A)
        [4] Четвёртая серия (Advanced B)
        [5] Пятая серия (Advanced C)
       *[6] Шестая серия (Advanced D)
    }
export-readme-day-off = day_off.days: 1 — понедельник, 2 — вторник, 3 — среда, 4 — четверг, 5 — пятница, 6 — суббота, 7 — воскресенье.
export-readme-hide-ladies = hide_ladies: скрыть кнопку 🌸 (сами 🌸 дни всё равно есть в этом файле).
export-readme-standing = В progression.csv «standing» значит: только Сурья Намаскар и стоячие.
export-readme-marked-by = marked_by: «self» — ты, «teacher» — учитель, «unknown» — аккаунт, которого больше нет.
export-readme-unreadable = unreadable = yes: запись сохранена, но личную часть не удалось прочитать. Такая отметка дня показана как отдых (никогда не 🌸), а такая заметка оставлена пустой.

invite-ask = 🤝 { $name } отправляет тебе приглашение. Добавить в список твоих учителей?
invite-consent =
    Если подтвердить:
    • { $name } увидит твоё имя{ $me } и то, что ты отмечаешь с сегодняшнего дня: практика или отдых и объём практики.
    • Ещё будет видна твоя последняя асана по отметкам в журнале.
    • Любой отмеченный отдых выглядит одинаково, какой бы ни была причина.
    • Если какое-то время показать нечего, { $name } увидит об этом короткую пометку.
    • Любой учитель из твоего списка может отметить тебе новую асану. Придёт сообщение, и отметку можно отменить.
    • Самочувствие, заметки и причина отдыха остаются личными.
    • { $name } может отправлять объявления всем своим ученикам через бота. Их можно отключить.
    • Убрать из списка можно в любой момент в /teachers. Сообщений никто не получит.
invite-know-them = Имя здесь может выбрать любой, поэтому подтверждай, только если знаешь этого человека.
invite-not-told = Если нажать «Не сейчас», { $name } об этом не узнает.
invite-accept = ✅ Подтвердить
invite-decline = Не сейчас
invite-linked = ✅ { $name } теперь в списке твоих учителей.
invite-already = { $name } уже в списке твоих учителей.
invite-own = Это твоя ссылка-приглашение: поделись ею с учениками.
invite-invalid = Эта ссылка больше не работает. Новую может прислать тот, кто ею поделился.
invite-full = Сейчас по этой ссылке не получится добавить учителя.
link-student-joined = 👥 { $name } теперь в списке твоих учеников.
link-students-open = 👥 Мои ученики
invite-hint = Поделись ссылкой или QR-кодом. Каждый ученик подтверждает сам.
invite-moon-hint = У учеников, которые не выбрали город, лунные дни будут считаться по городу, который ты выберешь в /moon.
invite-share-text = Моя ссылка, чтобы добавить меня как учителя в Tristhana. Перед подтверждением бот покажет, что мне будет видно.
invite-new-ask = Сделать новую ссылку? Старая ссылка и QR перестанут работать. Те, кто уже в списке, останутся.
invite-qr-caption = Отсканируй, чтобы добавить меня как учителя в Tristhana.
link-unlink-ask = Убрать из списка учителей: { $name }? Сообщений никто не получит, просто в списке учеников тебя больше не будет.
link-next-main = Основным учителем станет: { $name }.
link-remove-ask = Убрать из списка учеников: { $name }? Сообщений никто не получит.
links-empty = Учителей в списке нет. Журнал практики работает и так.
links-no-students = Учеников в списке нет.
links-primary-hint = ⭐ — твой основной учитель. Поменять можно в любой момент.
links-main-chosen = ⭐ Основной учитель: { $name }
links-main-auto = ⭐ Основной учитель: { $name } (в начале списка)
links-title = 👥 Учителя и ученики
command-teachers = Мои учителя и ученики
link-no-name = (без имени)
export-readme-links = teacher_links в data.json: твои учителя и ученики без имён, поэтому чужих данных в этом списке нет.
export-readme-shalas = shalas в data.json: шалы, в которых ты состоишь. side: «staff» — в команде, «student» — ученик; owner — это твоя шала; roles — твои роли там («admin» — управляющий, «teacher» — преподаватель, «assistant» — ассистент, «office» — администратор). Чужих имён здесь нет.
links-make-main = ⭐ Сделать основным
links-remove = Убрать…
links-invite-first = Я преподаю: пригласить учеников
links-students = 👥 Мои ученики ({ $count })
links-invite = ➕ Пригласить учеников
links-remove-yes = Убрать
invite-share = 📤 Поделиться
invite-qr = 🔳 QR-код
invite-new = 🔄 Новая ссылка…
invite-new-yes = 🔄 Да, новая ссылка

students-days-note = Дни считаются по часовому поясу каждого ученика.
students-week = Последние 7 дней
students-last-asana = Последняя асана по отметкам в журнале: { $asana } ({ $series } серия)
students-last-standing = По отметкам в журнале: Сурья Намаскар и стоячие
students-blank-note = Не каждый день попадает в журнал, в том числе дни отдыха. Пустой день ничего не говорит о практике.
students-quiet = Какое-то время показать нечего
students-mark =
    { $state ->
        [practiced] 🧘
       *[rest] 😌
    }
students-day = { $date }: { $state }
students-day-length = { $date }: { $state }, { $length }
students-day-blank = { $date }: ·

## PR-08 Phase 3: учитель отмечает ученику новую асану (spec §8). $series — `series-lower`.
students-give = 🎉 Отметить новую асану
students-give-pick = { $name }: какая новая асана? { $name } получит одно сообщение, даже если асан несколько.
students-give-option = { $asana }
students-give-range = → { $asana }
students-give-ask = { $name }: следующая асана — { $asana } ({ $series } серия). Отметить как новую? { $name } получит сообщение от бота и сможет отменить отметку.
students-give-ask-range = { $name }: новые асаны — { $from } → { $asana } ({ $series } серия). Отметить? { $name } получит одно сообщение от бота и сможет отменить отметку.
students-give-ask-across = { $name }: новые асаны — { $from } ({ $from_series } серия) → { $asana } ({ $series } серия). Отметить? { $name } получит одно сообщение от бота и сможет отменить отметку.
students-give-yes = 🎉 Да, отметить
students-given = ✅ Отмечено: { $asana }.
students-given-range = ✅ Отмечено: { $from } → { $asana }.
students-give-stale = Карточка устарела, поэтому ничего не отмечено. Вот актуальная.
students-give-unset = Последняя асана пока не указана. Когда она будет указана в разделе „Мои асаны“, здесь можно будет отмечать новые.

## Шалы (SC-01, ADR-0033). Названия шал и имена — как есть, без склонения.
shala-join-ask = 🏛 Присоединиться к шале { $shala } (📍 { $city })?
shala-join-consent =
    Если присоединиться:
    • Преподаватели и сотрудники шалы увидят твоё имя{ $me }. Ничего из журнала.
    • Сотрудники шалы могут отправлять участникам объявления через бота. Их можно отключить.
    • Лунные дни будут считаться по календарю шалы, если город не выбран ни тобой, ни твоим учителем. Если учитель преподаёт в этой шале, календарь шалы важнее.
    • Посещение занятий могут отмечать сотрудники шалы, и ты тоже. Эти отметки видны тебе, и их можно снять в любой момент.
    • Выйти можно в любой момент в /teachers. Сообщений никто не получит.
shala-know-them = Присоединяйся только к знакомой шале: создать шалу с любым названием может кто угодно.
shala-join-yes = ✅ Присоединиться
shala-staff-ask = 🏛 { $name } приглашает тебя в шалу { $shala }. Роль: { $role }.
shala-staff-consent =
    Если подтвердить:
    • Все в шале, включая учеников, увидят твоё имя{ $me } и роль.
    • Тебе будут видны имена учеников и сотрудников, но не их журналы.
    • Объявления шалы тоже будут приходить тебе через бота. Их можно отключить.
    • Можно отмечать посещение занятий.
    • Выйти можно в любой момент в /teachers.
shala-staff-yes = ✅ Подтвердить
shala-staff-joined = 🏛 { $name } теперь в шале { $shala }. Роль: { $role }.
shala-staff-link-hint = Эта ссылка добавит одного человека. Роль: { $role }. Работает один раз, 7 дней.
shala-staff-pick = Выбери роль. Ссылка добавит одного человека с этой ролью.
shala-role =
    { $role ->
        [owner] Владелец
        [admin] Управляющий
        [teacher] Преподаватель
        [assistant] Ассистент
       *[office] Администратор
    }
shala-role-in-list =
    { $role ->
        [owner] владелец
        [admin] управляющий
        [teacher] преподаватель
        [assistant] ассистент
       *[office] администратор
    }
shala-moon-shared = 🌙 Сотрудники и участники, чей учитель преподаёт здесь, следуют этому календарю, если сами не выбрали город. Остальные — если город не выбран ни ими, ни их учителем.
shala-invalid = Эта ссылка на шалу больше не работает. Новую может прислать тот, кто ею поделился.
shala-already = Ты уже в шале { $shala }.
shala-already-staff = Ты уже в команде шалы { $shala }, ссылка для учеников тебе не нужна.
shala-full = Сейчас по этой ссылке не получится присоединиться к шале.
shala-joined = ✅ Теперь ты в шале { $shala }. Добро пожаловать 🙏
shala-leave = Выйти…
shala-leave-ask = Выйти из шалы { $shala }? Сообщений никто не получит, журнал останется как есть.
shala-leave-yes = Выйти
shala-remove-ask = Убрать из шалы: { $name }? Сообщений никто не получит.
shala-remove-yes = Убрать
shala-students =
    { $n ->
        [one] 👥 { $n } ученик
        [few] 👥 { $n } ученика
       *[many] 👥 { $n } учеников
    }
shala-no-students = В этой шале пока нет учеников.
shala-staff-title = Преподаватели и сотрудники: { $people }
shala-invite-students = ➕ Пригласить учеников
shala-invite-staff = ➕ Пригласить в команду
shala-join-hint = Поделись ссылкой или QR-кодом. Каждый ученик подтверждает сам.
shala-share-text = Присоединяйся к шале { $shala } в Tristhana. Перед подтверждением бот покажет, кто что увидит.
shala-qr-caption = Отсканируй, чтобы присоединиться к шале { $shala } в Tristhana.
shala-create = 🏛 Создать шалу
shala-online = 🌐 Онлайн
shala-place = 📍 { $city }
shala-time = { $place } · время шалы: { $zone }
shala-moon-line = 🌙 Лунные дни: 📍 { $city }
shala-delete-ask = Удалить шалу { $shala } для всех участников? Журналы у всех останутся. Сообщений никто не получит. Отменить это нельзя.
shala-name-invalid = Шале нужно название, до 64 символов.
shala-caps = Больше шал или ссылок для команды пока не получится: это предел.
moon-source-shala = 🏛 Как в шале: { $shala }. Можно выбрать другой город.
moon-follow-shala = 🏛 Как в шале ({ $shala })
settings-moon-line-shala = 🌙 Лунные дни: 📍 { $city } (как в шале: { $shala })

## Занятия шалы (SC-02). Время по часам шалы; { $zone } = «Алматы (UTC+5)».
## { $day } приходит готовым («пт, 13 нояб.»). Об изменениях никто не получает сообщений (Q122).
class-type = { $type ->
        [conference] Конференция
        [pranayama] Пранаяма
        [chanting] Чантинг
       *[workshop] Семинар
    }
class-led-hint = Часто в пятницу или воскресенье
schedule-open = 🗓 Расписание
schedule-title = 🗓 { $shala }: расписание, { $range }
schedule-zone = Время: { $zone }
schedule-your-time = ({ $time } по твоему времени)
schedule-moon-day = 🌙 Лунный день
schedule-reason = { $reason ->
        [moon] лунный день
        [closure] шала закрыта
       *[cancelled] отменено
    }
schedule-swap = 🔁 Вместо { $day }
schedule-swapped-to = 🔁 { $class }: перенесено на { $day } ({ $reason })
schedule-moved = ↪ перенесено с { $day } { $time }
schedule-substitute = { $name } (замена)
schedule-day-off = 😌 Выходной в шале
schedule-empty = В эти дни занятий нет.
shala-moon-policy = { $p ->
        [pranayama] 🌙 В лунные дни только пранаяма, чантинг и конференции
        [open] 🌙 В лунные дни занятия как обычно
       *[closed] 🌙 В лунные дни шала закрыта
    }
shala-moon-policy-note = Даты считаются по лунному городу шалы (лунный день на восходе). Если в шале отмечают другой день, используй «Всё равно провести» или «Отменить».
shala-day-off-line = 😌 Выходной: { $days }
shala-day-off-adopt = 😌 Мой выходной тоже: { $days }
class-cancel-ask = Отменить { $class } { $day }? Отмена будет видна в расписании. Сообщений никто не получит.
class-cancel = ❌ Отменить
class-restore = ↩ Вернуть
class-hold = ✅ Всё равно провести
class-cancel-pick = ❌ Отменить занятие…
class-pick-title = Какое занятие? Ближайшие 48 часов:
class-pick-empty = В ближайшие 48 часов занятий нет.
class-gone = Это занятие уже изменилось. Вот актуальное расписание.
class-caps = Для этой шалы это пока предел.
class-invalid = Такое изменение не вписывается в расписание.
# Своя неделя учителя (/classes): все шалы, где он в команде. Время в поясе каждой шалы.
command-classes = Мои занятия на этой неделе
my-classes-covered = тебя заменяет { $name }
my-classes-covering = ты заменяешь { $name }

## Моё расписание (SC-03): все мои шалы, в моём поясе. { $zone } — «Алматы (UTC+5)».
command-schedule = Моё расписание: занятия всех моих шал
my-schedule-open = 🗓 Моё расписание
my-schedule-title = 🗓 Моё расписание, { $range }
my-schedule-filter = { $f ->
        [teachers] 👤 Мои учителя
        [mine] 🧑‍🏫 Веду
       *[all] Все
    }
my-schedule-my-moon = 🌙
my-schedule-teacher-mark = 👤
schedule-held-moon = · 🌙
schedule-swapped-from = 🔁 вместо { $day }
schedule-swapped-inline = 🔁 { $day }
schedule-covering-for = { $name } (за { $teacher })
# $hours: 1 час, 2 часа, 5 часов; дробное (0,5, 1,5) — «other» → «часа».
schedule-shift = ⚠ С { $weekday ->
        [1] понедельника
        [2] вторника
        [3] среды
        [4] четверга
        [5] пятницы
        [6] субботы
       *[7] воскресенья
    }, { $date }, { $where } на { $hours } { $hours ->
        [one] час
        [few] часа
        [many] часов
       *[other] часа
    } { $dir ->
        [earlier] раньше
       *[later] позже
    } по твоему времени
my-schedule-empty = { $f ->
        [teachers] На этой неделе занятий с твоими учителями нет.
        [mine] На этой неделе ты не ведёшь занятий.
       *[all] На этой неделе занятий нет.
    }
my-schedule-none = Здесь будут занятия шал, в которые ты вступишь. Попроси у шалы ссылку.
my-schedule-zone-unknown = Время указано по { $zone }. Укажи свой город, чтобы видеть своё время.
my-schedule-more = Вся неделя целиком — в приложении.

## Подписка в календаре (SC-06): личная ICS-ссылка для Google, Apple или Outlook.
feed-open = 📅 Добавить в календарь
feed-title = 📅 Подписка в календаре
feed-explain = Твои занятия и лунные дни в Google, Apple или Outlook Календаре. Обновляется само (в Google — до суток).
feed-moon-only = Когда вступишь в шалу, здесь появятся и её занятия.
feed-create = 📅 Создать ссылку
feed-google = Добавить в Google Календарь
feed-google-phone = С телефона кнопка Google может не сработать. Сделай это один раз на компьютере: calendar.google.com → «Другие календари» + → по URL, и вставь ссылку. После этого календарь появится и на телефоне.
feed-apple = Добавить в Apple / Outlook
feed-copy = 📋 Скопировать ссылку
feed-private = 🔒 По этой ссылке видно твоё расписание. Не пересылай её; если она попала к кому-то, создай новую.
feed-checked = { $day ->
        [none] Календарь ещё не подключён
       *[other] Календарь последний раз обновлялся: { $day }
    }
feed-rotate = 🔄 Новая ссылка
feed-rotate-confirm = Старая ссылка перестанет работать. В календаре нужно будет подписаться заново.
feed-off = Отключить
feed-off-confirm = Календарь перестанет обновляться. События, которые уже в нём, останутся, пока ты не удалишь календарь.
feed-off-done = Отключено.
feed-confirm = ✅ Да
feed-cancel = ‹ Назад
# Текст самой ленты (названия и описания событий), на языке аккаунта в момент обновления.
ics-calendar-name = Tristhana: моё расписание
ics-class = { $what } · { $teacher }
ics-desc-online = 🌐 Онлайн
ics-desc-time = По времени шалы: { $time }
ics-desc-held-moon = 🌙 Проходит в полнолуние или новолуние (по календарю шалы)

## NT-03: объявления от учителя или шалы (обычный текст, как написан)
ann-head-teacher = 📣 { $name } · учитель
ann-head-shala = 📣 { $shala } · { $name }
ann-head-shala-only = 📣 { $shala }
ann-mute = 🔕 Не присылать
ann-unmute = 🔔 Присылать снова
ann-muted = Объявления больше не будут приходить. Они остаются в разделе 📣 Объявления. Об этом никому не сообщается.
ann-unmuted = Объявления снова будут приходить сюда.
ann-list = 📣 Объявления
ann-list-title = 📣 Объявления: { $source }
ann-list-empty = За последние 30 дней объявлений нет.
ann-item = 📅 { $date } · { $name }
ann-pinned-until = 📌 Закреплено до { $date }
ann-announce = 📣 Сделать объявление

## SC-05: посещение занятий (только присутствие; не запись в журнале и не пропуск)
attend-me-open = 🙋 Отметиться…
attend-me-title = 🙋 Отметка о посещении: выбери занятие (за сегодня и 6 предыдущих дней)
attend-me-none = За последние 7 дней отмечать нечего.
attend-claimed = { $state ->
        [confirmed] ✅ Отмечено: { $what }.
       *[claimed] 🙋 Отмечено: { $what }. Сотрудники шалы могут это подтвердить.
    }
attend-removed = Отметка снята: { $what }.
attend-state = { $s ->
        [confirmed] ✅ подтверждено
       *[claimed] 🙋 твоя отметка
    }
# My schedule: a row I marked (SC-05), after the row text.
attend-row-mark = { $state ->
        [confirmed] · ✅
       *[claimed] · 🙋
    }
attend-log-day = 🧘 Записать этот день
attend-staff-open = 📋 Посещаемость…
attend-roster-title = 📋 { $class } · { $day }, { $time }
attend-staff-pick = 📋 Какое занятие? Последние 7 дней.
attend-staff-none = За последние 7 дней занятий нет.
attend-row-counts = ✅ { $confirmed } · 🙋 { $claimed }
attend-roster-counts = ✅ { $confirmed } · { $claimed ->
        [0] подтверждать нечего
        [one] 🙋 { $claimed } ждёт подтверждения
        [few] 🙋 { $claimed } ждут подтверждения
       *[many] 🙋 { $claimed } ждут подтверждения
    }
attend-roster-hint = Нажми на имя, чтобы отметить посещение. 🙋 — собственная отметка.
attend-confirm-all = ✅ Подтвердить все 🙋 ({ $n })
attend-staff-tag = · сотрудник
attend-empty = Список пока пуст. Ученики появятся здесь, когда присоединятся к шале.
attend-not-open = Это занятие сейчас нельзя отметить: оно ещё не началось, отменено или было больше 7 дней назад.

# ST-07: карточка, присланная в свой чат из мини-приложения («Прислать в чат»).
share-card-caption = Карточка из Tristhana: перешли или сохрани, чтобы поделиться.

# ID-05 (ADR-0042): строка о списке учителей. Один сверенный факт с датой; никогда не «значок»,
# не «подтверждённый учитель» и не рекомендация. $listed — имя, как в списке; $when — месяц и год.
listing-mark = ✔ { $listed } — в списке учителей Sharath Yoga Centre (сверено: { $when })
listing-level = Уровень (со слов учителя): { $level }
listing-level-name =
    { $level ->
       *[authorised] Authorised (авторизация)
        [authorised-1] Authorised Level 1 (авторизация, уровень 1)
        [authorised-2] Authorised Level 2 (авторизация, уровень 2)
        [certified] Certified (сертификация SYC)
    }
listing-about = Это имя есть в открытом списке учителей Sharath Yoga Centre (SYC); запись сверена вручную в указанную дату. Это не рекомендация от SYC, и Tristhana не имеет отношения к SYC. Уровень указан со слов учителя: в списке уровней нет. Многих опытных учителей в этом списке нет; отсутствие строки ничего не говорит об учителе.
listing-open = Строка о списке SYC
listing-title = Строка о списке SYC
listing-intro = Если твоё имя есть в списке учителей Sharath Yoga Centre, я могу показывать это ученикам рядом с твоим именем. Сверяет человек, вручную, поэтому это может занять несколько дней. Многих опытных учителей в этом списке нет, и без этой строки всё здесь работает точно так же.
listing-how = Форма — в приложении. Понадобится имя, точно как в списке, и страна или регион.
listing-pending = Отправлено: «{ $listed }». Человек сверит запись вручную.
listing-listed-hint = Ученики видят эту строку в твоём приглашении и рядом с твоим именем.
listing-not-found = Сверить запись «{ $listed }» с этим аккаунтом пока не получилось. Возможно, имя написано иначе или список изменился. Можешь проверить данные и отправить их ещё раз.
listing-app = ✏️ Открыть форму
listing-remove = Убрать…
listing-remove-ask = Убрать строку о списке SYC? Ученики перестанут её видеть. Позже можно отправить запрос снова.
listing-remove-yes = Убрать
listing-removed = Убрано. Ученики эту строку не видят.
listing-note-listed = ✔ «{ $listed }» есть в списке учителей Sharath Yoga Centre. Теперь ученики видят это рядом с твоим именем.
listing-note-not-found = Сверить запись «{ $listed }» в списке учителей с этим аккаунтом пока не получилось. Возможно, имя написано иначе или список изменился. Можешь проверить данные и отправить их ещё раз.
listing-note-ended = При сегодняшней сверке найти «{ $listed }» в списке учителей Sharath Yoga Centre не получилось, поэтому эта строка больше не показывается. Список меняется, и это ничего не говорит о твоём преподавании. Всё остальное остаётся как есть: твои ученики, ссылка, списки. Если имя снова появится в списке, в том числе в другом написании, отправь данные в любой момент.
export-readme-listing = directory_listing в data.json: твой запрос на строку о списке учителей Sharath Yoga Centre, если он был отправлен. status: «pending» — ждёт сверки, «listed» — строка показывается, «not_found» — сверить запись с этим аккаунтом не получилось, «withdrawn» — строка убрана по твоему запросу.
admin-listing-title = Запросы о списке: ждут — { $waiting } · в списке — { $listed }
admin-listing-oldest = Самая давняя сверка: { $when }
admin-listing-listed-title = В списке, сначала давние сверки. Проходи список примерно два раза в год.
admin-listing-empty = Здесь пусто.
admin-listing-recheck = В списке: сверить заново
admin-listing-waiting = Ждут ответа
admin-listing-card-name = Имя в аккаунте: { $name }
admin-listing-card-listed = Имя в списке: { $listed }
admin-listing-card-region = Страна или регион: { $region }
admin-listing-card-level = Уровень (со слов учителя): { $level }
admin-listing-card-note = Заметка учителя: { $note }
admin-listing-card-requested = Отправлено: { $date }
admin-listing-card-checked = Последняя сверка: { $when }
admin-listing-open-directory = 🌐 Открыть список
admin-listing-listed = ✔ Есть в списке
admin-listing-still-listed = ✔ По-прежнему в списке
admin-listing-not-found = Не удалось сверить…
admin-listing-ended = Больше нет в списке…
admin-listing-not-found-ask = Ответить, что запись «{ $listed }» сверить не удалось? Учитель получит одно сообщение и сможет отправить данные снова.
admin-listing-ended-ask = Убрать строку для «{ $listed }»? Она скроется сразу, учитель получит одно сообщение. Ученикам ничего не сообщается.
admin-listing-yes = Да
admin-listing-stale = Этот запрос изменился. Вот актуальный список.
admin-listing-done-listed = ✔ Есть в списке: «{ $listed }».
admin-listing-done-not-found = Готово: строки для «{ $listed }» нет. Учитель получит одно сообщение.
admin-listing-new = Ждёт запрос о списке учителей: /admin
