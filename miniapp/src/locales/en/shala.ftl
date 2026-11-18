## Setting up a shala and its classes (UI-06 stage 4, ADR-0048). Loaded with the shala card's
## lazy chunk (`shalaCopy`); the card's other copy is in app.ftl.

## The class form: type, start and days, then "More options".
class-form-new-title = New class
class-form-edit-title = Change the class
class-form-type = Type
# $zone: "Almaty", or "Almaty (UTC+5)" for staff in another zone.
class-form-start = Start, { $zone }
# Two chips under this label: regularly (on weekdays, every N weeks), or one date.
class-form-when = When
class-form-weekly = Regularly
class-form-once = One date
class-form-days = Repeats on
# Under the weekday chips (UI-06 stage 6, B2): one class is one type at one time.
class-form-days-hint = A different time or type is another class: Mysore on weekdays and Led on Sunday are two. Save this one, then add the next.
class-form-date = Date
class-form-days-needed = Choose at least one day, or “One date”.
class-form-day-off-warning = One of the chosen days is the shala's day off.
class-form-more = More options
# The parts of the one line under "More options", " · " between them.
class-form-sum-until = until { $time }
class-form-sum-length = { $minutes } min
class-form-sum-from = from { $date }
class-form-sum-end = through { $date }
class-form-until = Until
# Minutes. Never "Length": in the practice details that word means how far in the series.
class-form-length = How long
class-form-length-chip = { $minutes } min
class-form-length-other = Enter minutes
# The field under the "Enter minutes" chip: a number, with "min" after it.
class-form-minutes = How many minutes
class-form-min = min
class-form-minutes-invalid = Enter 15 to 480 minutes. The class needs to end by midnight.
class-form-title = Title (optional)
# An example in the empty title field.
class-form-title-example = Full Primary
class-form-teacher = Teacher
class-form-no-teacher = —
class-form-every = How often
class-form-every-n = { $n ->
        [1] every week
       *[other] every { $n } weeks
    }
class-form-from = First date
class-form-end = Last date (optional)
class-form-online = 🌐 Online
class-form-zone = Times in
# Changing a class that has already run (ADR-0048).
# One sentence instead of a date field; "Another date" brings the field, labelled
# "Changes apply from". $date: "Mon, Nov 16".
class-form-applies-on = Changes apply from { $date }.
class-form-applies-other = Another date
class-form-applies = Changes apply from
class-form-applies-hint = Earlier dates stay as they were.
# After the two lines above, when the class already has a last date (a later change may begin
# after it; the app does not know, so it names only the date). $date: "Thu, Dec 31".
class-form-applies-last = The changes apply through the class's last date: { $date }.
# $zone: the city an online class is timed in, "Berlin (UTC+1)".
class-form-applies-zone = Earlier dates stay as they were. The date goes by { $zone } time.
class-form-window-invalid = The class needs to end after it starts, and by midnight.
class-form-end-early = The last date is before the first one. Choose a later last date.
class-form-end-before-applies = The last date is before the date the changes apply from. Move one of them.
class-form-save = Save the class
class-form-failed = Couldn't save the class. Check the times and try again.
class-form-caps = That's the limit for this shala for now.
class-form-gone = This class has just changed or was removed. Here's the current schedule.
# Back with something typed and not saved.
class-form-discard-ask = Leave without saving this class?
class-form-discard-yes = Don't save
class-form-discard-no = Keep editing
# Deleting a class that has a last date: the dates that go. $from, $to: "Jan 5, 2026".
class-delete-ask-range = Delete this class from { $from } through { $to }? Anything after that stays. No one gets a message.

## A class on one date: what is for this date, and what is for the whole class.
# $day: "Mon, Nov 16".
occurrence-this-date = This date: { $day }
occurrence-whole-class = The whole class
class-edit = ✏️ Change the class…
# Only on a date that has not begun. $day: "Mon, Nov 16".
class-end = ⏹️ End this class from this date…
class-end-ask = End this class from { $day }? That date and later ones go from the schedule. Earlier dates stay. No one gets a message.
# The same question for a class that already has a last date. $end: "Dec 31, 2026".
class-end-ask-range = End this class from { $day }? That date and later ones through { $end } go from the schedule. Anything before or after stays. No one gets a message.
class-end-yes = End the class
class-end-first = This is the class's first date. To remove the class, open “Change the class…” and delete it there.
occurrence-tell = 📣 Tell students…
# The announcement's text after a class is cancelled; the person edits it before sending.
# Written as a teacher would write it to the shala: a greeting, the fact, a warm sign-off
# that also fits a conference or a chanting class (no mat).
# $class: "Mysore" or "Led Full Primary". $day: "Mon, Nov 16". $time: "06:00 Almaty (UTC+5)".
ann-cancel-draft = Hi everyone. { $class } on { $day } at { $time } is cancelled. See you next time 🙏

## The owner's setup list on a new shala.
setup-title = Set up your shala
setup-class = Add a class
setup-students = Invite students
setup-staff = Invite teachers and staff
# The quiet second line of the third step.
setup-staff-note = Optional
setup-staff-skip = I teach alone
setup-done-mark = done

## The shala card's Classes (UI-06 stage 6, spec §3.1): each class as it stands, a row each, for
## those who may manage the schedule. The Schedule below is by date.
# No 🗓 here: the Schedule's heading has it.
shala-classes-title = Classes
shala-classes-none = No classes yet.
# One class: $class "Mysore" or "Led Full Primary", $days "Mon–Fri" or "Mon, Wed" (from the
# weekday names) or a date, $start and $end "06:00", "09:30".
shala-class-row = { $class } · { $days } · { $start }–{ $end }
# $days for a class on all seven days.
shala-class-every-day = every day
# On the card after a class was saved from the form, for this visit.
class-form-saved = ✓ Class saved.
# The Classes' add row after a save, for this visit (before: schedule-add-class).
class-add-another = ➕ Add another class
