# UI-06 stage 2: the Mini App shell (three tabs, a gear, the Today tab)

- Status: **proposed** (the design in §1 is approved: owner, 2026-11-16, Q300 and Q304; open points are Q331–Q335 in §12) · Size **L**, one pull request, branch `ui-06/stage-2-app-shell` on top of stage 1 (PR #108)
- Parent: `docs/specs/UI-06-simple-journey.md` (§1, §3 "Mini App", §10). Requirements: **UI-06**; changes UI-03, UI-04, PR-01/02/06/07; touches PR-10, ID-04, SC-01/03, MD-03; UI-02 depends on Q331.
- Related: ADR-0013, 0015, 0021, 0029, 0044 (its TypeScript twin lands here). New, proposed: **ADR-0047** (three tabs and one stack; Back or tabs, never both).

## 1. Scope
**In:** a bottom tab bar Today / Practice / Shala and a gear; the Today tab (three-choice day card, folded details, one "next step" card, today's class and next moon day as rows); the existing Stats and "Teachers and students" screens moved under the Practice and Shala tabs as they are; launch links re-targeted; the ADR-0044 label on the Today tab; one read-only endpoint for the next step.
**Out (later stages):** the Practice tab's layout and Settings pages (3); the Shala tab's layout, shala setup, class editing (4); wording sweep (5). No stored role, no analytics, no change to what a teacher or a shala sees, no bot change, no migration.

## 2. Navigation model (ADR-0047)
- **State:** `Nav = { tab, stack, start }` in a pure reducer (`shell/nav.ts`); no router library, the address never changes (Telegram owns it). `Tab = "today" | "practice" | "shala"`. `Screen = settings{focus?: "day-off" | "remind"} | asanas | moon | schedule | students | announce{shala} | listing`. `start` is a one-time intent for the Shala root: `create` (form open and focused), `invite` (invite card open) or `shala:<id>` (that shala's card open).
- **What renders:** the top of the stack, else the tab's root. One thing is mounted at a time. A tab switch clears the stack; coming back to a tab shows its root (cached queries make it immediate). Tapping the active tab scrolls to the top.
- **Telegram's Back:** on a tab root there is no Back layer, so Telegram shows Close, and Android's hardware back leaves the app, as on Home today. Inside a stack, Back pops one screen. Layers inside a screen (a shala card over the lists, Badges over Stats, the day editor, an unsaved note) work as today.
- **Back or tabs, never both:** the tab bar is drawn only while no Back layer is mounted. `telegram/index.ts` already keeps the layer list; it gains `useBackShown()` and counts layers also where Telegram's button is unavailable (dev browser, old clients). So the bar is on the three roots and hidden in every pushed screen, form, editor and unsaved note, without the shell knowing how deep a screen is (Q332).
- **Gear and Telegram's ⋯ "Settings":** one route. Both call `openSettings` = push `settings` unless it is already on top. The gear (44×44, top right) shows on the three roots; ⋯ works everywhere. Back returns to where it was opened.
- **Launch links** (read once; the values stay a contract):

| `?open=` | Lands on | Back |
|---|---|---|
| none, unknown, malformed | Today root | none |
| `practice` | Practice root | none |
| `new-shala` | Shala root, `start: create` | none |
| `announce` (`&shala=<uuid>`, else null) | Shala tab + `announce` (compose) | Shala root |
| `listing` | Shala tab + `listing` | Shala root |

- **Where everything went (nothing becomes unreachable):**

| Today (`View` in `App.tsx`) | Stage 2 |
|---|---|
| `home` | Today root |
| `stats` (Home row) | Practice root; the Home row is gone |
| `progression` (Home row) | first row on the Practice root (`progression-open`) → `asanas` |
| `settings` (Home row, ⋯) | gear or ⋯ → `settings` |
| `day-off` (link on Stats) | `settings{focus: "day-off"}` over Practice; Back → Practice |
| `links` (row in Settings) | Shala root; the Settings row is removed (Q300) |
| `students`, `links-students` | `students` over the Shala tab, from the row in its students card; the Home row is deleted, not duplicated |
| `my-schedule` (Home row) | first row on the Shala root → `schedule`; also behind Today's class row |
| Moon card on Home | Today's moon row → `moon`: the card whole (three days, source lines, home-city line, calculation note) |
| Tour offer on Home, "Quick tour" in Settings | retired (Q331); "Guide" stays in Settings |

- **First run and `welcomed_at`:** the app neither reads nor writes it; `Me` is unchanged. The app has no front door: a new person lands on Today, whose card is the first step. Someone who opens the app first and does nothing still meets the bot's front door on their first `/start`; someone who logged in the app gets the bot's Today (activity is derived).

## 3. Files under `miniapp/src`
- **Add:** `shell/nav.ts` (reducer, `launchNav(search)`); `shell/Shell.tsx` (tab or screen, gear, focus and scroll on a switch); `shell/TabBar.tsx`; `shell/ChunkBoundary.tsx` (error boundary round the lazy tabs and screens: a failed chunk shows `chunk-failed` and a retry, the bar stays; Today is never lazy, so logging never waits for a second chunk); `screens/DayLog.tsx` (the one day card, for today and for any date); `screens/DayChoice.tsx` (three choices and the reasons); `screens/NextStep.tsx`; `screens/TodayRows.tsx` (class row, moon row); `screens/useChunk.ts` (load on tap, failure does nothing; replaces `tour/useTour.ts`); `screens/dayExtras.ts` (lazy: `PracticeDetails` + `CheckIn`); `screens/moon/MoonScreen.tsx` (lazy: the former `MoonCard` and `MoonSource`); `screens/cityName.ts`; `screens/timeLabel.ts` (ADR-0044).
- **Change:** `App.tsx` (providers, deleted / not-in-Telegram / session, then `<Shell>`; the `View` union and row components go); `Home.tsx` (the Today root; unchanged API); `TodayCard.tsx` (thin: `DayLog` for the server's today plus the moon-today line); `stats/DayEditor.tsx` (thin: `DayLog` for a date, its label, Done; Q335); `PracticeDetails.tsx` (loses "same as last" and its hint, `lastTimeText` moves to `practiceText.ts`, start time under `practice-more`, open when one is stored); `CheckIn.tsx` (the editor only: its own fold and the auto-open go to `DayLog`); `practiceText.ts` (`zoneLabel` delegates to `timeLabel.ts`, optional `viewer`); `stats/Stats.tsx` (`root`: no Back layer, no back link; the slot that held the back link holds the My asanas row, so it also shows when stats fail to load); `settings/Links.tsx` (`root`, `start`, `onSchedule`, the empty state of §4, heading `tab-shala`); `settings/Settings.tsx` (rows `links-title` and `tour-open` and their props removed; `focus: "remind"`); `telegram/index.ts` (`useBackShown`, `setBottomBarColor`); `api/client.ts` (`useNextSteps`, invalidations); `theme/tokens.css` (bar, gear, choices, entries; tour rules removed).
- **Delete:** `screens/tour/` (five files), `screens/onboard.ts`, `screens/MoonCard.tsx` (split as above), every `data-tour` attribute (all subject to Q331).

## 4. Each tab, in display order
**Today** (first chunk, not lazy): greeting + gear · travel prompt (existing, when the phone's clock differs) · **day card** (§5) · **next step** (§6; at most one) · **today's class** row (in a shala with a class today; opens `schedule`) · **next moon day** row (existing `moon-day-line`; opens `moon`) · server status line (existing).

| Person | Sees on Today |
|---|---|
| New (nothing logged) | card with the prompt and three choices; moon row. No next step before the first log: the card is the step |
| Student | card; next step: reminder, then where the practice ends, then nothing; class row when in a shala; moon row |
| Teacher | card; "invite your first student" until one joins; then as a student |
| Shala owner | card; "add a class", then "invite students"; class row; moon row |

**Practice** (lazy `Stats`, as it is): heading + gear · My asanas row · consistency · year · month and its day editor · Badges row · Check-ins row. Same for everyone.

**Shala** (lazy `Links`, as it is): heading `tab-shala` + gear · My schedule row (in a shala) · Announcements row (has a teacher) · teachers card · students card with its My students row · invite row · directory-line row (existing rule) · shalas card with "Create a shala".
**Nobody yet** (no teacher, no student, no shala, and neither start tapped): heading, one plain line `shala-empty` (the teacher or the shala sends a link), and two quiet starts with the bot's labels: `shala-start-invite` ("Invite students") opens the full layout with the invite card open; `shala-start-shala` ("Shala and classes") opens it with the create form. No empty cards.

## 5. The day card (`DayLog`)
One builder for today and for any earlier day, as the bot's E0 = T0. Choices are one per row at every width (as the bot's buttons; nothing truncates at 320 px). "Today" and the date in the heading come from the server's `days.today`, never the device.

| State | Lead | Controls |
|---|---|---|
| Unlogged, ordinary day | `today-prompt` | `status-practiced` · `status-rest` · `today-other` |
| Unlogged, auto-rest (moon day, weekly day off) | the existing `today-auto-*` line; no prompt | the three choices, none pressed |
| Unlogged, a pause is running | the existing `today-period` line + "End the pause" | the three choices, none pressed |
| "Other…" open (`aria-expanded`) | group label `today-reasons` | moon · ladies' holiday · sick / injury · travel · no practice, in `domain/journey.OTHER_REASONS` order; 🌸 left out under `hide_ladies` unless it is the logged status. A tap saves and closes |
| Logged: rest or a reason | `today-logged` with the status label; `today-private-note` for 🌸; the pause question when the save offers one | the choices with the logged one pressed ("Other…" for a reason) · `diary-add` · `today-clear` |
| Logged: practiced | `today-logged`; then one line: the stored summary (class type · how far · how long), else `practice-last-time[-dated]` when a previous practice exists | the choices · `practice-same-as-last` (previous practice and no details yet; copies type, online, length, duration, never the start time) · `practice-add-details` (`practice-details` once some exist) · `checkin-edit` (shown per `entry_shown`: the setting is on, or a check-in exists; with one, its one-line summary) · `diary-add` · `today-clear` |
| Failed | `today-load-failed` / `today-save-failed` (existing) | – |

Nothing opens by itself: details and the check-in mount only on their tap (chunk `dayExtras`, prefetched when the card first shows "practiced"). The note entry shows on a logged day or when a note exists; an unlogged day's note stays possible from the day editor. Count celebrations, the "New asana?" question, "Keep the pause" and the day editor's device-only 🌸 switch (`showLadies`) are unchanged.

## 6. The next step: domain, use case, API
**Decision: a shared use case, one new read endpoint.** Client-side derivation would need three to five more requests on Today, cannot see whether an invite link exists (`POST /me/invite` creates it), and would put a role rule in TypeScript that the bot could not reuse.
- **Domain (pure, `domain/journey.py`):** `NextStep` (enum; definition order = offer order): `ADD_CLASS`, `INVITE_SHALA_STUDENTS`, `INVITE_STUDENT`, `REMINDER`, `POSITION`. `JourneyFacts(has_days, reminder_answered, position_set, invite_made_on, owned: tuple[OwnedShala(id, classes, students), ...])`. `next_steps(account, facts, today) -> tuple[Step(kind, shala_id), ...]`:
  - `ADD_CLASS`: an owned shala with no class (the oldest). `INVITE_SHALA_STUDENTS`: an owned shala with a class and no student.
  - `INVITE_STUDENT`: an invite link made at most 30 days before `today`, no students (`account.teaches` false), no owned shala (Q334).
  - `REMINDER`: `has_days` and `practice_on` is NULL (never chosen; "yes" and "no" both answer it). `POSITION`: `has_days` and no position set.
- **Then it disappears: derived, no flag, no migration.** Each step ends in data that already exists. Three steps have no "no" in the data (position, the two invites); see Q333.
- **Use case:** `application/journey.py::GetNextSteps.execute(principal) -> tuple[Step, ...]`. **Port:** `AccountRepository.journey_facts(account_id) -> JourneyFacts`, one statement (EXISTS and scalar subqueries over `day_log`, the reminder setting, the progression position, `teacher_invite`, the shalas this account owns with two counts). Table and column names to check when building.
- **API:** `GET /api/v1/me/next-steps` → `200 NextStepsOut { steps: NextStepOut[] }`, `NextStepOut { kind: "add_class" | "invite_shala_students" | "invite_student" | "reminder" | "position", shala_id: uuid | null }`; `401`, `503`. Auth: initData (`CurrentPrincipal`). Policy: the caller's own facts only; shala facts only for shalas the caller owns (so every offered action is one the owner may take); no new policy function. New router `api/v1/journey.py`.
- **OpenAPI:** `uv run tristhana-openapi` → `miniapp/src/api/openapi.json` → `npm run gen:api`; `useNextSteps()` in `api/client.ts` (key `["next-steps"]`, stale after 60 s; invalidated by the notification-settings patch, a progression event, class and shala creation and deletion, and a day save). An API older than the bundle answers 404: no card.
- **The card:** one sentence, one button, a quiet `next-not-now` (Q333: kept in `localStorage` per step; blocked storage counts as "not now", never a nag). The app shows the first step not skipped here. Reminder → `settings{focus: "remind"}` (the person sees the time they set); position → `asanas`; invite → Shala tab, `start: invite`; class and shala invite → Shala tab, `start: shala:<id>`.
- **Bot:** unchanged in this stage; it can call `GetNextSteps` later.

## 7. Copy keys (`locales/{en,ru}/app.ftl`; the ux-writer writes the text)
- **New:** `tab-today`, `tab-practice`, `tab-shala` ("Shala" / «Шала», fixed by the owner; each one line, emoji + word as the bot's Menu rows; `tab-shala` is also the Shala root's heading), `tabs-label` (the bar's accessible name), `today-prompt` (the bot's `start-prompt` sentence), `today-other` (= bot: "Other…" / «Другое…»), `today-reasons` (the bot's `today-reasons-title` sentence), `today-logged` (= bot, `$label`), `practice-add-details`, `practice-details` (= bot), `practice-more`, `checkin-summary-energy`, `checkin-summary-effort` (= bot), `today-class` (`$time`, `$type`, `$shala`), `today-class-there` (`$time`, `$zone`: the class's own time when its zone is not mine), `today-class-more` (`$n`), `next-reminder`, `next-reminder-do`, `next-position`, `next-position-do`, `next-invite`, `next-invite-do`, `next-class`, `next-class-do`, `next-shala-invite`, `next-shala-invite-do`, `next-not-now`, `shala-empty` (the bot's `links-empty` sense), `shala-start-invite`, `shala-start-shala` (= the bot's `welcome-path-invite` / `-shala`), `chunk-failed`, `chunk-retry`.
- **Changed text, same key:** `today-title` (gains `$date`), `checkin-edit` (the bot's "How do you feel?"), `settings-checkin` and `settings-checkin-hint` (Q313: shows or hides that entry), `links-empty` (as the bot's: the teacher or shala sends a link), `settings-open` (now the gear's accessible name).
- **Removed:** `home-first-hint`, `stats-open`, `links-title`; with Q331 the fifteen `tour-*` keys.
- **Unchanged on purpose:** `status-*`, `practice-same-as-last`, `practice-last-time*`, `diary-add`, `today-clear`, `today-auto-*`, `today-period`, `today-private-note`, `moon-*`, `progression-open`, `my-schedule-open`, `link-students-open`.

## 8. First-chunk budget (147.6 of 150 KB gzip today)
Rule: **stage 2 does not raise the first chunk.** The PR description records `npm run check:bundle` before and after; build in this order, measuring after the first step.
1. **Leaves the first chunk:** `PracticeDetails` with its custom-length picker, start time and "New asana?" question, and the `CheckIn` editor (chunk `dayExtras`); the moon card and `MoonSource` (`moon/MoonScreen`); `TourOffer`, `useTour`, `onboard.ts` and the tour's CSS; the Home rows; about twenty Fluent messages in each language.
2. **Enters it:** `nav.ts`, `Shell`, `TabBar`, `ChunkBoundary`, `DayChoice`, `NextStep`, `TodayRows`, `timeLabel.ts`, `useChunk`, about thirty short messages per language, about thirty CSS rules. No icon set: tabs and gear are emoji and text, as everywhere else. No new dependency.
3. Practice, Shala and every pushed screen stay lazy chunks; `TodayRows` may import `scheduleText.ts` only (never `MySchedule` or `ClassForm`, which would pull their chunks in).
The sizes above are not measured. **If the check still fails:** load only the active language's `app.ftl` (both are in the first chunk today, about 900 lines each); that is a separate small PR with its own note, not part of this one.

## 9. Cross-cutting checks
- **Time zones ✔.** `timeLabel.ts` mirrors `domain/time_label.py`: `offsetShown(zone, viewer)` (IANA names compared; unknown viewer shows the offset; `UTC` never gets one) and `offsetText(zone, day, at)`. It must pass the backend's table, which today's `zoneLabel` does not in two cases: London in winter is `UTC+0` (now `UTC`), and the offset must be the one at the wall-clock time on a change night (now the time is read as UTC). Stage 2 passes the viewer's zone on the Today tab only: the class row and the start-time label in details. Zone descriptions keep the offset (ADR-0044); other screens change with their stages. Without a zone the reminder step opens Settings, which already says a zone is needed.
- **Privacy ✔.** The endpoint returns the caller's own facts. "Not now" never leaves the device. 🌸 sits behind "Other…", follows `hide_ladies`, keeps `today-private-note`. Tab and launch navigation store nothing; `shala` in a launch link is still checked as a UUID.
- **i18n ✔.** Every string in `app.ftl`, en + ru, key and variable parity; no text in code. The three Russian tab labels fit one line at 320 px.
- **Responsiveness ✔.** Today's requests: `me`, `days`, `moon-days`, `shalas`, `health` (as now), `next-steps` (new, one statement) in place of `links`; `schedule` only for shala members. A tab switch with a warm cache makes no request. Saves stay optimistic. Choices answer with a haptic before the network call.
- **Accessibility and touch ✔.** The bar is `<nav aria-label>` with three buttons, `aria-current="page"` on the active one (not a `tablist`: no arrow-key contract). Each tab is a third of the width and at least 48 px high; the gear is 44×44 with an accessible name; choices and entries are at least 44 px high. The active tab differs by weight and a top line as well as colour. After a switch, focus moves to the new root's heading and the page scrolls to the top. Choices use `aria-pressed`, "Other…" and the entries `aria-expanded`.
- **Safe area and keyboard ✔.** The bar is `position: fixed`, its bottom raised by the part of the page Telegram has not revealed (`100vh − --tg-viewport-stable-height`, as the tour sheet does today) and padded by `max(env(safe-area-inset-bottom), var(--tg-viewport-safe-area-inset-bottom, 0px))` (the SDK already binds the second). Roots get the same bottom padding. While a text field has focus the bar is hidden by CSS alone (`:root:has(textarea:focus, input:not([type="checkbox"], [type="radio"]):focus)`), so iOS (keyboard over the page) and Android (page resized) behave alike and the bar never rides on the keyboard. To check by hand on an iPhone with a home indicator and on Android with gesture navigation.
- **Haptics, theme ✔.** `selection` on a tab or gear tap and on opening an entry; `impact("light")` on a choice (existing); `notify("error")` on a failed save. Bar colour `--tg-theme-bottom-bar-bg-color` with the surface colour as fallback; `miniApp.setBottomBarColor` where available so the strip under the bar matches; no new colours, dark theme through the existing tokens.
- **Layering ✔.** `journey` stays pure; the bot and the API can share `GetNextSteps`; API types are generated.

## 10. Tests to write first
- **Backend.** Domain `test_journey.py`: `next_steps` for nobody, a student before and after the first day, reminder answered yes / no, position set, a link with no students, an owner with no class / with a class and no student / complete, owner and teacher at once (order). Use case and DB: `journey_facts` is one statement and counts only owned shalas. API contract: `GET /me/next-steps` shape, 401, the OpenAPI snapshot. **Bot handlers: none change; no bot test.**
- **`shell/nav.test.ts`:** `launchNav` for every row of §2, `"/?open="`, `"new-shala%20"`, a bad `shala`; push, pop, a tab switch clears the stack, Settings is never pushed twice.
- **`App.test.tsx` (rewritten):** three tabs with `aria-current`; a tap switches and focuses the heading; gear and ⋯ open Settings and Back returns to the same tab; no Back on a root; the bar is absent inside a pushed screen and while a note has unsaved text; each launch link lands as in §2; My asanas from Practice, My schedule and My students from Shala; Settings has no "Teachers and students" row; a failing chunk shows the retry line and keeps the bar.
- **`DayLog` / `TodayCard`:** exactly three choices; reasons in order, four under `hide_ladies`, 🌸 kept when logged; a reason saves and closes; each lead line of §5; after "Practiced" nothing is expanded and the control count is small; "same as last" only with history and no details, and its PUT has no start time; "Add details" loads the chunk, a failed load keeps the card; start time behind `practice-more`; the check-in entry follows `offer_check_in` and an existing check-in; the note entry rule.
- **`NextStep.test.tsx`:** the first step only; nothing for `[]`, while loading and on 404; each action's navigation; "Not now" hides that step on this device and shows the next; blocked storage shows nothing. **`TodayRows.test.tsx`:** own zone without an offset, another zone with one, no row without a class. **`timeLabel.test.ts`:** the cases of `backend/tests/domain/test_time_label.py`, one for one. **`telegram/index.test.tsx`:** `useBackShown` with and without Telegram's button.
- **Existing tests that pin what changes:** `App.test.tsx` (whole file); `TodayCard.test.tsx` (the seven chips); `tour/Tour.test.tsx`, `tour/TourOffer.test.tsx` (deleted with Q331); `MoonCard.test.tsx` (moves with the card); `CheckIn.test.tsx` (the three "is open…" cases and the collapsed ones); `PracticeDetails.test.tsx` ("same as last", start time); `stats/DayEditor.test.tsx` and `RestPeriods.test.tsx` (status chips); `settings/Settings.test.tsx` ("re-opens the quick tour…", the check-in switch text); `settings/TeachersAndStudents.test.tsx` (heading, Back, empty state); `stats/Stats.test.tsx` (Back); `i18n/bundles.test.ts` (parity). `Home.test.tsx`, `DiaryNote.test.tsx` and the launch cases' intent (`new-shala` shows the focused form, an unknown value opens Today) must survive.

## 11. Guides and screenshots that go stale
The site build fails on a removed key (ADR-0043), so this stage touches `site/` as stage 1 did (Q316: `/guide-update UI-06`).
- **Build-breaking quotes:** `:ftl[tour-open]` (`start/bot-and-app`), `:ftl[links-title]` (`teachers/invite-students`, `teachers/what-you-see`, `teachers/directory-line`, `staff/create-shala`), `:ftl[stats-open]` (`students/my-practice`, `students/log-practice`); each with its `ru/` twin.
- **Pages whose app part changes** (candidates, each with its `ru/` twin; `npm run check:guide -- --stale` gives the exact list): `start/first-steps`, `start/bot-and-app`, `students/log-practice`, `students/check-in-and-diary`, `students/rest-and-moon-days`, `students/reminders`, `students/my-practice`, `students/my-asanas`, `students/settings` ("at the bottom of the first screen"), `students/my-teacher`, `students/my-shala`, `teachers/invite-students`, `teachers/what-you-see`, `teachers/directory-line`, `teachers/announcements`, `staff/create-shala`, `staff/classes`, `staff/announcements`, `reference/faq`, `reference/whats-new`.
- **Screenshots (`site/shots/manifest.yaml`, en + ru):** every `app-*` shot changes (the bar, or the screen itself), and every `click` path changes: `app-my-practice` `[tab-practice]`, `app-badges` and `app-trends` `[tab-practice, …]`, `app-my-asanas` `[tab-practice, progression-open]`, `app-schedule` `[tab-shala, my-schedule-open]`, `app-settings` `[settings-open]` (the gear has no visible text, so `shoot.mjs` must also find a control by its accessible name), `app-student-card` and `app-announce` `[tab-shala, link-students-open, …]`, `app-shala`, `app-class-form`, `app-shala-announce` `[tab-shala, =shala, …]`. `app-home` is the new Today. New: `app-today-practiced`, `app-shala-tab`.
- **Notes on acceptance (not done by this spec):** UI-03 and UI-06 rows in `02 Requirements.md`; UI-02 and `UI-02-quick-tour.md` per Q331; ADR-0047 in `04 Architecture.md`; `09 Roadmap.md`.

## 12. Questions for the owner (the bold recommendations are what this spec builds)
- **Q331. The coach-mark tour.** Q301 said it stays; its seven steps point at Home rows that no longer exist. **Recommended: retire it with the bot's tour**; the tabs, the next-step card and "Guide" in Settings do its job, and it frees room in the first chunk. Alternative: rewrite it as four steps (three tabs and the gear), which keeps about 1 KB and fifteen messages.
- **Q332. The tab bar inside a screen.** **Recommended: hidden whenever Telegram's Back is shown** (roots have tabs, everything deeper has Back). Alternative: always visible, which collides with keyboards, Telegram's main button and unsaved notes.
- **Q333. A step the person does not want.** The reminder step ends on "yes" or "no"; "where the practice ends" and the two invite steps have no "no" in the data. **Recommended: every step has a quiet "Not now", remembered on that device only** (as the tour offer was): no flag, no migration. Alternatives: no way out (the card stays until done); a stored flag per step (a migration, and the bot could then honour it).
- **Q334. Who sees "Invite your first student".** Roles are not stored, so the sign is an invite link with nobody on it yet. That includes anyone who once opened the invite screen out of curiosity. **Recommended: only while the link is at most 30 days old** (`teacher_invite.created_at`), and never for a shala owner (the shala steps cover it). Alternative: no age limit, relying on "Not now".
- **Q335. The day editor on the Practice tab.** **Recommended: it gets the same three-choice card in this stage** (one builder, as in the bot; otherwise details and the check-in need two modes until stage 3). Alternative: it keeps the seven chips until stage 3.
