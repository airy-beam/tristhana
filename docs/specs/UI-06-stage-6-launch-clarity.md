# UI-06 stage 6: launch clarity (every way in leads somewhere, every word says where)

- Status: **accepted** (owner, 2026-11-18: fix all of the audit before launch, blockers, confusing and polish; a Classes list on the shala card; "📅 Another day" beside "☰ Menu" on Today; "🧘 My asanas" as a Menu row; the first question's "My practice" becomes "🧘 Log my practice"). Choices the audit left open are settled in §13 and told, not asked. · Size **L**, five pull requests (§11), branch per slice from `main` (audit at `11b1bea`)
- **Revised 2026-11-18** after the ux-writer's and ashtanga-expert's reviews, the owner's C14 answer (keep «Администратор») and the coordinator's decisions (§13). **Slice A1 is committed (`8071bfa`)**: the four launch targets, the Classes section (`screens/shalas/ShalaClasses.tsx`), `shala-class-every-day`, the class form hint and "Add another class". Anything below marked **"changed after A1, applied in A2"** touches an A1 string or screen: the A2 builder updates the app too.
- Input: `docs/audits/2026-11-18-launch-clarity-audit.md` (B1–B8, C1–C20, polish). Parent: `UI-06-simple-journey.md`; follows stages 4, 4B and 5. Requirements: **UI-06**; touches SC-01/02/03/06, ID-01/04/07, PR-01/07/08, NT-01/03, MD-04, UI-05.
- Related: ADR-0008, 0029, 0044, 0045, 0047, 0048, 0050. New, proposed: **ADR-0051** (a tap on an old Today asks which day).

## 1. Goal and scope
**Goal:** at launch nobody gets stuck: an owner sets up classes from the bot or the app without help, a student never logs the wrong day or goes without a city, a staff teacher sends the right link, and every button says where it goes.
**In:** every audit item; four new Mini App launch targets; the Classes list (bot and app); one new day callback letter; copy en + ru; guides, screenshots, What's new.
**Out:** no API route, schema or migration; no change to use-case rules except the read compositions named in §7; the practice reminder's own buttons (ADR-0051); per-screen guide links in the bot (polish N9 is done in the app only, §5). **No shipped callback letter changes meaning**; two new letters (`d1:n`, `h1:ls`).

## 2. Launch targets (Mini App) and how the bot builds them
*Built in A1 (`8071bfa`).* `launchNav` (`miniapp/src/shell/nav.ts`) learns four `open` values; the bot builds every URL with `screens.app_url`, whose docstring gains the list, and a new `APP_OPEN` set in `screens.py` that a test pins against `nav.ts`'s `case` labels (`tests/bots/test_app_targets.py`).

| `open` | Params | Lands on | Built by (bot) |
|---|---|---|---|
| `shala` | `shala=<uuid>` optional | that shala's card (`start: shala:<id>`), or the Shala root | card "🗓 Add or change classes" and the no-teachers hint's "🏛 Shala in the app", week "🗓 Full week in the app", overview's "🏛 Shala in the app" (no id) |
| `class` | `shala=<uuid>` | the card with a new class form (`class:<id>`, exists) | card "➕ Add a class" (no classes yet), Today's step (B4) |
| `edit-shala` | `shala=<uuid>` | the card with its edit form open (`ShalaOpen` gains `"edit"`, start `edit:<id>`) | card "✏️ Edit the shala" |
| `schedule` | – | Shala tab + `schedule` pushed; Back → root | My schedule "🗓 Full week in the app" |

A bad or missing uuid opens the Shala root; a shala the person left shows the card's `shala-load-failed`, Back → root (as `announce&shala=`). Existing values unchanged.

## 3. Blockers
| # | Bot | Mini App |
|---|---|---|
| B1 | **Card** (`shalas.py::_card`), by `application/policies`: `can_manage_schedule` → the Classes block (§3.1) and "🗓 Add or change classes" → `open=shala&shala=`, or "➕ Add a class" → `open=class&shala=` while none; `can_edit_shala` → "✏️ Edit the shala" → `open=edit-shala&shala=`. `request-no-teachers-hint` (§6) ends "…open the shala in the app, then Teachers and staff." and gets its own button `app-open-shala` "🏛 Shala in the app" → `open=shala&shala=`. **Week** (`classes.py::_week`): `s.manage` → "🗓 Add or change classes" (also on the empty week); not managing and the week cut ("…") → "🗓 Full week in the app" → `open=shala&shala=`. **My schedule** cut: the `my-schedule-more` line becomes the button "🗓 Full week in the app" → `open=schedule`. `ShalaScreens` and `ScheduleScreens` get the app URL as `LinkScreens` has it. | §2 targets; `ShalaScreen` opens Edit for `open: "edit"`. |
| B2 | Classes block on the card (§3.1). | *Built in A1.* Classes section on the card (§3.1). Class form: `class-form-days-hint` under "Repeats on" (**text changed after A1, applied in A2**, §6); after a save the card says `class-form-saved` and the add row reads `class-add-another` for this visit. Setup list unchanged (its step is done by the first class). **Changed after A1, applied in A2:** while the setup list shows its "Add a class" step, the Classes empty state's add row is a plain row, not the primary one (one main action per screen); it becomes primary only when the setup list is not shown (not the owner, or the step is gone). |
| B3 | "Shala and classes" (`home.py::shala`): with `account.shala` set, one read (`shalas.mine`) and one row per shala I am in, `🏛 Name` → `h1:c:<id>` (the card, with B1's buttons), on top; then the student line (only if I am staff nowhere; C12), then `shala-create-another` ("🏛 Create another shala") when I am staff somewhere, else `shala-create`. Text for staff: `welcome-shala-mine`. Back unchanged (`w1:s:<f|o|c>`). `menu-teach` comment and the guide say the row stays until one has students. | – (the Shala tab already lists shalas) |
| B4 | Today (`days.py::_picker`, not the editor): when `account.shala` is staff, `GetNextSteps` runs **in parallel** with the day read; the first step of kind `add_class` or `invite_shala_students` adds its line (`next-class` / `next-shala-invite`, copied from the app) under the day block and one row above the last row: "Add a class" → `open=class&shala=<id>`, or `next-shala-invite-do` → `h1:i:<id>`. No "Not now" in the bot: the step goes once its data exists (as in the app). Other kinds stay app-only. | unchanged |
| B5 | `shala-invite-students` → "➕ Invite students to the shala"; `links-invite` → "➕ Invite my students"; `welcome-path-invite` → "👥 Invite my students"; `shala-join-hint` gains the ux-writer's line on what students do next (join, then pick their teacher); `next-shala-invite-do` → "Invite students to the shala". "For teachers and shalas" (`home.py::teach`) for someone on a shala's staff (`account.shala.staff`): its first row is `shala-invite-students` → `h1:i:<account.shala.id>` instead of the personal invite. The personal invite screen (`invite_screen`), for someone on a shala's staff, adds `invite-own-not-shala` "This is your own link, not the shala's." (pure render from the account). | Same keys, same text (words-in-step); `shala-start-invite` → "Invite my students"; `setup-students` → "Invite students to the shala" (**changed after A1, applied in A2**). |
| B6 | ADR-0051: Today's status buttons and the reasons screen opened from Today (`d1:r:…:t`) use **`d1:n:<date>:<code>`**. On `d1:n`: date = today → saved as `d1:s`; earlier → the message becomes `today-which-day` with one full-width row per date (today's day label, then that date's; both `d1:s`, explicit dates) and a last row `log-back` "‹ Back" → `w1:n` (Today); later → the `DateInFuture` path. `d1:s` unchanged. | – |
| B7 | §3.2. | – (opening the app records the zone, as now) |
| B8 | `calendar_feed.py::_off` and `_on` end with `screens.menu_row`. The "way back" test is extended (§9). | – |

### 3.1 The Classes list
- **Who:** members for whom `can_manage_schedule` holds (owner, Manager, Teacher, Front desk). Students and assistants keep the Schedule by date. The read is the existing `ListClasses` / `GET /api/v1/shalas/{id}/classes` (guard in SQL by that policy: 403/404). **No API change.**
- **Which:** `GET …/classes` returns ended series (ADR-0048), so a pure `domain/classes.py::current_classes(classes, today)` keeps weekly series with no last date or one on/after `today` and one-date classes on/after `today`, sorted weekly first, by first weekday, start, type; `today` is the shala's. A pure `day_runs(weekdays)` turns `{1,2,3,4,5}` into one run "Mon–Fri", three or more consecutive days into a run, others into "Mon, Wed", all seven into `shala-class-every-day` (A1's key; the bot copies it, same text). Both mirrored in `screens/shalas/classText.ts`; one table of cases feeds the pytest and the vitest.
- **Row:** `shala-class-row` = "Mysore · Mon–Fri · 06:00–09:30", then, joined by " · ": the teacher's name, `class-form-every-n` when `every > 1`, `class-form-sum-from` for a future first date, `class-form-sum-end` for a last date, "🌐" and the class's zone label (ADR-0044, viewer-aware) for an online class timed elsewhere. A one-date class shows its date (`day-label`, other).
- **Bot:** in the card's text after the staff line: `shala-classes-title`, one line per class (at most 12, then "…"), or `shala-classes-none`; read-only. The read joins the card's `asyncio.gather` (+1 statement, in parallel); `NotAllowed` / `NotFound` → no block.
- **App** (*built in A1 as `ShalaClasses.tsx`*; one change for A2 in B2's row): a `card` section after the place line, before the announcements: `shala-classes-title` (h2), one `Row` per class → `ClassForm` with `edit: {classId, date: max(shala today, starts_on)}` (ADR-0048's "applies from" proposes that date), then the add row `schedule-add-class` **moved here from `ShalaSchedule`** (key kept: guides quote it); while empty, `shala-classes-none` and the add row as the primary row. `useClasses(shala.id, shala.me.schedule)`: the form already uses this cache.

### 3.2 Asking for the city (B7)
- **Rule (domain, pure):** `journey.asks_for_city(account) = account.timezone is None and account.home_city is None`.
- **Why:** without a zone, "today" is a guess (Moscow for RU, UTC for EN) and no reminder is sent (`notifications.py` skips accounts without a zone). The home city sets the zone (ADR-0029); it does **not** set the moon city (MD-02 follows the person's moon choice, teacher or shala), so the question promises days and reminders only.
- **Where:** after every save while it holds, on the saved screens (`saved_screen`, the practiced summary P0, the pause question, `period_saved`): the line `city-ask` and one row [`city-ask-button` "🏙 Choose my city" → `s1:cp:0`] [`next-not-now` → `s1:n`]. It replaces `app_rows` ("Open the app") on the pause question and My asanas. **Not on Today:** Today keeps one main action (log the day).
- **How it stops:** a city chosen in the bot or the app, opening the app (the zone is recorded, ID-01), or "Not now": `s1:n` keeps its meaning exactly (marks the nudge answered, `NOT_NOW` → never overwrites a chosen city) and its landing, Settings, where the city row stays one tap away. That landing gets one lead line, `settings-city-later` (`SettingsScreens.view` takes an optional lead; only the `not_now` case passes it, so old pre-UI-06 nudges get it too, which fits). Nothing new is stored.

## 4. Confusing
| # | Change (bot · app) |
|---|---|
| C1 | `screens.app_button` takes the label key. "🙏 Teacher and shala" (`overview`): `app-open-shala` "🏛 Shala in the app" → `open=shala`. The "Open the app" rows while the zone is unknown go (B7). |
| C2 | `overview`: for someone on any shala's staff (from the `mine` rows it already reads), `links-empty` becomes `links-empty-staff` ("No teacher on your list."). |
| C3 | Bot `students` (names only) and the app card's Students section, for staff who are not removers: `shala-students-not-yours` under the list and "➕ Invite my students" (`t1:i` / the tab's invite start). |
| C4 | `accept_staff`: lead `shala-staff-welcome` (shala, role, next step). Staff consent gets the language row with a **new letter `h1:ls:<locale>:<code>`** (`h1:l` keeps meaning "student consent"). |
| C5 | `overview` reads `requests.waiting_count` in parallel and shows `waiting_row` on top when > 0. Guide says where. |
| C6 | `links-no-students` (both): a `$shala` select with a default variant (`*[other]`: no shala teaching), the ux-writer's text (§6). App `Students` screen gets "➕ Invite my students" → Shala tab, `start: invite`. |
| C7 | `menu-text-lead` says how a note is kept; `saved_screen` for a rest day gains `note_button(…, "d")` (Back → the day's editor). |
| C8 | Today's last row: [`log-another-day` → `d1:w:<today>`] [☰ Menu]. |
| C9 | The front door's three buttons all carry an emoji, words kept: `welcome-path-practice` "🧘 Log my practice", `welcome-path-invite` "👥 Invite my students" (B5), `welcome-path-shala` "🏛 Shala and classes" (also on "For teachers and shalas" and the teacher's closing screen, which use the same key). `MenuItem.ASANAS` after PRACTICE, `menu-asanas` → the `g1` "open" data that `help-asanas` already uses. `menu_for`'s docstring: at most nine rows. Help keeps its row. |
| C10 | `remind.py` time tap: `ReminderPatch(at=…, enabled=True)` (the chip means "remind me at"; the app's separate switch is unchanged). |
| C11 | P1 (practice details, `practice.py`) drops "✨ How do you feel?" and "📓 Note"; the done summary V has both (*built in B:* V had only ✨, so it gains "📓 Note" on its own row with a new note origin `n1:…:v`, Back → V, or the day's editor once the day is no longer 🧘). Old `n1:…:p` / check-in data still decode; Back lands on P1. |
| C12 | "Shala and classes": the student line first (B3). |
| C13 | `on_location`: the result line goes out with `ReplyKeyboardRemove` (awaited call), then the Settings screen is the webhook reply; also after `settings-location-unknown`. |
| C14 | **Owner: RU «Администратор» stays** for the front desk (Q104 stands). Instead every role picker says what each role can do: the bot's `pick_role` screen lists one `shala-role-hint` line per role it offers under `shala-staff-pick`; the app's staff invite picker (`StaffInvite`) and role editor (`RoleEditor`) show the same line under each role. Lines follow `application/policies.py` (§6), not the audit's guess: **the front desk does manage the schedule** (`_SCHEDULE_ROLES` = Manager, Teacher, Front desk). The owner is never offered, so has no line. |
| C15 | `shala-moon-shared` → one line (ashtanga-expert, §6); the exception (a student whose teacher works elsewhere follows that teacher's city) goes to the guide. The app card's two moon lines become one `shala-moon-summary` "🌙 Moon days (📍 Mysuru): shala closed", with a new select `shala-moon-policy-short`; the bot's card the same. |
| C16 | `ShalaTab`: while `useNextSteps` (cached by Today) holds `add_class` for one of my shalas, that shala's row moves first and is the main row (it opens the card, setup list on top). |
| C17 | Help: `help-shala-classes` "🗓 Shala classes" → `h1:c:<account.shala.id>` when `account.shala.staff` (pure render). |
| C18 | Guides (§10), incl. a new page "You were invited to a shala's staff". |
| C19 | One next step each: `invite-full` (ask the sender for a new link), `shala-full` (ask the shala), `class-invalid` (open the class in the app), `shala-caps` / `class-form-caps` (staff links expire in 7 days; the class cap counts running series). |
| C20 | `ann-announce` → "📣 Announce to the shala"; new `ann-announce-students` "📣 Announce to my students" (`announce_button` with no shala; the app's My students). |

## 5. Polish (one line each; **the ux-writer's review wording is the text to build** for `start-prompt` line 2, `invite-own`, `links-invite-first` (RU kept as it is), the `shala-leave-ask` addition, `settings-privacy-location`, `export-caption` and the C19 next steps)
Location privacy line: no "tzfpy", "ODbL" or "time zone"; "© OpenStreetMap contributors" stays as a link to openstreetmap.org/copyright (attribution kept). Moon note: "the moon at sunrise in your city" (ashtanga-expert). RU «по URL» → «по ссылке». `export-caption`: what to open with what. Badges: "Tap a badge to see what it's for." Trends: a "1 low · 5 high" axis note. RU quotes „…" → «…», EN «…» → "…" (a quotes check joins `words.test.mjs`). "Add a note" → "📓 Note". `start-prompt` names what Other… holds (moon day, sick, travel). App guide links: `guideUrl(locale, page)`; the class form and the Classes section get a quiet "📖 Guide" → `staff/classes/`. `shala-leave-ask` for a teacher: "Your own students stay on your list." A teacher's mark in My asanas says who can undo it. `invite-own`: "send it". `links-invite-first` → "I teach: invite my students" (EN only; RU unchanged).

## 6. Copy (new or changed; EN / RU; RU «ты», no gendered past tense, names after a colon, Tristhana never declined)
Rows marked **UX** use the ux-writer's proposal from its 2026-11-18 review, which replaces the draft shown here; the drafts only show the intent. Rows without the mark are the reviewed text.

| Key | EN | RU |
|---|---|---|
| `welcome-path-practice` | 🧘 Log my practice | 🧘 Отмечать свою практику |
| `welcome-path-invite` | 👥 Invite my students | 👥 Пригласить своих учеников |
| `welcome-path-shala` | 🏛 Shala and classes | 🏛 Шала и занятия |
| `menu-asanas` | 🧘 My asanas | 🧘 Мои асаны |
| `shala-classes-title` · `shala-classes-none` | Classes · No classes yet. | Занятия · Занятий пока нет. |
| `shala-class-row` | { $class } · { $days } · { $start }–{ $end } | (same) |
| `shala-classes-edit` | 🗓 Add or change classes | 🗓 Добавить или изменить занятия |
| `schedule-full-app` | 🗓 Full week in the app | 🗓 Вся неделя в приложении |
| `app-open-shala` | 🏛 Shala in the app | 🏛 Шала в приложении |
| `request-no-teachers-hint` | No one here has the Teacher role yet, so students can't pick a teacher. To give it, open the shala in the app, then Teachers and staff. | В шале пока ни у кого нет роли «Преподаватель», поэтому ученики не могут выбрать учителя. Чтобы дать её, открой шалу в приложении, затем «Преподаватели и команда». |
| `shala-create-another` | 🏛 Create another shala | 🏛 Создать ещё одну шалу |
| `welcome-shala-mine` **UX** | Classes, the student invite and settings are on your shala's card. | Занятия, приглашение для учеников и настройки — в карточке шалы. |
| `shala-invite-students` · `next-shala-invite-do` | ➕ Invite students to the shala · Invite students to the shala | ➕ Пригласить учеников в шалу · Пригласить учеников в шалу |
| `setup-students` (app; changed after A1, applied in A2) | Invite students to the shala | Пригласить учеников в шалу |
| `links-invite` · `shala-start-invite` | ➕ Invite my students · Invite my students | ➕ Пригласить своих учеников · Пригласить своих учеников |
| `invite-own-not-shala` | This is your own link, not the shala's. | Это твоя личная ссылка, не ссылка шалы. |
| `shala-join-hint` (addition) **UX** | They join the shala, then pick their teacher. | Ученики присоединятся к шале, а потом выберут учителя. |
| `class-form-days-hint` (changed after A1, applied in A2) | Pick the days this class runs at this time. A different time or type is a separate class: Mysore Mon–Fri at 06:00 and Led on Sunday at 08:00 are two. Save this one, then add the next. | Выбери дни, когда это занятие идёт в это время. Другое время или тип — отдельное занятие: Майсор пн–пт в 06:00 и Лед-класс в воскресенье в 08:00 — это два занятия. Сохрани это занятие, потом добавь следующее. |
| `class-form-saved` · `class-add-another` (A1) | ✓ Class saved. · ➕ Add another class | ✓ Занятие сохранено. · ➕ Добавить ещё занятие |
| `shala-class-every-day` (A1; the bot copies it) | every day | каждый день |
| `today-which-day` | This message is from an earlier day. Which day is it for: { $label }? | Это сообщение с прошлого дня. На какой день записать: { $label }? |
| `city-ask` · `city-ask-button` | 📍 Which city do you live in? Your days and reminders follow its clock. · 🏙 Choose my city | 📍 В каком городе ты живёшь? Дни и напоминания идут по его часам. · 🏙 Выбрать город |
| `settings-city-later` (lead after "Not now") | Pick your city here any time. | Город можно выбрать здесь в любой момент. |
| `links-empty-staff` | No teacher on your list. | Учителя в списке нет. |
| `links-no-students` **UX** | `$shala` select: `[yes]` names that students of the shala can pick you; `*[other]` asks to send your link | the same two variants |
| `shala-students-not-yours` **UX** | These are the shala's students. They join your own list when they pick you as their teacher or open your link. | Это ученики шалы. В твой список они попадут, когда выберут тебя учителем или откроют твою ссылку. |
| `shala-staff-welcome` **UX** | ✅ You're on the staff: { $shala }. Role: { $role }. The schedule and the student invite are on this card; ☰ Menu now has 🗓 My schedule. | ✅ Теперь ты в команде шалы: { $shala }. Роль: { $role }. Расписание и приглашение для учеников — в этой карточке, а в ☰ Меню появилось 🗓 Моё расписание. |
| `menu-text-lead` **UX** | I can't read messages. To keep a note on a day, tap 📓 Note under it. Here is everything I can do 🙏 | Сообщения я читать не умею. Чтобы сохранить заметку к дню, нажми 📓 Заметка под ним. Вот что я умею 🙏 |
| `help-shala-classes` | 🗓 Shala classes | 🗓 Занятия шалы |
| `shala-role-hint` (new, both; `$role` select) | admin: Everything except deleting the shala and adding managers. · teacher: Classes and schedule, attendance, announcements, the student list; students can pick them as their teacher. · assistant: Attendance and the student list; not the schedule or announcements. · office: Classes and schedule, attendance, announcements, the student list; can remove a student; not the shala's settings or roles. | admin: Всё, кроме удаления шалы и назначения управляющих. · teacher: Занятия и расписание, посещаемость, объявления, список учеников; ученики могут выбрать преподавателя своим учителем. · assistant: Посещаемость и список учеников; без расписания и объявлений. · office: Занятия и расписание, посещаемость, объявления, список учеников; может убрать ученика; без настроек шалы и ролей. |
| `shala-role` office | Front desk (unchanged) | Администратор (unchanged, owner) |
| `ann-announce` · `ann-announce-students` | 📣 Announce to the shala · 📣 Announce to my students | 📣 Объявление для шалы · 📣 Объявление своим ученикам |
| `shala-moon-shared` | 🌙 Staff and students follow this calendar unless they chose a city. | 🌙 Команда и ученики шалы следуют этому календарю, если сами не выбрали город. |
| `shala-moon-summary` (new, both) | 🌙 Moon days (📍 { $city }): { shala-moon-policy-short } | 🌙 Лунные дни (📍 { $city }): { shala-moon-policy-short } |
| `shala-moon-policy-short` (new, both; `$p` select) | closed: shala closed · open: classes as usual · pranayama: pranayama, chanting and talks only | closed: шала закрыта · open: занятия как обычно · pranayama: только пранаяма, чантинг и конференции |
| **Copied app → bot (same text):** `next-class`, `next-class-do`, `next-shala-invite`, `next-not-now`, `shala-edit`, `schedule-add-class`, `shala-class-every-day`, `class-form-every-n`, `class-form-sum-from`, `class-form-sum-end` | | |

`shala-role-hint` restates `application/policies.py` as of `11b1bea`: Manager = `_manages` (edit, roles but Manager, remove non-managers, moderate); Teacher, Front desk = `can_manage_schedule` and `can_announce_to_shala`; Front desk also `can_remove_student`; every staff seat = student list, invite link, attendance. A comment above the key names these policies, so a policy change updates the lines in the same PR.

**Glossary (`docs/glossary.yaml`, same PR as the words):** a shala's **Classes** (the repeating rules; the Schedule is by date; no 🗓 on the heading) / «Занятия»; the two invites ("Invite students to the shala" / «Пригласить учеников в шалу» joins the shala · "Invite my students" / «Пригласить своих учеников» links to me) with EN bare "Invite students" retired in those keys; app buttons say what opens ("🏛 Shala in the app"). No role rename.

## 7. Domain, use cases, API
- **Domain (pure):** `classes.current_classes`, `classes.day_runs`; `journey.asks_for_city`; `journey.MenuItem.ASANAS`. No entity or rule change.
- **Use cases (unchanged rules, new callers):** the bot calls `ListClasses` (card), `GetNextSteps` (Today, staff only), `ShalaUseCases.mine` (Shala and classes), `RequestScreens.waiting_count` (overview). Who sees what stays in `application/policies` (`can_manage_schedule`, `can_edit_shala`, `can_show_join_link`, `can_view_shala_students`) and the SQL guards; handlers only choose rows by them.
- **API:** none; no `tristhana-openapi` / `gen:api` run needed (a slice that finds one must regenerate the client in the same PR).

## 8. Cross-cutting checks
- **Time zones ✔.** Class rows are the rule's wall clock in the class zone; another zone gets its label with the offset only outside the viewer's zone (ADR-0044). "Current" uses the shala's today; B6 uses the person's today (provisional zone while unknown, as now). B7 is the fix for unknown zones; no offset is stored.
- **Privacy ✔.** The Classes list only for those the existing guard lets read it; 1:1 titles stay staff-only. C3 shows staff the names they already see. No 🌸 wording touched; the city question asks for a city, never a location.
- **i18n ✔.** Every string in `.ftl`, en + ru, key and variable parity; shared keys equal across products (ADR-0050 test); RU plurals via Fluent (`class-form-every-n`); labels wrap at 320 px («🗓 Добавить или изменить занятия» checked by eye).
- **Responsiveness ✔.** Answers first, edits in place. Added statements, all in parallel with an existing read: card +1 (classes), Today +1 for staff only (next steps), overview +1 (waiting count); "Shala and classes" +1 for members only. B6, B7, B8, C8, C9, C17 add none. Mini App: no new chunk; the Classes section rides the lazy `ShalaScreen` chunk; initial JS (≤ 150 KB) and CSS must not rise (`check:bundle` before/after A1).
- **Layering ✔.** aiogram only in `bots/telegram/`; new rules pure in `domain/`; import-linter unchanged.

## 9. Tests (pytest with `TEST_DATABASE_URL`; vitest also `TZ=UTC`)
- **Domain:** `current_classes` (ended, ending today, future one-off, past one-off, order), `day_runs` (Mon–Fri, Mon/Wed/Fri, Sat–Mon wrap is two runs, all seven), shared case table with vitest; `asks_for_city` (zone set, `NOT_LISTED`, never chosen); `menu_for` with ASANAS (order, nine at most).
- **Bot:** card per role (owner/manager/teacher/front desk/assistant/student): Classes block or none, buttons and their `web_app` URLs; week and empty week buttons; My schedule cut → `open=schedule`; Shala and classes for nobody / student / staff of two (B3, C12); teach screen for staff (B5); Today: step for an owner, none for a student, no extra read for a non-staff account (B4); `d1:n` today / yesterday / future and the reasons screen's letter (B6); city line on each saved screen, gone after a city, `s1:n` or a zone (B7); feed screens end with the Menu (B8); C2–C7, C9–C13, C17, C20 one test each; `h1:ls` re-renders the staff consent. **Stale buttons:** `d1:n` and `h1:ls` added to the frozen list in both worlds; `d1:s`, `h1:l`, `s1:n` keep their screens. **Way back:** `test_every_screen_the_menu_and_help_open_has_a_way_back` goes two taps deep, following only an allow-list of callback shapes that just show a screen (never a save, remove, leave, rotate or consent tap), and adds Today's "📅 Another day", the feed screens and the Classes card. `test_app_targets.py`: every `APP_OPEN` value has a `case` in `nav.ts`.
- **Mini App:** `nav.test.ts` (four targets, bad uuid, Back paths; A1); `Shalas.test.tsx` (Classes section for `me.schedule` only, rows and order, tap opens the form with the proposed date, no `/classes` read for a student, `open: "edit"`; A1). **A2 adds:** the empty state's add row is plain while the setup list shows its step and primary otherwise; the new `class-form-days-hint` and `setup-students` text. `ShalaTab.test.tsx` (C16 main row; A1). **C adds:** `Students.test.tsx` (C6 invite); `ShalaScreen` moon summary line (C15); a role hint under each role in the staff invite picker and the role editor (C14).
- **Bot, added by the reviews:** B6 rows are one date per row and the last row is `log-back` → `w1:n`; `invite-own-not-shala` only for staff; `settings-city-later` only after `s1:n`; the role picker lists one `shala-role-hint` line per role it offers.
- **Words:** `words.test.mjs` with the new glossary lines and the quotes check; the guide's words-in-step test with the copied keys; `test_i18n*.py` text pins (`welcome-path-practice`, invites, `ann-announce`, `menu-text-lead`, consent texts untouched).

## 10. Guides, What's new, screenshots (`/guide-update UI-06`, EN + RU twins)
- **Pages:** `staff/classes` (worked example: Mysore Mon–Fri 06:00 + Led Sunday 08:00 = two classes, shown as the app prints them, e.g. "Mysore · Mon–Fri · 06:00–09:30" and "Led Full Primary · Sun · 08:00–09:30"; the Classes list; the bot's buttons; what each role can do, as `shala-role-hint`), `teachers/moon-days` (the exception: a student whose main teacher works elsewhere follows that teacher's city; one whose teacher works at this shala follows the shala), `staff/create-shala` (step 1; the Menu row stays until you have students), `staff/change-class` (open a class from the list), `teachers/invite-students` (step 1; the two links), `teachers/what-you-see` ("at the top of My students"), `students/log-practice` (Another day on Today; the which-day question replaces "from tomorrow the bot opens on today"; the first question's label), `students/my-asanas` (Menu row), `students/settings` and `start/first-steps` (the city question), `students/reminders` (a time turns it on), `students/check-in-and-diary` (a note on a rest day; typing outside the prompt), `students/my-shala`, `start/bot-and-app` (app buttons say where they open), `reference/faq`. **New:** `staff/joined-staff` "You were invited to a shala's staff" (+ `ru/`), with `features: [SC-01, UI-06]`.
- **What's new** (EN + RU), one entry "Ready for launch": the Classes list and the bot's buttons into the app; 📅 Another day on Today and 🧘 My asanas in the Menu; the bot asks which day for yesterday's Today and asks your city; the two invites named apart; announcements named by audience.
- **Screenshots:** a full re-run (en + ru): labels change on most bot shots. New: `bot-which-day`, `bot-city-ask`, `bot-staff-welcome`, `app-shala-classes`. Changed on purpose: `bot-today`, `bot-menu`, `bot-start`, `bot-shala`, `bot-schedule`, `bot-help`, `bot-teachers`, `app-shala`, `app-class-form`, `app-shala-tab`. Check 320 px, Russian, dark.

## 11. Slices (one pull request each; each green alone: pytest, ruff `--no-cache`, pyright, lint-imports, vitest also `TZ=UTC`, lint, typecheck, format, `check:bundle`, site tests and build, `check:guide`)
A **key both products define changes in both in the same slice** (words-in-step test); a slice that renames or moves a quoted key fixes the quoting page in that slice; prose and screenshots wait for D.
1. **A1. App: shalas and classes — committed (`8071bfa`):** §2 targets; Classes section (`ShalaClasses.tsx`) with `current_classes` / `day_runs` mirrors and the shared case table; the add row moved; B2 form hint and "Add another class"; `shala-class-every-day`; C16 (`ShalaTab` reads the next steps).
2. **A2. Bot: shalas and classes:** B1 (card, week, My schedule, the no-teachers hint's button), Classes block, B3, B4, B5 (bot + app keys, `welcome-path-invite`, `invite-own-not-shala`), C1, C12, C17; `APP_OPEN` and its test. Glossary: Classes, the two invites. **App items changed after A1:** the new `class-form-days-hint` (en + ru), `setup-students`, `shala-invite-students` / `links-invite` / `shala-start-invite`, and the Classes empty state's add row as a plain row while the setup list shows its step.
3. **B. Student journey:** B6 (+ ADR-0051, frozen list), B7 (+ `settings-city-later`), B8 and the way-back test, C7, C8, C9 (the three emoji front-door buttons), C10, C11, C13.
4. **C. Teacher and staff:** C2, C3, C4 (+ `h1:ls`), C5, C6, C14 (role hints, bot and app), C15, C19, C20.
5. **D. Polish, guides, screenshots, notes:** §5; §10 in full; ux-writer and ashtanga-expert review the copy before the final suite.
- **Ops ☁️ (ask the owner):** none required; `set_webhook.py` only if the command menu changes (it does not).
- **Notes on acceptance (notes-keeper, not done by this spec):** the owner's four answers and §13 numbered in `03 Open Questions & Decisions.md`; ADR-0051 in `04 Architecture.md`; UI-06 stage 6 in `02 Requirements.md` and `09 Roadmap.md`; the audit linked from the roadmap.

## 12. Risks
- **Old Today messages** (before B) still save their own date; they age out. **Stale buttons:** only new letters; the frozen list grows.
- **Bot Today for an owner** shows the add-class step every day until a class exists; no Not now. Mitigation: the step is one line and goes with the first class.
- **Card load:** +1 statement per card view, also for students (the read fails fast on the guard); watch p50 on the card in the PR.
- **Two buttons to one place** (`open=shala` from Add or change classes and Full week): different words for different intents; the card shows both the list and the week.
- **RU width** of the new labels at 320 px; **guide drift** while A–C ship before D (all before launch).
- **C10** changes a silent behaviour: a person who set a time with reminders off now gets them; the screen shows 🔔 on, with the switch beside it.

## 13. Decisions made in the spec (by Claude, the owner is told)
1. **B7 placement:** on every saved screen while the zone and the city are unknown, never on Today; one row [🏙 Choose my city] [Not now]. The question promises days and reminders, not moon days (the home city does not set the moon city, ADR-0029, MD-02). It stops on a city, on opening the app, or on Not now, which reuses `s1:n` (same meaning, lands on Settings, now with the lead `settings-city-later`). No stored flag.
2. **C14 (owner's answer):** RU «Администратор» stays for the front desk (Q104). Every role picker, bot and app, shows one line per role saying what it can do, taken from `application/policies.py`; the front desk does manage the schedule there, so its line says so.
3. **Classes list audience:** those who may manage the schedule (the existing API guard); students and assistants keep the Schedule by date. In the bot the rows are text, not buttons; one app button edits.
4. **B6:** a new letter `d1:n` for Today's taps; the question offers today and the carried date (ADR-0051).
5. **B4 in the bot:** only the two shala steps, no Not now; reminder and position steps stay app-only (the bot has its own offers).
6. **B5 in the Menu:** "For teachers and shalas" offers staff their shala's invite; the personal invite is on the shala's student list (C3) and My students.
7. **Targets:** `shala`, `class`, `edit-shala`, `schedule`; the Classes button opens the card (`open=shala`), not a separate list screen.
8. **The add row** moves from the Schedule section to the Classes section (one place to add a class; key kept).
9. **C15:** one moon line in both products, policy included, in the ashtanga-expert's words; the teacher-elsewhere exception lives in the guide.
10. **Polish attribution:** "© OpenStreetMap contributors" stays as a link; "ODbL", "tzfpy" and "time zone" leave the line.
11. **Slicing:** five PRs instead of four: A splits into app (A1) and bot (A2) so the bot never links to a target the app does not know.
12. **First-run buttons (coordinator):** all three carry an emoji, words kept: "🧘 Log my practice", "👥 Invite my students", "🏛 Shala and classes".
13. **Personal invite for shala staff (coordinator):** one line, "This is your own link, not the shala's."
14. **One main action on a new shala's card (coordinator, A1 follow-up):** while the setup list shows "Add a class", the Classes empty state's add row is plain; it is the primary row only when the setup list is not shown.

## 14. Questions for the owner
None.
