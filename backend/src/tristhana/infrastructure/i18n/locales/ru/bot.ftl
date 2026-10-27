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
    🧘 /asanas: мои асаны, отметить новую
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
diary-empty = Заметки за этот день нет. Можно записать что угодно: как прошла практика, что сказал преподаватель, новая асана или просто мысль.
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
    Аккаунт и всё, что в нём, удалятся сразу: дни и паузы, практики, самочувствие, заметки, прогресс в асанах и настройки. Отменить это нельзя.
    • Сообщения в этом чате останутся, их можно удалить в Telegram.
    • Из резервных копий данные исчезнут в течение 30 дней.
    • Если снова написать боту, всё начнётся с чистого листа.
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
export-readme-ladies = Дни 🌸 здесь указаны как есть, даже там, где приложение показывает их как отдых.
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
