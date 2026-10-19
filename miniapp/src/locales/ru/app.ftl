# Тексты Mini App (ru). Ключи совпадают с locales/en/app.ftl. Префикс ключа — экран.

# Главный экран: приветствие по имени из Telegram (только для показа).
home-greeting = Намасте, { $name } 🙏
home-greeting-anon = Намасте 🙏
home-subtitle = Твой спутник в практике аштанги.

# Главный экран: статус сервера (в dev или после долгого нажатия на приветствие).
home-server-status = Сервер { $version } · { $commit }
home-server-loading = Подключаемся к серверу…
home-server-offline = Не получается связаться с сервером. Твои данные в порядке, попробуй чуть позже.

# Главная кнопка Telegram и ее результат, когда детали сервера скрыты.
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
preset-short = ☀️ Короткая: приветствия солнцу, стоячие, завершающие
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
moon-calc-note = Даты рассчитаны для 📍 { $city } (лунный день на восходе). Календарь твоей шалы может отличаться на день, ориентируйся на своего учителя.
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
remind-explain-app = Раз в день спрошу в боте, как прошёл день: ответить можно одним нажатием. В лунные дни и в уже отмеченные дни не пишу.
remind-time-label = Время · { $zone }
remind-day-off = Выходной: { remind-weekday }
remind-days-label = Дни
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
stats-online = 🌐 онлайн: { $n }
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
zone-travel = Телефон живёт по времени { $device }, а напоминания — по { $current }.
zone-travel-switch = Перейти на { $city }
zone-travel-keep = Оставить { $city }
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
