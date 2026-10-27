# Тексты Mini App (ru). Ключи совпадают с locales/en/app.ftl. Префикс ключа — экран.

# Главный экран: приветствие по имени из Telegram (только для показа).
home-greeting = Намасте, { $name } 🙏
home-greeting-anon = Намасте 🙏
home-subtitle = Твой спутник в практике аштанги.

# Главный экран: статус сервера (в dev или после долгого нажатия на приветствие).
home-server-status = Сервер { $version } · { $commit }
home-server-loading = Подключаемся к серверу…
home-server-offline = Не получается связаться с сервером. Твои данные в порядке, попробуй чуть позже.

# Главная кнопка Telegram и её результат, когда детали сервера скрыты.
home-check-connection = Проверить связь
home-connection-ok = Связь в порядке ✓

# Если приложение не запустилось (простой текст, вне React).
startup-failed = Что-то пошло не так. Открой Тристхану заново.

# Если страницу открыли не из Telegram (в проде).
not-in-telegram = Открой Тристхану в Telegram: @tristhana_bot

# Пример множественного числа для статистики (ST-03).
practice-days =
    { $count ->
        [one] { $count } день
        [few] { $count } дня
       *[many] { $count } дней
    }

# Показывается, если сессия Telegram старше 24 часов (или её не удалось проверить).
session-expired = Сессия истекла. Закрой Тристхану и открой её снова из бота.

# Карточка «Сегодня» на главной (PR-01). Подписи статусов совпадают с ботом.
home-first-hint = Для начала отметь сегодня: практика или отдых.
today-title = Сегодня
status-practiced = 🧘 Практика
status-rest = 😌 День отдыха
status-moon = 🌙 Лунный день
status-ladies = 🌸 Женские дни
status-sick = 🤒 Болезнь / травма
status-travel = ✈️ В дороге
status-skipped = 🌱 Без практики
today-private-note = Это видишь только ты. Остальные видят «День отдыха».
today-clear = Убрать отметку
today-save-failed = Не получилось сохранить. Попробуй ещё раз чуть позже.
today-load-failed = Не получилось загрузить отметку за сегодня. Попробуй ещё раз чуть позже.

# Детали практики (PR-02, PR-03, PR-05). Совпадают с формулировками бота.
practice-title = Практика
practice-same-as-last = 🔁 Как в прошлый раз
context-mysore = Майсор
context-led = Лед-класс
context-private = Индивидуально
context-self = Самостоятельно
practice-online = 🌐 Онлайн
practice-length = Объём практики
practice-duration = Длительность
preset-short = ☀️ Короткая → стоячие
preset-half-primary = ½ первой → Навасана
preset-full-primary = Первая серия целиком
preset-other = 🎯 Другое…
length-pick-range = Серии
length-pick-end = Последняя асана
length-full-series = Вся серия
duration-min = { $min } мин
duration-none = Без длительности
practice-start-time = Время начала
practice-clear = Убрать детали
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
length-only = Только { $series }
length-summary =
    { $kind ->
        [short] Короткая практика
        [full-one] { $range } серия целиком
        [full] { $range } (полностью)
       *[to] { $range } → { $asana }
    }

# Лунные дни (MD-03). Совпадает с ботом; названия городов приходят с сервера.
moon-title = 🌙 Лунные дни · 📍 { $city }
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
moon-city = Город для календаря
moon-reminders-label = Напоминать
moon-offset =
    { $n ->
        [one] за { $n } день
        [few] за { $n } дня
       *[other] за { $n } дней
    }
moon-zone-needed-app = Напоминания начнутся, как только станет известен твой часовой пояс. Он определится сам, когда ты откроешь приложение на телефоне.
moon-today =
    { $phase ->
        [purnima] Сегодня 🌕 полнолуние · 📍 { $city }
       *[amavasya] Сегодня 🌑 новолуние · 📍 { $city }
    }
moon-save-failed = Не получилось сохранить. Попробуй ещё раз чуть позже.

## Напоминание о практике (PR-10). { $d } — день недели по ISO (1 = понедельник).
remind-card-title = 🧘 Напоминание о практике
remind-switch = 🔔 Спрашивать раз в день
remind-explain-app = Раз в день спрошу в боте, как прошёл день: ответить можно одним нажатием. Не пишу в лунные дни, в уже отмеченные дни и пока стоит пауза.
remind-time-label = Время · { $zone }
remind-weekday = { $d ->
        [1] пн
        [2] вт
        [3] ср
        [4] чт
        [5] пт
        [6] сб
       *[7] вс
    }

## Статистика (ST-01..03). Только «подряд», никогда «серия», «полоса», «пропуск».
stats-open = 📊 Моя практика
stats-title = Моя практика
stats-year-total = { $year }: { $n ->
        [one] { $n } практика
        [few] { $n } практики
       *[many] { $n } практик
    }
stats-consistency = В этом месяце: практика в { $x } из { $y ->
        [one] { $y } дня
       *[other] { $y } дней
    }
stats-consistency-count = В этом месяце: { $n ->
        [0] пока без практики
        [one] { $n } практика
        [few] { $n } практики
       *[many] { $n } практик
    }
stats-run-current = 🌿 { $n ->
        [one] { $n } практика
        [few] { $n } практики
       *[many] { $n } практик
    } подряд
stats-run-longest = Больше всего подряд в этом году: { $n }
stats-consistency-hint = Дни без отметки не учитываются. Отдых, лунные дни, болезнь и поездки не сбивают счёт: отдых тоже часть практики.
stats-legend-practiced = Практика
stats-legend-rest = Отдых
stats-legend-moon = 🌙 Лунный день (отдых)
stats-legend-away = Болезнь или поездка
stats-legend-skipped = Без практики
stats-legend-none = Без отметки
stats-legend-moon-marker = Полнолуние или новолуние · 📍 { $city }
stats-show-ladies = Показывать 🌸 дни на этом устройстве
stats-cell-label = { $date }: { $status }{ $moon ->
        [yes] , полнолуние или новолуние
       *[no] {""}
    }
stats-cell-future = { $date }{ $moon ->
        [yes] : полнолуние или новолуние
       *[no] {""}
    }
stats-back = ‹ Назад
stats-month-practices = { $n ->
        [one] { $n } практика
        [few] { $n } практики
       *[many] { $n } практик
    }
stats-online = 🌐 Онлайн: { $n }
stats-by-series = По сериям
stats-series-short = ☀️ Короткая
stats-no-details = Без деталей
# $th/$tm = всего часов/минут; нулевые части не показываем («45 мин», «2 ч»).
stats-duration = ⏱ всего { $th ->
        [0] { $tm } мин
       *[other] { $tm ->
            [0] { $th } ч
           *[other] { $th } ч { $tm } мин
        }
    } · в среднем { $avg } мин за практику
stats-unlogged = { $n ->
        [one] { $n } день без отметки: нажми на день, чтобы отметить
        [few] { $n } дня без отметки: нажми на день, чтобы отметить
       *[many] { $n } дней без отметки: нажми на день, чтобы отметить
    }
stats-month-empty = В этом месяце пока нет отметок. Отмеченные дни появятся здесь.
stats-load-failed = Не получилось загрузить статистику. Попробуй ещё раз чуть позже.
stats-editor-done = Готово
stats-prev = ‹
    .aria-label = Предыдущий год
stats-next = ›
    .aria-label = Следующий год

## Настройки (ID-06).
settings-open = ⚙️ Настройки
settings-title = Настройки
settings-name = Имя
settings-name-hint = Так я к тебе обращаюсь. Оставь пустым, и я возьму имя из Telegram.
settings-language = Язык
language-auto = Как в Telegram
language-en = English
language-ru = Русский
settings-zone = Часовой пояс
settings-zone-now = { $time } { $zone }
settings-zone-unset = Пока не задан. Напоминания начнутся, как только он появится.
settings-zone-use-device = Взять пояс телефона: { $zone }
settings-zone-pick = Выбрать город
settings-zone-utc = UTC (без летнего времени)
settings-zone-hint = Напоминания приходят по этому поясу. Уже отмеченные дни останутся на своих датах.
zone-travel = Время на телефоне: { $device }. Напоминания приходят по времени: { $current }.
zone-travel-switch = Перейти: { $city }
zone-travel-keep = Оставить: { $city }
settings-moon-time = Во сколько
settings-quiet = Тихие часы
settings-quiet-from = Тихо с
settings-quiet-to = Тихо до
settings-quiet-off = Без тихих часов
settings-quiet-conflict = На эти часы приходится напоминание. Сначала передвинь его.
settings-cap = { $n ->
        [one] Не больше { $n } сообщения в день
       *[other] Не больше { $n } сообщений в день
    }
settings-privacy = Приватность
settings-privacy-ladies = 🌸 Женские дни хранятся в зашифрованном виде. Остальные видят только «День отдыха».
settings-privacy-sharing = Пока твои отметки видишь только ты. Когда появятся учителя, ты выберешь, что им показывать.
settings-save-failed = Не получилось сохранить. Попробуй ещё раз чуть позже.

## Выходной и автоотдых (PR-09). { $d } — день недели по ISO (1 = понедельник).
settings-day-off = Выходной
settings-day-off-hint = Отметь один или два; остальные дни — дни практики. Выходные отмечаются как отдых в журнале и статистике, а напоминания о практике приходят только в дни практики. { $first ->
        [yes] Прошлые недели тоже отметятся.
       *[no] Изменение действует с сегодняшнего дня, прошлые недели остаются как были.
    } Если день прошёл иначе, просто отметь его. Без постоянного выходного напоминания приходят каждый день, кроме лунных дней.
day-off-none = Без постоянного выходного
remind-days-follow = В дни практики: { $days }. Поменять дни — в разделе «Выходной».
remind-every-day = каждый день
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
today-auto-moon = 🌙 Лунный день (📍 { $city }) — традиционно день отдыха{ $dayoff ->
        [yes] , к тому же твой выходной
       *[no] {""}
    }. Если была практика, отметь ниже.
today-auto-day-off = 😌 Твой выходной — отмечен как отдых. Если день прошёл иначе, отметь ниже.
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
stats-legend-auto = Выходной или лунный день (без отметки)
stats-cell-auto = { $date }: { $kind ->
        [moon] 🌙 лунный день (📍 { $city })
       *[day_off] 😌 выходной
    }{ $dayoff ->
        [yes] , к тому же твой выходной
       *[no] {""}
    }, без отметки
stats-day-off-link = 😌 Выбрать выходной

## WH-01 part 2: несколько дней 🌸 / болезни / поездки с паузой напоминаний (черновик спеки §7)
pause-ask = { $reminders ->
        [on] { $rel ->
            [yesterday] ⏸ На сколько дней приостановить напоминания о практике, включая вчерашний день? Эти дни отметятся как „{ $label }“, если не отметишь иначе.
           *[today] ⏸ На сколько дней приостановить напоминания о практике, включая сегодня? Эти дни отметятся как „{ $label }“, если не отметишь иначе.
        }
       *[off] { $rel ->
            [yesterday] Сколько дней отметить как „{ $label }“, включая вчерашний день?
           *[today] Сколько дней отметить как „{ $label }“, включая сегодня?
        }
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
pause-set = { $reminders ->
        [on] ⏸ Напоминания о практике на паузе по { $until } включительно. Эти дни отмечаются как „{ $label }“; любой день можно отметить иначе.
       *[off] ⏸ Готово, по { $until } включительно. Эти дни отмечаются как „{ $label }“; любой день можно отметить иначе.
    }
today-period = „{ $label }“ по { $until } включительно. Если день прошёл иначе, отметь ниже.
pause-end = { $reminders ->
        [on] ⏹ Завершить паузу
       *[off] ⏹ Закончить раньше
    }
pause-ended = { $reminders ->
        [on] ▶️ Напоминания о практике снова приходят с сегодняшнего дня.
       *[off] ⏹ Готово: с сегодняшнего дня отметка „{ $label }“ снята.
    }
pause-cut = { $rel ->
        [yesterday] ⏸ Практика отмечена на вчера, поэтому следующие дни, по { $until } включительно, больше не отмечены как „{ $label }“. Оставить как было?
        [other] ⏸ Практика отмечена на этот день, поэтому следующие дни, по { $until } включительно, больше не отмечены как „{ $label }“. Оставить как было?
       *[today] ⏸ Практика отмечена на сегодня, поэтому следующие дни, по { $until } включительно, больше не отмечены как „{ $label }“. Оставить как было?
    }
pause-keep = ⏸ Оставить паузу
pause-kept = ⏸ Пауза сохранена: „{ $label }“ по { $until } включительно.
remind-paused-until = ⏸ На паузе по { $until } включительно
remind-resume = ▶️ Возобновить сейчас
settings-ladies-button = Показывать кнопку 🌸 „Женские дни“
settings-ladies-button-hint = В боте и здесь. Уже отмеченные дни не меняются.

## После практики: самочувствие (PR-06). Всегда по желанию; без советов и выводов.
checkin-title = Самочувствие
checkin-mood = Настроение
checkin-energy = ⚡ Энергия: 1 мало → 5 много
checkin-effort = 🔥 Усилие: 1 легко → 5 тяжело
checkin-body = Тело
checkin-mind = Ум
# Для экранного диктора: кнопки настроения — эмодзи.
checkin-mood-label = Настроение { $n } из 5
checkin-mood-chip = { $n ->
        [1] 😔
        [2] 😕
        [3] 😐
        [4] 🙂
       *[5] 😊
    }
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
checkin-edit = ✨ Самочувствие
checkin-clear = Убрать самочувствие
checkin-save-failed = Не получилось сохранить самочувствие. Попробуй ещё раз чуть позже.
settings-checkin = Предлагать отметить самочувствие после практики
settings-checkin-hint = Настроение, энергия и усилие сразу после отметки практики. Добавить можно и позже, в любой день практики.

## Дневник (PR-07). Личная заметка на день, при любом статусе; не просим писать.
diary-title = Дневник
diary-add = Добавить заметку
diary-edit = Изменить
diary-save = Сохранить
diary-cancel = Отмена
diary-placeholder = Твоя заметка…
# Видно с 1800 символов; только числа, без форм множественного числа.
diary-counter = { $n } / { $max }
diary-save-failed = Не получилось сохранить заметку. Текст остался здесь, можно попробовать ещё раз.
diary-private-hint = Дневник личный: преподаватели его не видят.
diary-unreadable = Эту заметку сейчас не получается прочитать. Можно написать новую или удалить старую.
diary-clear = Удалить заметку
diary-clear-confirm = Удалить заметку?
diary-clear-yes = Удалить
diary-removed = Заметка удалена из дневника.

## Прогресс (PR-08) и праздники (GM-01). Как в боте; названия асан, элементов и серий —
## из каталога. $series — `series-name`, $traditional — традиционное
## название или "none".
progression-open = 🧘 Мои асаны
progression-title = Мои асаны
progression-unset = Где сейчас заканчивается твоя практика? Укажи это один раз, а новые асаны потом отмечай здесь.
progression-suggest = По журналу: { $length }
progression-standing-only = Сурья Намаскар и стоячие
progression-current = Твоя практика: { $length }
progression-items = Прогибы: { $items }
progression-new = 🎉 Новая асана: { $asana }
progression-item-new = 🎉 { $item }
progression-new-other = 🎉 Другая новая асана…
progression-change = ✏️ Изменить
progression-change-explain = Выбери, где сейчас заканчивается практика. История сохранится.
progression-pick-series = Серия
progression-pick-asana = Последняя асана
progression-save = Сохранить
progression-cancel = Отмена
progression-date = Дата
progression-history = История
progression-undo = ↩︎ Отменить
progression-back = { $asana } — в твоей практике.
progression-changed = Это изменилось на другом устройстве. Вот свежая версия.
progression-save-failed = Не получилось сохранить. Попробуй ещё раз.
progression-event =
    { $kind ->
        [start] Отмечено впервые: { $asana }
        [given] 🎉 { $asana }
        [changed] Изменено: { $asana }
        [item_given] 🎉 { $item }
       *[item_removed] { $item }: убрано
    }
progression-ask-new = { $asana } — дальше твоей последней асаны. Новая асана? 🎉
progression-ask-yes = 🎉 Да, новая
progression-ask-no = Не новая
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
