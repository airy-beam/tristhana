## Badges (GM-02): a quiet collection to look back at. Loaded with the Badges screen.
## A record of showing up, never a score: no earned / unlocked / lost / next, no streaks.
## `badges-open` (the entry on My practice) is in app.ftl.

badges-title = Badges
badges-group-practice = Practice
badges-group-asanas = Asanas
badges-new = New
badges-at-start = From the start of your log
badges-empty = Badges appear here by themselves as you log your practice.
badges-note = Badges are just for you; teachers don't see them.
# Not "again" (avoid-word list); "once more" as in checkin-save-failed.
badges-load-failed = Couldn't load your badges. Try once more in a moment.

# Shared lines, prefixed "badges-" so no badge key can match them (not terms: a term gets
# literal arguments only, and these need $asana, $item, $count).
# $asana / $item: the catalog name (no variant letter; tic-tacs via milestone-label).
badges-stop-about = { $asana } became part of your practice.
badges-item-about = { $item } became part of your practice.
# $count: the badge's number (Fluent groups it: 1,000).
badges-practices-about =
    { $count ->
        [one] { $count } practice in your log.
       *[other] { $count } practices in your log.
    }

badge-ekam = Ekam
    .about = The first practice in your log.
badge-nava = Nava
    .about = Nine practices, as many as the vinyasas of Surya Namaskara A.
badge-shatam = Shatam
    .about = { badges-practices-about }
badge-count-108 = 108
    .about = { badges-practices-about }
badge-count-365 = 365
    .about = { badges-practices-about }
badge-sahasra = Sahasra
    .about = { badges-practices-about }
badge-mandala = Mandala
    .about =
        { $count ->
            [one] { $count } practice without a break; rest days are part of it.
           *[other] { $count } practices without a break; rest days are part of it.
        }
# $before: the wall-clock threshold, e.g. 06:00.
badge-before-dawn = Before dawn
    .about =
        { $count ->
            [one] { $count } practice started before { $before } local time.
           *[other] { $count } practices started before { $before } local time.
        }
badge-led-by-the-count = Led by the count
    .about =
        { $count ->
            [one] { $count } Led practice.
           *[other] { $count } Led practices.
        }
badge-self-practice = Self-practice
    .about =
        { $count ->
            [one] { $count } practice on your own.
           *[other] { $count } practices on your own.
        }
badge-rest-is-practice = Rest is practice
    .about =
        { $count ->
            [one] { $count } moon day of rest.
           *[other] { $count } moon days of rest.
        }
badge-return = Return
    .about = Back on the mat. Welcome back.
badge-yoga-chikitsa = Yoga Chikitsa · the full Primary series
    .about = Yoga therapy: the whole Primary series became part of your practice.
badge-nadi-shodhana = Nadi Shodhana · Intermediate begins
    .about = Cleansing the channels: the first asanas of Intermediate became part of your practice.
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
