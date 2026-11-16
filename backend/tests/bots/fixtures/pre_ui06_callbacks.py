"""Every callback-data shape the bot shipped before UI-06, frozen on 2026-11-16 (UI-06 §5, §8).

These strings sit under messages in people's chat history, so they are literals on purpose:
never rebuild this list from the encoders, and never edit an entry to make a test pass. A
tap on any of them must still get a screen (`test_stale_buttons_bot.py`); nothing here may
lose its meaning (UI-06 §5: "no prefix and no letter is removed or given a new meaning").

One example per prefix-and-letter combination, plus each value that changes the handler's
branch (status codes, origins, on/off flags). The ids, codes and dates below are the ones
inside the strings, so a test can seed rows that match them.
"""

from datetime import date
from uuid import UUID

DAY = date(2026, 11, 15)  # `20261115`: the day every dated entry acts on
PERIOD_START = date(2026, 11, 13)  # `a1:k`, `a1:e`, `a1:er`: a rest period 13-17 November
PERIOD_END = date(2026, 11, 17)
MOON_DAY = date(2026, 11, 5)  # `m1:q`: the moon day a reminder was about
SHALA = UUID("11111111-1111-4111-8111-111111111111")  # short: ERERERERQRGBEREREREREQ
CLASS = UUID("22222222-2222-4222-8222-222222222222")  # short: IiIiIiIiQiKCIiIiIiIiIg
# The other person (a student, a teacher, a staff member, a listed account), and the
# `x1:y` account tag `33333333`.
PERSON = UUID("33333333-3333-4333-8333-333333333333")  # short: MzMzMzMzQzODMzMzMzMzMw
TEACHER_CODE = "AbCdEfGh12345678"  # the code of `/start t_<code>`
SHALA_CODE = "ZyXwVuTs87654321"  # the code of `/start h_<code>` and `hs_<code>`
CITY = "almaty"
EVENT_ID = 1234  # `g1:u`: a progression event

PRE_UI06_CALLBACKS: tuple[str, ...] = (
    # --- d1: day status (callbacks.py) ---------------------------------------------------
    "d1:t",  # "Log today" under /start greetings from before UI-01
    "d1:o:20261115",  # a day's status grid: week picker row, ✏️ Change, the reminder's "Other"
    "d1:s:20261115:p",  # status grid (/start, /log, a day): 🧘 Practiced
    "d1:s:20261115:r",  # status grid: 😌 Rest
    "d1:s:20261115:m",  # status grid: 🌕 Moon day
    "d1:s:20261115:l",  # status grid: 🌸 Ladies' holiday
    "d1:s:20261115:k",  # status grid: 🤒 Sick
    "d1:s:20261115:t",  # status grid: ✈️ Travel
    "d1:s:20261115:s",  # status grid: No practice
    "d1:x:20261115",  # status grid: Clear
    "d1:w:20261115",  # "Another day": the week picker (also its earlier / later paging)
    # --- o1: language under /start (start.py) --------------------------------------------
    "o1:l:en",  # /start: switch to English
    "o1:l:ru",  # /start: switch to Russian
    # --- q1: quick tour (tour_callbacks.py) ----------------------------------------------
    "q1:1:s",  # /start: "Quick tour" (step 1)
    "q1:2:s",  # tour opened from /start: Next / Back, steps 2-6
    "q1:3:s",
    "q1:4:s",
    "q1:5:s",
    "q1:6:s",
    "q1:d:s",  # tour opened from /start: Done
    "q1:1:h",  # /help: "Quick tour" (step 1)
    "q1:2:h",  # tour opened from /help: Next / Back, steps 2-6
    "q1:3:h",
    "q1:4:h",
    "q1:5:h",
    "q1:6:h",
    "q1:d:h",  # tour opened from /help: Done
    # --- p1: practice details (practice_callbacks.py) ------------------------------------
    "p1:o:20261115",  # saved screen: "Details" (opens the details screen P)
    "p1:v:20261115",  # details: Done (the summary V)
    "p1:s:20261115",  # details: Same as last time
    "p1:x:20261115",  # details: Remove details
    "p1:m:20261115",  # details: Length (the length screen L)
    "p1:a:20261115",  # length screen: Other… (the series screen O)
    "p1:d:20261115",  # details: Duration (the duration screen D)
    "p1:c:20261115:m",  # details: class type Mysore
    "p1:c:20261115:l",  # details: class type Led
    "p1:c:20261115:i",  # details: class type 1:1
    "p1:c:20261115:s",  # details: class type self-practice
    "p1:n:20261115:1",  # details: online on
    "p1:n:20261115:0",  # details: online off
    "p1:t:20261115:90",  # duration screen: 90 minutes
    "p1:t:20261115:0",  # duration screen: no duration
    "p1:r:20261115:2",  # series screen: up to Intermediate (the range screen S)
    "p1:g:20261115:11:0",  # range screen: the asana grid of Primary, page 0
    "p1:g:20261115:12a:1",  # asana grid: half Primary + Intermediate, page 1
    "p1:l:20261115:00:",  # length screen: a short practice
    "p1:l:20261115:11:",  # length screen: full Primary (no last asana)
    "p1:l:20261115:12:pasasana",  # asana grid: Primary + Intermediate up to Pasasana
    "p1:l:20261115:12a:pasasana",  # asana grid: the same after the first half of Primary
    # --- k1: check-in (check_in_callbacks.py) --------------------------------------------
    "k1:o:20261115",  # summary / details: ✨ Check-in (the check-in screen K)
    "k1:v:20261115",  # check-in: Done
    "k1:g:20261115",  # check-in: Body and mind (the tags screen T)
    "k1:x:20261115",  # check-in: Remove
    "k1:m:20261115:4",  # the one-tap mood row and the check-in screen: mood 4
    "k1:m:20261115:0",  # check-in: clear the mood (✓ tapped again)
    "k1:e:20261115:3",  # check-in: energy 3
    "k1:e:20261115:0",  # check-in: clear the energy
    "k1:f:20261115:2",  # check-in: effort 2
    "k1:f:20261115:0",  # check-in: clear the effort
    "k1:t:20261115:s:1",  # tags screen: "stiff" on
    "k1:t:20261115:s:0",  # tags screen: "stiff" off
    # --- n1: diary note (diary_callbacks.py) ---------------------------------------------
    "n1:o:20261115:d",  # status grid: 📝 Note (the note screen N)
    "n1:o:20261115:k",  # check-in screen: 📝 Note
    "n1:w:20261115:d",  # note screen: Write
    "n1:w:20261115:k",
    "n1:r:20261115:d",  # note screen: Rewrite
    "n1:r:20261115:k",
    "n1:y:20261115:d",  # note screen: Remove (asks to confirm)
    "n1:y:20261115:k",
    "n1:x:20261115:d",  # note screen: Yes, remove
    "n1:x:20261115:k",
    "n1:b:20261115:d",  # note screen: Back to the day
    "n1:b:20261115:k",  # note screen: Back to the check-in
    # --- g1: my asanas (progression_callbacks.py) ----------------------------------------
    "g1:o",  # /asanas, details: "My asanas" (the screen G)
    "g1:c",  # my asanas: ✏️ Change
    "g1:g:2:kapotasana-b",  # my asanas: "New asana: Kapotasana B"
    "g1:g:2:kapotasana-b:20261115",  # details of a practice: the same, back to that day
    "g1:s:2:laghu-vajrasana",  # stop grid: set the position
    "g1:s:0:",  # stop grid: standing only
    "g1:i:drop-backs:1",  # my asanas: item given
    "g1:i:drop-backs:0",  # my asanas: item removed
    "g1:a:s",  # change screen: choose where I am (the series picker)
    "g1:a:g",  # the series picker in "give" mode (decoded, shown by no current screen)
    "g1:p:s:2:1",  # series picker: the stop grid of Intermediate, page 1
    "g1:p:g:0:1",  # "Another new asana…": later stops, page 1
    "g1:u:1234",  # after a new asana: Undo
    "g1:n:2:kapotasana-b:20261115",  # details of a practice: "Not new"
    # --- r1: practice reminder (remind_callbacks.py) -------------------------------------
    "r1:v",  # /remind, back rows: the reminder screen
    "r1:o:1",  # reminder screen: turn on
    "r1:o:0",  # reminder screen: turn off
    "r1:t:1000",  # reminder screen: send at 10:00
    "r1:w:123457",  # reminder days (retired with PR-09): shows the reminder screen
    "r1:y:20261115",  # the offer under "practice saved": Yes
    "r1:n:20261115",  # the offer under "practice saved": No, thanks
    "r1:s:20261115",  # a reminder message: practiced, same as last time
    "r1:p:20261115",  # a reminder message: 🧘 Practiced
    "r1:r:20261115",  # a reminder message: 😌 Rest
    "r1:q:20261115:0",  # a reminder message: turn reminders off
    "r1:q:20261115:1",  # a reminder message: turn them back on
    "r1:d:6",  # the one-time day-off question: Yes, Saturday
    "r1:d:67",  # the day-off question: two days (decoded, offered by no current screen)
    "r1:d:0",  # the day-off question: no fixed day off (decoded, as above)
    "r1:dp",  # reminder screen: the day off picker
    "r1:dt:67",  # day off picker opened from /remind: set, and stay in it
    "r1:dt:0",  # day off picker opened from /remind: no fixed day off
    "r1:dn",  # the one-time day-off question: Not now
    # --- a1: rest periods (rest_callbacks.py) --------------------------------------------
    "a1:p:20261115:l:5",  # the pause question after 🌸: 5 days
    "a1:p:20261115:k:3",  # the pause question after 🤒: 3 days
    "a1:p:20261115:t:14",  # the pause question after ✈️: 14 days
    "a1:m:20261115:k:1",  # the pause question: Other… (more day counts)
    "a1:m:20261115:k:0",  # the same when reminders were off
    "a1:b:20261115:k:1",  # more day counts: Back
    "a1:b:20261115:k:0",
    "a1:o:20261115:l",  # the pause question: just this day
    "a1:k:20261113:20261117:l:20261115",  # after 🧘 inside a pause: Keep the pause
    "a1:e:20261113:1",  # status grid during a pause: End the pause
    "a1:e:20261113:0",  # the same when reminders were off
    "a1:er:20261113",  # /remind during a pause: End the pause
    # --- s1: settings (settings_callbacks.py) --------------------------------------------
    "s1:v",  # /settings, back rows: the settings screen
    "s1:l:a",  # settings: language as in Telegram
    "s1:l:en",  # settings: English
    "s1:l:ru",  # settings: Russian
    "s1:cp:2",  # settings: the "My city" picker, page 2
    "s1:zp:2",  # the same from before MD-04 (the time zone picker)
    "s1:c:almaty",  # city picker: my city
    "s1:z:almaty",  # the same from before MD-04
    "s1:c:-",  # city picker: my city isn't listed
    "s1:u",  # city picker: UTC
    "s1:n",  # the city nudge: Not now
    "s1:o",  # settings: the day off picker
    "s1:o:67",  # day off picker: Saturday and Sunday
    "s1:o:0",  # day off picker: no fixed day off
    "s1:h:1",  # settings: hide the 🌸 button
    "s1:h:0",  # settings: show the 🌸 button
    "s1:k:1",  # settings: offer the check-in after practice
    "s1:k:0",  # settings: don't offer it
    # --- m1: moon days (moon_callbacks.py) -----------------------------------------------
    "m1:v",  # /moon, back rows: the moon screen
    "m1:r",  # moon screen: reminder settings
    "m1:c:2",  # moon screen: the city picker, page 2
    "m1:s:almaty",  # city picker: follow that city
    "m1:f",  # moon screen: follow my teacher
    "m1:h",  # moon screen: follow my shala
    "m1:k:almaty",  # the first-student note: keep that city as my own
    "m1:z:almaty",  # moon screen: use that city's zone for reminders
    "m1:o:71",  # moon reminders: 7 days and 1 day before
    "m1:o:0",  # moon reminders: off
    "m1:t:1900",  # moon reminders: send at 19:00
    "m1:q:20261105:p:7:1",  # a moon reminder (full moon, 7 days before): only the day before
    "m1:q:20261105:a:1:0",  # a moon reminder (new moon, the day before): turn off
    "m1:q:20261105:p:3:a",  # a moon reminder: turn back on
    # --- x1: my data (data_callbacks.py) -------------------------------------------------
    "x1:o",  # settings: 📦 My data
    "x1:e",  # my data: send the export
    "x1:e:x",  # delete screen: send the export first
    "x1:d",  # my data: Delete (step 1, the delete screen)
    "x1:y:33333333:hp03k",  # delete screen: Yes, delete (expired: it is older than 10 minutes)
    # --- t1: teacher links (teacher_links_callbacks.py) ----------------------------------
    "t1:a:AbCdEfGh12345678",  # consent screen of /start t_…: ✅ Confirm
    "t1:y:AbCdEfGh12345678",  # the confirm button from before ST-06: shows the consent again
    "t1:n",  # consent screen: Not now
    "t1:l:en:AbCdEfGh12345678",  # consent screen: switch to English
    "t1:l:ru:AbCdEfGh12345678",  # consent screen: switch to Russian
    "t1:o",  # /teachers, back rows: the teachers screen
    "t1:s:0",  # teachers screen: My students, page 0
    "t1:c:33333333-3333-4333-8333-333333333333",  # teachers screen: a teacher's card
    "t1:p:33333333-3333-4333-8333-333333333333",  # teacher card: make main
    "t1:u:33333333-3333-4333-8333-333333333333",  # teacher card: remove (asks)
    "t1:x:33333333-3333-4333-8333-333333333333",  # teacher card: Yes, remove
    "t1:v:33333333-3333-4333-8333-333333333333",  # a student's card (no page: older lists)
    "t1:v:33333333-3333-4333-8333-333333333333:0",  # my students: a student's card
    "t1:r:33333333-3333-4333-8333-333333333333",  # student card: remove (asks)
    "t1:z:33333333-3333-4333-8333-333333333333",  # student card: Yes, remove
    "t1:i",  # teachers screen: invite students
    "t1:q",  # invite screen: QR code
    "t1:w",  # invite screen: new link (asks)
    "t1:wy",  # invite screen: Yes, a new link
    "t1:g:33333333-3333-4333-8333-333333333333:0",  # student card: mark a new asana
    "t1:gp:33333333-3333-4333-8333-333333333333:2:3:1:0",  # the picker: one stop further
    "t1:gy:33333333-3333-4333-8333-333333333333:2:3:1:0",  # the confirm screen: mark it
    "t1:gp:33333333-3333-4333-8333-333333333333:0:0:2:0",  # the picker from standing only
    # --- h1: shalas (shalas_callbacks.py) ------------------------------------------------
    "h1:a:ZyXwVuTs87654321",  # consent screen of /start h_…: ✅ Join
    "h1:b:ZyXwVuTs87654321",  # consent screen of /start hs_…: ✅ Accept
    "h1:n",  # both shala consent screens: Not now
    "h1:l:en:ZyXwVuTs87654321",  # shala consent screens: switch to English
    "h1:l:ru:ZyXwVuTs87654321",  # shala consent screens: switch to Russian
    "h1:c:ERERERERQRGBEREREREREQ",  # teachers screen: a shala's card
    "h1:m:ERERERERQRGBEREREREREQ:0",  # shala card: students, page 0
    "h1:v:ERERERERQRGBEREREREREQ:MzMzMzMzQzODMzMzMzMzMw",  # shala students: one student
    "h1:i:ERERERERQRGBEREREREREQ",  # shala card: the join link
    "h1:q:ERERERERQRGBEREREREREQ",  # join link: QR code
    "h1:w:ERERERERQRGBEREREREREQ",  # join link: new link (asks)
    "h1:wy:ERERERERQRGBEREREREREQ",  # join link: Yes, a new link
    "h1:e:ERERERERQRGBEREREREREQ",  # shala card: invite staff (pick a role)
    "h1:e:ERERERERQRGBEREREREREQ:t",  # staff link for a teacher
    "h1:e:ERERERERQRGBEREREREREQ:a",  # staff link for an assistant
    "h1:e:ERERERERQRGBEREREREREQ:o",  # staff link for the office
    "h1:e:ERERERERQRGBEREREREREQ:m",  # staff link for a manager
    "h1:u:ERERERERQRGBEREREREREQ:MzMzMzMzQzODMzMzMzMzMw",  # shala student: remove (asks)
    "h1:x:ERERERERQRGBEREREREREQ:MzMzMzMzQzODMzMzMzMzMw",  # shala student: Yes, remove
    "h1:k:ERERERERQRGBEREREREREQ",  # shala card: leave (asks)
    "h1:ky:ERERERERQRGBEREREREREQ",  # shala card: Yes, leave
    # --- c1: classes (classes_callbacks.py) ----------------------------------------------
    "c1:w:ERERERERQRGBEREREREREQ:0",  # shala card, /classes: the schedule, this week
    "c1:w:ERERERERQRGBEREREREREQ:3",  # the schedule: three weeks ahead
    "c1:p:ERERERERQRGBEREREREREQ",  # the schedule (staff): pick an occurrence
    "c1:o:ERERERERQRGBEREREREREQ:IiIiIiIiQiKCIiIiIiIiIg:20261115",  # an occurrence's card
    "c1:x:ERERERERQRGBEREREREREQ:IiIiIiIiQiKCIiIiIiIiIg:20261115",  # occurrence: cancel
    "c1:r:ERERERERQRGBEREREREREQ:IiIiIiIiQiKCIiIiIiIiIg:20261115",  # occurrence: restore
    "c1:h:ERERERERQRGBEREREREREQ:IiIiIiIiQiKCIiIiIiIiIg:20261115",  # occurrence: hold anyway
    "c1:d:ERERERERQRGBEREREREREQ",  # shala card: make the shala's day off mine
    "c1:m:0:a",  # /schedule: My schedule, this week, all classes
    "c1:m:1:t",  # My schedule: next week, my teachers' classes
    "c1:m:3:m",  # My schedule: three weeks ahead, the classes I teach
    "c1:f:s",  # settings, /moon, My schedule: 📅 Add to calendar (show my link)
    "c1:f:n",  # calendar link: create
    "c1:f:r",  # calendar link: new link (asks)
    "c1:f:R",  # calendar link: Yes, a new link
    "c1:f:x",  # calendar link: turn off (asks)
    "c1:f:X",  # calendar link: Yes, turn off
    # --- v1: attendance (attendance_callbacks.py) ----------------------------------------
    "v1:l",  # My schedule, the schedule: 🙋 I was there…
    "v1:p",  # the same screens (staff): attendance, pick an occurrence
    "v1:i:IiIiIiIiQiKCIiIiIiIiIg:20261115",  # "I was there" list: claim
    "v1:u:IiIiIiIiQiKCIiIiIiIiIg:20261115",  # "I was there" list: remove my mark
    "v1:r:IiIiIiIiQiKCIiIiIiIiIg:20261115:0",  # staff: the roster, page 0
    "v1:a:IiIiIiIiQiKCIiIiIiIiIg:20261115:0",  # roster: confirm every 🙋
    "v1:y:IiIiIiIiQiKCIiIiIiIiIg:20261115:MzMzMzMzQzODMzMzMzMzMw:0",  # roster: mark present
    "v1:n:IiIiIiIiQiKCIiIiIiIiIg:20261115:MzMzMzMzQzODMzMzMzMzMw:0",  # roster: unmark
    # --- b1: announcements (announcements_callbacks.py) ----------------------------------
    "b1:l:t:MzMzMzMzQzODMzMzMzMzMw:0",  # teacher card: 📣 the teacher's announcements
    "b1:l:h:ERERERERQRGBEREREREREQ:0",  # shala card: 📣 the shala's announcements
    "b1:m:t:MzMzMzMzQzODMzMzMzMzMw:n",  # an announcement message: mute the teacher
    "b1:m:h:ERERERERQRGBEREREREREQ:n",  # an announcement message: mute the shala
    "b1:u:t:MzMzMzMzQzODMzMzMzMzMw:n",  # an announcement message: unmute
    "b1:u:h:ERERERERQRGBEREREREREQ:n",
    "b1:m:t:MzMzMzMzQzODMzMzMzMzMw:l",  # the feed: mute
    "b1:m:h:ERERERERQRGBEREREREREQ:l",
    "b1:u:t:MzMzMzMzQzODMzMzMzMzMw:l",  # the feed: unmute
    "b1:u:h:ERERERERQRGBEREREREREQ:l",
    # --- l1: directory listing (directory_listing_callbacks.py) --------------------------
    "l1:o",  # invite screen: my directory line
    "l1:w",  # my directory line: remove (asks)
    "l1:wy",  # my directory line: Yes, remove
    "l1:a:0",  # /admin: the waiting list, page 0
    "l1:k:0",  # /admin: the listed list (re-check), page 0
    "l1:c:33333333-3333-4333-8333-333333333333",  # admin lists: one card
    "l1:y:33333333-3333-4333-8333-333333333333:1",  # admin card: Listed / Still listed
    "l1:n:33333333-3333-4333-8333-333333333333:1",  # admin card: not found (asks)
    "l1:ny:33333333-3333-4333-8333-333333333333:1",  # admin card: Yes, not found
)
