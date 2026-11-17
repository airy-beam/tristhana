## ID-07: teacher requests. A student names a teacher in the bot; here the teacher answers
## (the waiting block on My students) and the student sees who they wait for (the Shala tab).
## Same wording as the bot's `request-*` keys. People and shala names are plain text.
## Nothing the student reads may tell a "no" from silence: no state, no date, no word for a
## refusal.

# The teacher: the block's heading, also the Shala tab's row that opens it.
request-waiting-open = ⏳ Waiting for your answer ({ $count })
# The heading once everyone is answered and only an Undo is left.
request-list-empty = No one is waiting for your answer.
request-list-hint = Confirm only people you know. If you tap "Not my student", the person isn't told.
request-yes-mine = ✅ Yes, my student
request-not-mine = Not my student
request-declined = Noted: not your student. { $name } isn't told.
request-undo = ↩️ Undo
link-student-joined = 👥 { $name } is on your list of students now.
request-gone = This request is no longer open. If this is your student, send them your own link.
request-list-full = This can't be confirmed right now: a list of students or teachers is full. The request stays waiting.
request-all = ✅ Confirm all ({ $count })
request-all-ask =
    { $count ->
        [one] Confirm { $count } person as your student? Confirm only if you know them.
       *[other] Confirm all { $count } people as your students? Confirm only if you know each of them.
    }
request-all-yes = ✅ Yes, confirm all
request-all-done =
    { $count ->
        [one] ✅ { $count } student is on your list now.
       *[other] ✅ { $count } students are on your list now.
    }
request-load-failed = Couldn't load who is waiting. Try again in a moment.

# The student: one line under the name of each teacher they asked. { $shala } is where.
request-waiting-line = ⏳ Waiting for an answer ({ $shala })
request-withdraw = Withdraw…
request-withdraw-ask = Withdraw your request to { $name }? No one gets a message. You can ask them again in about a month.
request-withdraw-yes = Withdraw
