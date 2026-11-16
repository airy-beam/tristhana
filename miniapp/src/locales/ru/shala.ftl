## Настройка шалы и её занятия (UI-06, этап 4, ADR-0048). Загружается вместе с карточкой шалы
## (`shalaCopy`); остальные тексты карточки в app.ftl.

## Форма занятия: тип, начало и дни, остальное в «Ещё настройки».
class-form-new-title = Новое занятие
class-form-edit-title = Изменить занятие
class-form-type = Тип
# $zone: «Алматы» или «Алматы (UTC+5)» для того, кто в другом поясе.
class-form-start = Начало, { $zone }
class-form-days = Повторяется по дням
class-form-once = Только одна дата
class-form-weekly = Повторять по дням недели
class-form-date = Дата
class-form-days-needed = Выбери хотя бы один день или нажми «Только одна дата».
class-form-day-off-warning = Один из выбранных дней — выходной в шале.
class-form-more = Ещё настройки
# Части строки под «Ещё настройки», между ними « · ».
class-form-sum-until = до { $time }
class-form-sum-length = { $minutes } мин
class-form-sum-from = с { $date }
class-form-sum-end = по { $date }
class-form-until = Окончание
class-form-length = Длительность
class-form-length-chip = { $minutes } мин
class-form-length-other = Другая
class-form-ends = Окончание
class-form-title = Название (по желанию)
class-form-teacher = Преподаватель
class-form-no-teacher = —
class-form-every = Как часто
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
# Изменение занятия, которое уже проходило (ADR-0048).
class-form-applies = Изменения действуют с
class-form-applies-hint = Более ранние даты останутся как были.
# $zone: город, по времени которого идёт онлайн-занятие, «Берлин (UTC+1)».
class-form-applies-zone = Более ранние даты останутся как были. Дата считается по времени: { $zone }.
class-form-window-invalid = Занятие должно закончиться после начала и не позже полуночи.
class-form-save = Сохранить занятие
class-form-failed = Не получилось сохранить занятие. Проверь время и попробуй ещё раз.
class-form-caps = Для этой шалы это пока предел.
class-form-gone = Это занятие уже изменилось или удалено. Вот актуальное расписание.

## Занятие в один день: что относится к этой дате, а что ко всему занятию.
# $day: «пн, 16 нояб.».
occurrence-this-date = Эта дата: { $day }
occurrence-whole-class = Всё занятие
class-edit = ✏️ Изменить занятие…
occurrence-tell = 📣 Сообщить ученикам…
# Текст объявления после отмены занятия; перед отправкой его можно поправить.
# $class: «Майсор» или «Лед Полная первая». $day: «пн, 16 нояб.». $time: «06:00 Алматы (UTC+5)».
ann-cancel-draft = Занятие отменено: { $class }, { $day }, { $time }.

## Список первых шагов владельца в новой шале.
setup-title = Настройка шалы
setup-class = Добавить занятие
setup-students = Пригласить учеников
setup-staff = Пригласить преподавателей (по желанию)
setup-staff-skip = Преподаю без команды
setup-done-mark = готово
