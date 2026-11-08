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
# MD-04: свой город, если это не тот, по которому считаются лунные дни. Город не склоняется.
moon-same-as-city = Как мой город ({ $city })
moon-home-fyi = ℹ 📍 { $city }: { $date }
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

## Лунный календарь учителя (MD-02). Имена в именительном падеже, без «у» перед ними; если имени нет, `link-no-name`.
moon-source-teacher = 👥 Как у основного учителя: { $name }. Можно выбрать другой город.
moon-source-teacher-none = 👥 У учителя ({ $name }) пока не выбран город, поэтому даты считаются по городу 📍 { $city }.
moon-follow-teacher = 👥 Как у учителя ({ $name })
moon-teacher-shared =
    { $chosen ->
        [yes] 👥 У учеников, которые не выбрали город, лунные дни как у тебя: 📍 { $city }.
        [follow] 👥 У учеников лунные дни считаются по городу 📍 { $city }. Можно оставить так или выбрать свой город.
       *[no] 👥 У учеников лунные дни считаются по городу 📍 { $city }, как и у тебя. Можно оставить так или выбрать свой город.
    }

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
settings-name-hint = Так я к тебе обращаюсь, и это имя видят твои учителя и ученики. Оставь пустым, и я возьму имя из Telegram.
settings-language = Язык
language-auto = Как в Telegram
language-en = English
language-ru = Русский
# MD-04 (ADR-0029): город задаёт часовой пояс. $zone = «Астана (UTC+5)».
settings-city = 🏙 Мой город
settings-zone-now = { $time } { $zone }
settings-zone-unset = Пока не задан. Напоминания начнутся, как только он будет задан.
settings-city-nudge = Если хочешь, выбери свой город: рядом со временем будет его название.
settings-city-not-now = Не сейчас
settings-city-pick = В каком городе ты живёшь?
settings-city-unlisted-option = Моего города нет в списке
settings-city-use-device = Взять время телефона: { $zone }
settings-zone-utc = UTC (без летнего времени)
settings-zone-hint = Напоминания и время идут по часам твоего города. Уже отмеченные дни останутся на своих датах.
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
settings-privacy-sharing = Твой журнал принадлежит тебе. Учитель из твоего списка видит твоё имя, последнюю асану и то, что ты отмечаешь со дня добавления: практика или отдых и объём практики. Любой отмеченный отдых выглядит одинаково, какой бы ни была причина. Если какое-то время показать нечего, учитель увидит об этом короткую пометку. Позже учитель из твоего списка сможет отметить тебе новую асану, а ты сможешь это отменить. Самочувствие, заметки и причина отдыха остаются личными. Убрать учителя из списка можно в любой момент.
# MD-04: данные о поясах в tzfpy под ODbL (ADR-0029), поэтому указаны здесь и в README.
settings-privacy-location = 📍 Геопозиция, которую ты присылаешь боту, нужна только чтобы найти часовой пояс, и не хранится. Поиск идёт на нашем сервере через tzfpy; данные карты © участники OpenStreetMap (ODbL).
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
diary-private-hint = Дневник личный: учителя его не видят.
diary-unreadable = Эту заметку сейчас не получается прочитать. Можно написать новую или удалить старую.
diary-clear = Удалить заметку
diary-clear-confirm = Удалить заметку?
diary-clear-yes = Удалить
diary-removed = Заметка удалена из дневника.
diary-discard-confirm = Выйти, не сохранив заметку?
diary-discard-yes = Не сохранять
diary-discard-no = Продолжить писать

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

## My data: export and account deletion (ST-09). The file is sent by the bot to the chat.

data-title = 📦 Мои данные
data-intro = Здесь можно скачать все свои записи или удалить аккаунт.
export-button = ⬇️ Скачать мои данные
export-sending = Отправляю…
export-sent-app = Отправлено в чат с ботом. В файле есть личные записи: когда сохранишь его, файл можно удалить из чата.
# $minutes = whole minutes until the next export (1–10)
export-too-soon = Файл только что отправлен. Ещё раз — через { $minutes } мин.
export-unreachable = Не получилось отправить файл в чат. Открой бота, нажми «Старт» и попробуй снова.
export-too-large = Файл слишком большой для Telegram, отправить его не получилось. Твои данные на месте, ничего не изменилось.
export-failed = Не получилось отправить файл. Попробуй чуть позже.
delete-button = Удалить аккаунт…
delete-explain = Аккаунт и всё, что в нём, удалятся сразу: дни и паузы, практики, самочувствие, заметки, прогресс в асанах, списки учителей и учеников и настройки. Отменить это нельзя.
delete-explain-chat = Сообщения в чате с ботом останутся, их можно удалить в Telegram.
delete-explain-backups = Из резервных копий данные исчезнут в течение 30 дней.
delete-explain-fresh = Если снова написать боту, всё начнётся с чистого листа.
delete-explain-shalas = Шалы, которыми ты владеешь, удалятся для всех участников. Их личные журналы останутся.
delete-export-first = ⬇️ Сначала скачать данные
delete-confirm = Удалить всё
delete-confirm-popup = Удалить аккаунт и все данные? Отменить нельзя.
delete-cancel = Отмена
delete-failed = Не получилось удалить. Попробуй чуть позже.
delete-done-app = Аккаунт и данные удалены. Хорошей практики 🙏 Открой бота, когда захочешь начать заново.
delete-close = Закрыть

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
students-day-blank-mark = { $date }: ·
students-day-blank = { $date }: показать нечего
students-more = Показать ещё
students-card-load-failed = Не получилось загрузить страницу. Попробуй ещё раз чуть позже.
students-load-failed = Не получилось загрузить учеников. Попробуй ещё раз чуть позже.
links-students = 👥 Мои ученики ({ $count })
link-students-open = 👥 Мои ученики
day-label =
    { $rel ->
        [today] Сегодня, { $date }
        [yesterday] Вчера, { $date }
       *[other] { $date }
    }

## Шалы (SC-01, ADR-0033). Названия шал и имена — как есть, без склонения.
moon-source-shala = 🏛 Как в шале: { $shala }. Можно выбрать другой город.
moon-follow-shala = 🏛 Как в шале ({ $shala })
links-shalas-title = 🏛 Шалы
shala-create = 🏛 Создать шалу
shala-name-label = Название
shala-city-label = Город
shala-online-only = 🌐 Только онлайн-занятия
shala-my-roles = Мои роли в шале
shala-create-submit = Создать
shala-name-invalid = Шале нужно название, до 64 символов.
shala-caps = Больше шал или ссылок для команды пока не получится: это предел.
shala-save-failed = Не получилось сохранить. Попробуй ещё раз чуть позже.
shala-load-failed = Не получилось загрузить шалу. Попробуй ещё раз чуть позже.
shala-role =
    { $role ->
        [owner] Владелец
        [admin] Управляющий
        [teacher] Преподаватель
        [assistant] Ассистент
       *[office] Администратор
    }
shala-title = 🏛 { $shala }
shala-person = { $name } · { $roles }
shala-online = 🌐 Онлайн
shala-place = 📍 { $city }
shala-time = { $place } · время шалы: { $zone }
shala-moon-line = 🌙 Лунные дни: 📍 { $city }
shala-moon-city = Город для лунных дней шалы
shala-moon-same = По городу шалы
shala-moon-shared = 🌙 Сотрудники и участники, чей учитель преподаёт здесь, следуют этому календарю, если сами не выбрали город. Остальные — если город не выбран ни ими, ни их учителем.
shala-staff-title = Преподаватели и сотрудники
shala-edit = ✏️ Изменить шалу
shala-roles-save = Сохранить
shala-students =
    { $n ->
        [one] 👥 { $n } ученик
        [few] 👥 { $n } ученика
       *[many] 👥 { $n } учеников
    }
shala-no-students = В этой шале пока нет учеников.
shala-invite-students = ➕ Пригласить учеников
shala-invite-staff = ➕ Пригласить в команду
shala-staff-pick = Выбери роль. Ссылка добавит одного человека с этой ролью.
shala-staff-link-hint = Эта ссылка добавит одного человека. Роль: { $role }. Работает один раз, 7 дней.
shala-join-hint = Поделись ссылкой или QR-кодом. Каждый ученик подтверждает сам.
shala-share-text = Присоединяйся к шале { $shala } в Tristhana. Перед подтверждением бот покажет, кто что увидит.
shala-qr-alt = QR-код ссылки шалы
shala-remove = Убрать…
shala-remove-ask = Убрать из шалы: { $name }? Сообщений никто не получит.
shala-remove-yes = Убрать
shala-leave = Выйти…
shala-leave-ask = Выйти из шалы { $shala }? Сообщений никто не получит, журнал останется как есть.
shala-leave-yes = Выйти
shala-delete = Удалить шалу…
shala-delete-ask = Удалить шалу { $shala } для всех участников? Журналы у всех останутся. Сообщений никто не получит. Отменить это нельзя.
shala-delete-yes = Удалить

## Занятия шалы (SC-02). Время по часам шалы; { $zone } = «Алматы (UTC+5)».
schedule-title = 🗓 Расписание
schedule-load-failed = Не получилось загрузить расписание. Попробуй чуть позже.
schedule-moon-day = 🌙 Лунный день
schedule-day-off = 😌 Выходной в шале
schedule-empty = В эти дни занятий нет.
schedule-your-time = ({ $time } по твоему времени)
schedule-reason = { $reason ->
        [moon] лунный день
        [closure] шала закрыта
       *[cancelled] отменено
    }
schedule-swap = 🔁 Вместо { $day }
schedule-substitute = { $name } (замена)
schedule-add-class = ➕ Добавить занятие
class-type = { $type ->
        [conference] Конференция
        [pranayama] Пранаяма
        [chanting] Чантинг
       *[workshop] Семинар
    }
class-led-hint = Часто в пятницу или воскресенье
class-form-type = Тип
class-form-title = Название (по желанию)
class-form-teacher = Преподаватель
class-form-no-teacher = —
class-form-start = Начало, { $zone }
class-form-until = Окончание
class-form-length = Длительность, мин
class-form-days = Дни (не выбраны — одна дата)
class-form-every = Повтор
class-form-every-n = { $n ->
        [1] каждую неделю
        [one] каждую { $n } неделю
        [few] каждые { $n } недели
       *[many] каждые { $n } недель
    }
class-form-from = Первая дата
class-form-end = Последняя дата (по желанию)
class-form-online = 🌐 Онлайн
class-form-zone = Часовой пояс
class-form-applies = Для каких дат
class-form-day-off-warning = Один из выбранных дней — выходной в шале.
class-form-window-invalid = Занятие должно закончиться после начала и не позже полуночи.
class-form-save = Сохранить занятие
class-form-cancel = Отмена
class-form-failed = Не получилось сохранить занятие. Проверь время и попробуй ещё раз.
class-form-caps = Для этой шалы это пока предел.
shala-moon-policy-label = 🌙 В лунные дни
shala-moon-policy = { $p ->
        [pranayama] 🌙 В лунные дни только пранаяма, чантинг и конференции
        [open] 🌙 В лунные дни занятия как обычно
       *[closed] 🌙 В лунные дни шала закрыта
    }
shala-moon-policy-option = { $p ->
        [pranayama] Только пранаяма, чантинг и конференции
        [open] Занятия как обычно
       *[closed] Шала закрыта
    }
shala-moon-policy-note = Даты считаются по лунному городу шалы (лунный день на восходе). Если в шале отмечают другой день, используй «Всё равно провести» или «Отменить».
shala-day-off-label = 😌 Выходной (до двух дней)
shala-day-off-line = 😌 Выходной: { $days }
shala-day-off-adopt = 😌 Мой выходной тоже: { $days }
occurrence-cancel = ❌ Отменить
occurrence-hold = ✅ Всё равно провести
occurrence-restore = ↩ Вернуть
occurrence-note = Сообщений никто не получит. Изменение будет видно в расписании.
occurrence-failed = Не получилось изменить занятие. Попробуй чуть позже.
occurrence-delete = 🗑 Удалить занятие (все даты)…
occurrence-delete-ask = Удалить это занятие во все даты? Оно пропадёт из расписания. Сообщений никто не получит.
occurrence-delete-yes = Удалить
closure-title = 🏖 Шала закрыта
closure-start = Первый день
closure-end = Последний день
closure-add = ➕ Добавить закрытые дни
closure-line = { $start } – { $end }
closure-remove = 🗑 Убрать
closure-failed = Не получилось сохранить даты: до 92 дней подряд, начиная с сегодня.
swap-title = 🔁 Перенос лунного дня
swap-from = Лунный день
swap-to = Перенести занятия на
swap-add = ➕ Добавить перенос
swap-remove = 🗑 Отменить перенос
swap-hint = Переносятся только занятия, отменённые из-за лунного дня или закрытия, остальные остаются на месте. Выбери выходной или день без такого же занятия, не дальше 6 дней.
swap-failed = Такой перенос не подходит: выбери выходной или день без таких же занятий в пределах 6 дней, не лунный и не закрытый.

# Paging (shala students, SC-01; schedule weeks, SC-02).
page-prev = ◀
page-next = ▶

## Quick tour (UI-02). Never names the ladies' holiday (a private topic in a tour for everyone).

tour-open = 🧭 Знакомство
tour-offer = Показать, что здесь где? Это займёт минуту.
tour-offer-yes = Покажи
tour-offer-no = Не сейчас
tour-progress = { $n } из { $total }
tour-next = Дальше
tour-prev = ‹
    .aria-label = Предыдущий шаг
tour-done = Готово
tour-today = Практика или отдых? После практики можно добавить детали, самочувствие и личную заметку.
tour-stats = Весь твой год на одном экране и календарь, чтобы дополнить прошлые дни.
tour-asanas = Твоя последняя асана. Здесь же отмечается новая, когда её даёт учитель.
tour-moon = Ближайшие лунные дни: полнолуние и новолуние, традиционные дни отдыха. Город — в настройках.
tour-settings = Твой город, выходной, напоминания и приватность. Знакомство тоже здесь.

links-title = 👥 Учителя и ученики
links-empty = Учителей в списке нет. Журнал практики работает и так.
links-no-students = Учеников в списке нет.
links-primary-hint = ⭐ — твой основной учитель. Поменять можно в любой момент.
links-main-chosen = ⭐ Основной учитель: { $name }
links-main-auto = ⭐ Основной учитель: { $name } (в начале списка)
links-make-main = ⭐ Сделать основным
links-remove = Убрать…
links-remove-yes = Убрать
links-invite = ➕ Пригласить учеников
links-invite-first = Я преподаю: пригласить учеников
link-no-name = (без имени)
link-unlink-ask = Убрать из списка учителей: { $name }? Сообщений никто не получит, просто в списке учеников тебя больше не будет.
link-next-main = Основным учителем станет: { $name }.
link-remove-ask = Убрать из списка учеников: { $name }? Сообщений никто не получит.
invite-hint = Поделись ссылкой или QR-кодом. Каждый ученик подтверждает сам.
invite-share = 📤 Поделиться
invite-share-text = Моя ссылка, чтобы добавить меня как учителя в Tristhana. Перед подтверждением бот покажет, что мне будет видно.
invite-copy = Скопировать ссылку
invite-copied = Скопировано
invite-new = 🔄 Новая ссылка…
invite-new-ask = Сделать новую ссылку? Старая ссылка и QR перестанут работать. Те, кто уже в списке, останутся.
invite-new-yes = 🔄 Да, новая ссылка
invite-qr-alt = QR-код твоей ссылки-приглашения
links-load-failed = Не получилось загрузить списки. Попробуй ещё раз чуть позже.
