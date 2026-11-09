## Badges (GM-02): a quiet collection to look back at. Loaded with the Badges screen.
## A record of showing up, never a score: no earned / unlocked / lost / next, no streaks.
## `badges-open` (the entry on My practice) is in app.ftl.

badges-title = Значки
badges-group-practice = Практика
badges-group-asanas = Асаны
badges-new = Новое
badges-at-start = С начала журнала
badges-empty = Значки появляются здесь сами, пока ты ведёшь журнал.
badges-note = Значки видны лишь тебе, учителям — нет.
badges-load-failed = Не получилось загрузить значки. Попробуй чуть позже.

# Shared lines, prefixed "badges-" so no badge key can match them (not terms: a term gets
# literal arguments only, and these need $asana, $item, $count).
# $asana / $item: the catalog name (no variant letter; tic-tacs via milestone-label).
# The stop line agrees with the asana (every stop ends in -асана), never with the person.
badges-stop-about = { $asana } вошла в твою практику.
badges-item-about = { $item } — теперь часть твоей практики.
# $count: the badge's number (Fluent groups it: 1 000).
badges-practices-about =
    { $count ->
        [one] { $count } практика в журнале.
        [few] { $count } практики в журнале.
       *[many] { $count } практик в журнале.
    }

badge-ekam = Экам
    .about = Первая практика в журнале.
badge-nava = Нава
    .about = Девять практик — по числу виньяс Сурья Намаскар А.
badge-shatam = Шатам
    .about = { badges-practices-about }
badge-count-108 = 108
    .about = { badges-practices-about }
badge-count-365 = 365
    .about = { badges-practices-about }
badge-sahasra = Сахасра
    .about = { badges-practices-about }
badge-mandala = Мандала
    .about =
        { $count ->
            [one] { $count } практика без перерыва; дни отдыха — её часть.
            [few] { $count } практики без перерыва; дни отдыха — её часть.
           *[many] { $count } практик без перерыва; дни отдыха — её часть.
        }
# $before: the wall-clock threshold, e.g. 06:00.
badge-before-dawn = До рассвета
    .about =
        { $count ->
            [one] { $count } практика, начатая до { $before } по местному времени.
            [few] { $count } практики, начатые до { $before } по местному времени.
           *[many] { $count } практик, начатых до { $before } по местному времени.
        }
badge-led-by-the-count = Под счёт
    .about =
        { $count ->
            [one] { $count } практика под счёт.
            [few] { $count } практики под счёт.
           *[many] { $count } практик под счёт.
        }
badge-self-practice = Своя практика
    .about =
        { $count ->
            [one] { $count } практика самостоятельно.
            [few] { $count } практики самостоятельно.
           *[many] { $count } практик самостоятельно.
        }
badge-rest-is-practice = Отдых — тоже практика
    .about =
        { $count ->
            [one] { $count } лунный день отдыха.
            [few] { $count } лунных дня отдыха.
           *[many] { $count } лунных дней отдыха.
        }
badge-return = Возвращение
    .about = Снова на коврике. С возвращением!
badge-yoga-chikitsa = Йога Чикитса · вся Первая серия
    .about = Йога-терапия: вся Первая серия вошла в твою практику.
badge-nadi-shodhana = Нади Шодхана · начало Второй серии
    .about = Очищение каналов: первые асаны Второй серии вошли в твою практику.
badge-supta-kurmasana = { $asana }
    .about = { badges-stop-about }
badge-kapotasana = { $asana }
    .about = { badges-stop-about }
badge-karandavasana = { $asana }
    .about = { badges-stop-about }
badge-drop-backs = { $item }
    .about = { badges-item-about }
badge-standing-up = { $item }
    .about = { badges-item-about }
badge-tic-tacs = { $item }
    .about = { badges-item-about }
