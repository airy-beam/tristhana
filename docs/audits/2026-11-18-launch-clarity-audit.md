# Launch clarity audit (2026-11-18)

Read-only audit of `main` at 11b1bea, after UI-06 stages 1–5. Four journeys were walked in both the bot and the Mini App, from the code, the copy and the guide screenshots: a shala owner setting up, a student, a teacher (private and on a shala's staff), and the whole product's navigation between bot and app. Trigger: the owner could not find how to set up a schedule from the bot, and a teacher asked how to set classes for different days of the week.

Severity: **blocker** = a person will likely give up or ask for help at launch; **confusing** = they will guess or take a wrong turn; **polish** = small. Source IDs: O (owner), S (student), T (teacher), N (navigation).

## Blockers

| # | What a person runs into | Where | Fix | From |
|---|---|---|---|---|
| B1 | **Classes and shala settings can't be reached from the bot.** The shala card, its week, the empty week ("No classes these days."), "The full week is in the app." and "Roles are set in the app." have no button into the app. The app can't be opened on a given shala at all: its launch parameter knows only `practice`, `new-shala`, `settings`, `announce`, `listing`. | `shalas.py:289-337`, `classes.py:228-249, 302-304`, `bot.ftl:848`, `miniapp/src/shell/nav.ts` | App: launch targets `open=shala&shala=<id>` and `open=class&shala=<id>` (the Shala tab already handles `shala:<id>` and `class:<id>`), and `open=schedule`. Bot: "🗓 Add or change classes" and "✏️ Edit the shala" on the card for staff who may; the same on the week and its empty state; "🗓 Full week in the app" under a cut-short week. | O1, N1, T4, N7, O5 |
| B2 | **Nothing says a different time or type means another class.** "Mysore Mon–Fri 06:00, Led Sunday 08:00" needs two classes; neither the form nor the guide says so, the setup list ticks "Add a class" after the first, and there is no list of a shala's classes (a class can only be found through a date in the week). | class form, setup list, `staff/classes.md` | A hint under "Repeats on"; after saving, "➕ Add another class"; a worked example in the guide; a **Classes** section on the shala card listing each class ("Mysore · Mon–Fri · 06:00–09:30") that opens its form. | O4 |
| B3 | **"Shala and classes" ignores the shala you already run.** An owner without students still has this Menu row; it only offers "🏛 Create a shala" again (a duplicate is one tap away). The guide says the row goes away once you have a shala; the code hides it only once you have students. | `domain/journey.py:61-70`, `home.py:141-159` | For someone on a shala's staff: their shala(s) first ("🏛 Name" → the card, with B1's buttons), then "🏛 Create another shala". The guide and the `menu-teach` comment say what the code does. | O2, N3, N4, T9 |
| B4 | **After creating a shala in the app, the chat never says what's next.** The app's Today says "add your first class"; the bot's Today says nothing. | `days.py`, `next_steps` | The same next step on the bot's Today, with the B1 button. | O3, O10 |
| B5 | **Two different links are both called "➕ Invite students".** One joins the shala (students then pick a teacher); the other links students to the teacher personally and joins no shala. A staff teacher sees both and will send the wrong one. | `bot.ftl:857, 957`, `app.ftl:606, 759` | "➕ Invite students to the shala" / «➕ Пригласить в шалу» and "➕ Invite my students" / «➕ Пригласить своих учеников»; one line under the shala link: "They join the shala, then pick their teacher." The Menu's "Invite students" for shala staff opens the shala's own invite. | T1, N3 |
| B6 | **Yesterday's Today message logs yesterday.** Today's buttons carry a fixed date; if the last message in the chat is yesterday's unanswered Today, tapping 🧘 the next morning saves yesterday. | `days.py:236-252, 477-484` | When a tap from Today arrives for a day that is no longer today, ask which day: [Today, Thu, Nov 19] [Wed, Nov 18]. The guide's "from tomorrow the bot opens on today" is corrected. | S1 |
| B7 | **The bot never asks for the city.** Without it, moon-day reminders never come (they skip anyone without a time zone), moon days fall back to Mysuru, and "today" is a guess (Moscow for RU, UTC for EN). Only opening the app sets it. | `infrastructure/db/notifications.py:259`, `domain/days.py:23` | While the city is unknown, one line and a button after the first save: "📍 Which city are you in? Your days, moon days and reminders follow its clock." [📍 Choose my city]. | S2 |
| B8 | **The calendar link screens are dead ends** (no Back, no Menu), reached from My schedule, Moon days and Settings. | `calendar_feed.py:70-112` | Add the Menu row; extend the "every screen has a way back" test to them. | N2 |

## Confusing

| # | What | Fix | From |
|---|---|---|---|
| C1 | "Open the app" buttons that don't say why, and on "🙏 Teacher and shala" it opens Today, not the Shala tab. | Say what opens ("🏛 Open in the app", "🕐 Set my time in the app"); new `open=shala` target. | S3, N5, O6 |
| C2 | "🙏 Teacher and shala" tells staff and owners how to *join* a shala, above the shala they run. | Skip that line for anyone on a shala's staff. | O6, T7 |
| C3 | A staff teacher sees the shala's students as plain names, with no word on why none are "theirs". | A hint under the list and "➕ Invite my students". | T2 |
| C4 | Accepting a staff invite opens the card with no "you're in" and no next step; the staff invite has no language switch. | A lead line naming the shala and role, and what happens next; the language row. | T3, T8 |
| C5 | A teacher's first requests can arrive before "👥 My students" is in the Menu. | The waiting row on "🙏 Teacher and shala" too; guide says where. | T5 |
| C6 | Empty "No students on your list." and the app's Students screen has no Invite button. | "No students yet. Send your link, or students of your shala can pick you." plus the button. | T6, N11 |
| C7 | A typed note outside Telegram's reply is lost; the answer is only "I can't answer messages yet." A rest day's Note is behind ✏️ Change. | Say how to keep a note; a 📓 Note button under a saved rest day. | S4 |
| C8 | No obvious way to log a past day from the bot's Today (three taps through Help). | "📅 Another day" beside ☰ Menu on Today. | S5 |
| C9 | "My practice" on the first question opens Today; "📊 My practice" in the Menu opens the app. My asanas is only under Help. | Owner's call on the first-question label; "🧘 My asanas" in the Menu. | S6 |
| C10 | Tapping a reminder time while reminders are off saves it silently and nothing comes. | A time tap turns the reminder on. | S7 |
| C11 | Practice details can show 11 buttons at once. | "How do you feel?" and Note leave the details screen (the Done screen has them). | S8 |
| C12 | "Shala and classes" shows a student "🏛 Create a shala" first; the line for students (ask your shala for its link) comes second. | Student line first. | S9 |
| C13 | Sharing a location answers with no buttons; the failure says "pick your city in Settings" with nothing to tap. | Follow with the Settings screen. | N6 |
| C14 | RU roles: «Администратор» (front desk, limited) next to «Управляющий» (full rights). An owner will give the wrong one. | «Ресепшен» for the front desk role. | O7 |
| C15 | The moon paragraph on every shala card is dense; the app card has two "🌙 Moon days" lines. | One short line. | O8 |
| C16 | On the app's Shala tab, an owner's main button is the read-only "🗓 My schedule". | While the shala has no classes, the shala row (or "➕ Add a class") leads. | O9 |
| C17 | Help has nothing for an owner. | "🗓 Shala classes" in Help for staff. | O11 |
| C18 | Guides out of step: create-shala step 1, invite-students step 1, "at the top of My students"; no page for someone invited to a shala's staff. | Correct the sentences; a short page "You were invited to a shala's staff". | T9, T5 |
| C19 | Errors that don't say what to do (`invite-full`, `shala-full`, `class-invalid`, caps). | One next step each. | N10 |
| C20 | Two "📣" buttons with different audiences under near-identical labels. | "📣 Announce to my students" / "📣 Announce to the shala". | T12 |

## Polish

Technical words in the app's location privacy line ("tzfpy", "ODbL", "time zone") and the moon note ("lunar day at sunrise"); RU «по URL»; export caption; badges: say a badge can be tapped; "How you've felt" charts without a 1–5 scale; RU quotes „…" → «…» and EN «…» → "…"; "Note" vs "Add a note"; "Other…" gives no hint; guide links go to the home page only (link each screen to its own page); leaving a shala doesn't say a teacher's own students stay; a wrongly marked asana: say who can undo it; `invite-own` still says "share"; "I teach: invite students" vs "Invite students". (S10–S15, N8, N9, N11, T10, T11, T13)

## What already works

The daily core (three choices, rest never a failure), consent and privacy (short and full texts, 🌸 discreet), the teacher request flow (a "no" is never told, Undo, Confirm all asks first), the two-field shala creation and setup list in the app, the class form's Mysore presets, a date's sheet (cancel, substitute, "Tell students…"), every app screen has Back, every top-level bot screen has the Menu, and the bot and the app share their words.
