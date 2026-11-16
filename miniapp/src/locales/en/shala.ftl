## Setting up a shala and its classes (UI-06 stage 4, ADR-0048). Loaded with the shala card's
## lazy chunk (`shalaCopy`); the card's other copy is in app.ftl.

## The class form: type, start and days, then "More options".
class-form-new-title = New class
class-form-edit-title = Change the class
class-form-type = Type
# $zone: "Almaty", or "Almaty (UTC+5)" for staff in another zone.
class-form-start = Start, { $zone }
class-form-days = Repeats on
class-form-once = One date only
class-form-weekly = Repeat weekly
class-form-date = Date
class-form-days-needed = Choose at least one day, or tap "One date only".
class-form-day-off-warning = One of the chosen days is the shala's day off.
class-form-more = More options
# The parts of the one line under "More options", " · " between them.
class-form-sum-until = until { $time }
class-form-sum-length = { $minutes } min
class-form-sum-from = from { $date }
class-form-sum-end = to { $date }
class-form-until = Until
class-form-length = Length
class-form-length-chip = { $minutes } min
class-form-length-other = Other
class-form-ends = Ends at
class-form-title = Title (optional)
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
class-form-applies = Changes apply from
class-form-applies-hint = Earlier dates stay as they were.
# $zone: the city an online class is timed in, "Berlin (UTC+1)".
class-form-applies-zone = Earlier dates stay as they were. The date is by the clock in { $zone }.
class-form-window-invalid = The class needs to end after it starts, and by midnight.
class-form-save = Save the class
class-form-failed = Couldn't save the class. Check the times and try again.
class-form-caps = That's the limit for this shala for now.
class-form-gone = This class has just changed or was removed. Here's the current schedule.

## A class on one date: what is for this date, and what is for the whole class.
# $day: "Mon, Nov 16".
occurrence-this-date = This date: { $day }
occurrence-whole-class = The whole class
class-edit = ✏️ Change the class…
occurrence-tell = 📣 Tell students…
# The announcement's text after a class is cancelled; the person edits it before sending.
# $class: "Mysore" or "Led Full Primary". $day: "Mon, Nov 16". $time: "06:00 Almaty (UTC+5)".
ann-cancel-draft = Class cancelled: { $class }, { $day }, { $time }.

## The owner's setup list on a new shala.
setup-title = Set up your shala
setup-class = Add a class
setup-students = Invite students
setup-staff = Invite teachers (optional)
setup-staff-skip = I teach alone
setup-done-mark = done
