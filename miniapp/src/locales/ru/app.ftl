# Тексты Mini App (ru). Ключи совпадают с locales/en/app.ftl. Префикс ключа — экран.

# Главный экран: приветствие по имени из Telegram (только для показа).
home-greeting = Намасте, { $name } 🙏
home-greeting-anon = Намасте 🙏
home-subtitle = Твой спутник в практике аштанги. Скоро здесь появится статистика.

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
