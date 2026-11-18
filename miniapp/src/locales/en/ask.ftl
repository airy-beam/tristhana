## ID-07, UI-06 stage 4B (ADR-0049): a student asks a teacher of their shala from the app.
## Every message here is the bot's (`bot.ftl`), copied under the same key, byte for byte: the
## consent a student gives in the app is the bot's text, so there is one consent record. A test
## (site/src/lib/guide.test.mjs, "words in step") fails until both files agree. Edit the bot's
## text first, then copy it here. Nothing the student reads may tell a "no" from silence.

# The question and both layers of the consent (ADR-0045). A name tapped on either layer
# agrees to all of `request-consent`.
request-ask = Who is your teacher here?
request-ask-one = Is { $name } your teacher?
request-yes = ✅ Yes
request-consent-short =
    • The teacher you pick sees your name{ $me } and what you log from today on: practice or rest, your practice length and your last asana. If nothing shows for a while, they see a short note saying just that.
    • Check-ins, diary notes and the reason for a rest stay private.
    • You can remove a teacher from your list any time. No one gets a message.
request-until-yes = Nothing is shown until they confirm. They get one message with your name.
request-know-them = Pick only a teacher you know.
request-consent =
    If you pick a teacher and they confirm:
    • The teacher you pick sees your name{ $me } and what you log from today on: practice or rest, your practice length and your last asana. If nothing shows for a while, they see a short note saying just that.
    • Check-ins, diary notes and the reason for a rest stay private. All rest you log looks the same, whatever the reason.
    • Any teacher on your list can mark a new asana for you. You get a message and can undo it. They can also send announcements through the bot. You can mute them.
    • Nothing is shown until they confirm. They get one message with your name.
    • Days count from today, even if they confirm a few days later.
    • Until they confirm, you can withdraw your request. You can remove a teacher from your list any time. No one gets a message.
consent-details = 📄 Details
consent-short-back = ‹ In short
invite-decline = Not now

# One line on the screen the person asked from, by what the tap came to (the bot's `_ASKED`).
request-asked = ✉️ Request sent to { $name }. Nothing from your log is shown until they confirm.
request-waiting = You've already asked { $name }. No answer yet.
request-recent = You asked { $name } not long ago. Try again later, or ask them for their invite link.
request-too-many = You've asked several teachers lately. You can ask another in a few days.
request-full = This request can't be sent right now. Try again later.
invite-already = { $name } is already on your list of teachers.
