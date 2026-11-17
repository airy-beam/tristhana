# UI-06 stage 4, part A: shala setup and classes (two-field create, setup list, short class form, class editing, form controls)

- Status: **accepted** (owner, 2026-11-16: the five points in §1, and Q337–Q340 in §13 all as recommended) · Size **L**, one pull request (part A of stage 4)
- Parent: `docs/specs/UI-06-simple-journey.md` (§1, §10). Sits in the shell of `UI-06-stage-2-app-shell.md` (ADR-0047) but does not need it (§11). Requirements: **UI-06**; changes SC-01 (create), SC-02 (class form, editing: closes its §11 "deferred"), touches SC-05 (marks follow a split), NT-03 (Q339), ID-03 (Q338).
- Related: ADR-0033, 0034, 0039, 0044, 0047. New, proposed: **ADR-0048** (a class edit applies from a date; the past is not rewritten).

## 1. Scope
**In (approved, not reopened):** (1) create a shala with name and city; (2) a setup list on the owner's shala screen; (3) a short class form with "More options" and length chips; (4) class editing through the existing `PATCH`; (5) one set of styled form controls for the forms on the shala screen.
**Also in, found while reading:** three defects in the `PATCH … from` path (§3), the Teacher select rule (§5), the edit entry and where Delete lives (§4).
**Out:** the Shala tab's own layout and its empty states (stage 4 part B, after stage 2); a list of class series; ending a class by a button (the form's "Last date" does it); cancellation notices from the bot; an "attendees only" audience; any bot change; any migration.

## 2. What `PATCH /shalas/{id}/classes/{class_id}` does today (read 2026-11-16)
- **Route** (`api/v1/classes.py::patch_class`): `ClassPatchIn` is every `ClassIn` field as optional (`type, title, online, city, teacher_id, start, minutes, weekdays, every, starts_on, ends_on`) plus `from`. It reads the shala's class list (`ListClasses`, policy `can_manage_schedule`), answers 404 when the id is not in it, lays the sent fields over the stored row (an explicit `null` clears `title`, `city`, `teacher_id`, `ends_on`; `null` for a required field is 422) and calls `UpdateClass`. Three statements. No client calls it.
- **Use case** (`application/classes.py::UpdateClass`): `from` must be in [caller's yesterday, today + 365]; `ends_on < from` is 422; then the usual checks.
- **Without `from`** (`SqlScheduleRepository.update`): one `UPDATE` of every column in place (same id, `starts_on` included), and it deletes every override, past or future, on a date the new rule no longer produces.
- **With `from`** (`_split`): only for a weekly series with `starts_on < from`. The old row gets `ends_on = min(ends_on, from − 1)`; a new row (new id) takes the merged values with `starts_on = from`; overrides on or after `from` move to the new id when the new rule produces their date, the rest are deleted. With `from ≤ starts_on`, or a one-off, it falls back to the in-place update.

| Thing | In place ("all dates") | With `from` (split) |
|---|---|---|
| Past occurrences | recomputed from the new rule: the last 7 days of the schedule and the calendar's back window change | unchanged before `from` |
| Cancelled / held / moved / substitute dates | kept where the date survives; deleted, past ones too, where it does not | before `from`: kept; from `from`: carried or deleted |
| Swaps and closures | shala-level, by date: untouched. A swap is validated only when made, so after an edit its target day may hold a class of the moving type (both show; the read-time net re-checks only closure and moon) | same |
| Attendance (ADR-0039) | rows stay on `(class_id, key)`; the snapshot keeps the old time and type; rows on dates the rule dropped are stranded (history by `(shala_id, on_date)` still reads them) | **not carried**: rows with `key ≥ from` stay on the ended id (defect D1) |
| Calendar feed | expanded instances, UID = class id + rule date, no RRULE (`to_rrule` feeds only `ClassOut.rrule`): events change in place, past ones too | dates from `from` get new UIDs: calendars replace them at the next poll |
| Shala schedule, My schedule | read-time (ADR-0034): the next read | the next read; old bot buttons for later dates re-render with `class-gone` |

**Does "from a date you choose" need a new field? No.** The route has `from`, and the model already ends a series on a date (`ends_on`) and starts a successor (a new row). The successor has a new id, so occurrence keys change from `from` on, and nothing links the two rows (not needed: nobody lists series). Three defects stand in the way:
- **D1.** Marks made on a date ≥ `from` (today's class, edited after it ran) drop off the roster and My schedule; a second claim makes a second row.
- **D2.** With `every > 1` the successor counts weeks from `from`'s ISO week: a split from an off week flips the rhythm.
- **D3.** A series that already ended before `from` (another staff member split it a minute ago) still gets a successor when the client sends `ends_on`, so the class doubles; otherwise the answer is a misleading 422.

## 3. Decision: an edit applies from a date (ADR-0048)
- **The app never rewrites the past.** Saving a change to a weekly class that has started always sends `from`; the form shows one line, "Changes apply from {date}", default the date that was tapped (its rule date), earliest the shala's today. No "all dates" choice (Q337). A class that has not started, and a one-off, change whole (the server already does this). The API keeps `from` optional.
- **Fix D1:** the split statement also moves `class_attendance` rows of the old id with `occurrence_key ≥ from` to the new id when the new rule produces that date (one more CTE, same predicate as overrides). Rows on dates the new rule drops stay on the ended series; their snapshot keeps them truthful.
- **Fix D2:** `domain/classes.py::split_start(old, every, from_date) -> date`: when `every` is unchanged and > 1, the first day ≥ `from` that lies in one of the old rule's weeks; else `from`. The old rule has no dates in the skipped days, so nothing is lost.
- **Fix D3:** a series whose `ends_on < from` is gone for this edit: `NotFound` (404), checked in the use case and again in the statement (`ended` requires `ends_on IS NULL OR ends_on ≥ from`; no fall-through to the in-place update).
- **Alternative (not built):** "Applies to: all dates · from {date}" as SC-02 drew it. "All dates" changes last week's schedule and calendar history, deletes past cancellations on dropped days and strands marks.

## 4. Flows (Mini App; the bot is unchanged)
**Create a shala.** `shala-name-label`, `shala-city-label` (preselected: home city), `shala-create-submit`. Nothing else on the form. Sent: `{name, city, online: false, roles: ["teacher"]}`; the API needs no change (`online` and `roles` already default; moon policy `closed`, moon city = the city, day off unset come from the table defaults). Online-only stays in `shala-edit`; the owner's own roles: Q338. On success the new shala's screen opens, with the setup list.

**Setup list** (owner only, top of the shala screen, while `setup` is not empty): three rows in fixed order. Done rows are plain text with ✓; the first row still due is the one highlighted button; later rows are quiet. `setup-class` opens the class form; `setup-students` opens the student link card; `setup-staff` opens the staff-invite picker and carries a quiet `setup-staff-skip` (Q340). The list leaves when nothing is due.

**Add a class.** `schedule-add-class` moves to the top of the schedule card. The form is a full-screen layer with its own Back (so the tab bar hides, ADR-0047).

| Visible | Under `class-form-more` (collapsed; the row shows a one-line summary of the values below) |
|---|---|
| Type (7 chips) · Start (time, labelled per ADR-0044) · Repeats on (weekday chips; `class-form-once` swaps them for one date field) · Save | Until (Mysore) or Length chips 60 · 75 · 90 · 120 · `class-form-length-other` (then an "Ends at" time) · Title · Teacher · Every 1–4 weeks · First date (default the shala's today) · Last date · Online, and then "Times in" |

Defaults: Mysore 06:00–09:30 on every day but the shala's day off (as today: open, Save); other types start with no day and keep `class-led-hint`; lengths Led 90, 1:1 60, Conference 60, Pranayama 60, Chanting 60, Workshop 120 (ashtanga-expert to confirm the lengths and whether 30 and 45 belong among the chips). Changing Start keeps the length. Weekly with no day chosen does not save: `class-form-days-needed` (no hidden "none means once"). An error inside "More options" opens it and focuses the field.

**Occurrence sheet (tap a class on its date).** Two groups, each with a heading. `occurrence-this-date` (`$day`): attendance, teacher on this date, cancel, hold anyway, restore, as today. `occurrence-whole-class`: one row, `class-edit`. Delete leaves the sheet: it is the last, quiet row of the edit form (same key, same confirm), so nothing on the "this date" side touches other dates.

**Edit a class.** `class-edit` loads the series (`GET …/classes`, picked by id) and opens the same form filled in. For a started weekly class the form shows `class-form-applies` with the date and `class-form-applies-hint` in place of "First date"; otherwise "First date" (or the one date) is editable. The request carries only the fields the person changed, plus `from`.

**Stale state.** The class was removed, or split by someone else, while the form was open: 404 → `class-form-gone`, the form closes, the schedule refetches. Another person changed other fields: they stay, because only changed fields are sent; the same field: the last save wins. A teacher removed from the staff meanwhile: 422 → `class-form-failed`, and the refetched shala drops them from the select. Opening an edit for an id no longer in the list shows `class-form-gone` at once.

**"Tell students" (Q339).** After a successful `occurrence-cancel` on a class that is not 1:1, for someone with `shala.me.announce`, the sheet shows `occurrence-tell`. It opens the existing compose screen with the text filled from `ann-cancel-draft`; the person edits and sends through the usual confirm. Nothing is sent by the cancel itself.

## 5. Rules
- **Who may edit:** unchanged, Q118: owner, Manager, Teacher, Front desk (`can_manage_schedule`, enforced in the SQL guard); assistants and students read. No per-class ownership. The buttons follow the server's `me.schedule`.
- **Teacher select:** every staff member, teachers and assistants first, then the rest (the owner's choice for the substitute picker, SC-02 §12; the FK only needs a staff row). Default: me when my roles include Teacher, else "—". This fixes the owner who is missing today.
- **Setup steps** (pure, `domain/journey.py`): `SetupStep` = `ADD_CLASS`, `INVITE_STUDENTS`, `INVITE_STAFF`; `setup_steps(classes, students, staff) -> tuple[SetupStep, ...]`: due while `classes == 0`, `students == 0`, `staff == 1`. `next_steps` is rewritten on it (a shala's first due step gives `add_class` or `invite_shala_students`), so the Today card and the list cannot disagree; its results do not change.
- **Length:** stored as minutes, 15–480, ending by 24:00 (unchanged).

## 6. Use cases, ports, API
- **`UpdateClass.execute(principal, shala, class_id, patch: ClassPatch, from_date)`** now owns the read and the merge (they sit in the route today, so no other adapter could reuse them): `classes_of` → `NotFound` → merge → D3 check → `split_start` → write. Still three statements. `ClassPatch` uses the `KEEP` sentinel as `ShalaPatch` does. The route only maps the body.
- **`ScheduleRepository.update`**: signature unchanged; `_split` gains the D1 CTE and the D3 guard.
- **`ShalaCard.classes_total`**: one scalar subquery in the card statement (index `(shala_id, starts_on)`), the same count as `journey_facts`.
- **API changes (then `tristhana-openapi` and `gen:api`):**

| Method, path | Change | Policy |
|---|---|---|
| `GET /api/v1/shalas/{id}`, and every answer that is a `ShalaOut` | `+ setup: ("add_class" \| "invite_students" \| "invite_staff")[] \| null`; null unless the caller owns the shala | member; the owner's own counts only |
| `PATCH …/classes/{class_id}` | schema unchanged; 404 also when the series ended before `from`; marks follow a split | `can_manage_schedule` |
| `POST /api/v1/shalas` | none | – |
| `PUT …/staff/{account_id}` (Q338) | schema unchanged; the owner may set their own Teacher, Assistant and Front desk | `can_set_roles`, one new branch |

- **Client (`api/client.ts`):** `useClasses(shala, enabled)`, `useUpdateClass(shala)`; every schedule write also invalidates the shala card and `["next-steps"]`.

## 7. Form controls and files
- **`miniapp/src/ui/`** (new): `controls.tsx` (`Field`: label above, hint and error wired with `aria-describedby` / `aria-invalid`; `TextInput`, `Select`, `TimeInput`, `DateInput`, `Check`: native elements, styled, so the phone's own pickers and screen readers keep working), `Chips.tsx` (one or many; `role="group"`, `aria-pressed`), `More.tsx` (button with `aria-expanded` / `aria-controls` and the summary line), `form.css`.
- **Look:** theme tokens only (`--c-bg`, `--c-surface`, `--c-text`, `--c-hint`, `--c-accent`); `accent-color` for checks; a visible focus ring; controls at least 44 px high, text 16 px (no zoom on iOS); 8 px between label and field, 16 px between fields.
- **CSS budget:** `form.css` is imported only by `ui/`, and `ui/` only by lazy screens, so Vite emits it with those chunks: **initial CSS stays at 3.0 KB**; `form.css` ≤ 1.5 KB gzip. Nothing in the first chunk may import `ui/` in this stage. The PR records `check:bundle` before and after.
- **320 px:** chips wrap; weekday chips show the short name (`Intl`, as `dayName`) with the full name as the accessible name; time and date fields are full width, one per row; the longest Russian label wraps, never truncates.
- **Screens:** add `shalas/CreateShala.tsx` (moved out of `Links.tsx`, which stage 2 also edits: the move is the only change there), `shalas/SetupList.tsx`, `shalas/OccurrenceSheet.tsx` (moved out of `ShalaSchedule.tsx`), `shalas/classForm.ts` (pure: defaults per type, changed fields, the default `from`, teacher choices). Change `ClassForm.tsx` (create and edit), `ShalaSchedule.tsx`, `ShalaScreen.tsx` (the list; Edit, closures, swap and the role editor on the new controls), `announcements/Announcements.tsx` (compose takes `draft`, Q339).

## 8. Copy keys (`locales/{en,ru}/app.ftl`; the ux-writer writes the text)
- **New:** `class-form-more`; `class-form-sum-until` (`$time`), `class-form-sum-length` (`$minutes`), `class-form-sum-from` (`$date`): parts of the summary line; `class-form-length-chip` (`$minutes`: "90 min"); `class-form-length-other`; `class-form-ends` ("Ends at"); `class-form-once` / `class-form-weekly` (switch between one date and weekdays); `class-form-date` (the one date); `class-form-days-needed`; `class-form-applies-hint` (earlier dates stay as they were); `class-form-gone`; `class-edit` ("Change the class…"); `class-form-edit-title`, `class-form-new-title` (the layer's headings); `occurrence-this-date` (`$day`), `occurrence-whole-class`; `setup-title`, `setup-class`, `setup-students`, `setup-staff`, `setup-staff-skip`, `setup-done-mark` (accessible "done"); with Q339 `occurrence-tell`, `ann-cancel-draft` (`$class`, `$day`, `$time`: the full zone label); with Q338 `shala-my-roles-edit`.
- **Changed text, same key:** `class-form-days` ("Repeats on"), `class-form-applies` ("Changes apply from"; unused until now), `class-form-from`, `class-form-title`, `occurrence-note` (with Q339), `shala-my-roles` (with Q338).
- **Removed:** `class-form-length`. **Must survive** (the guides quote them): `schedule-add-class`, `class-form-type`, `class-form-save`, `occurrence-delete`, `occurrence-cancel`, `occurrence-restore`, `occurrence-hold`, `occurrence-teacher`, `shala-create`, `shala-create-submit`, `shala-name-label`, `shala-city-label`, `shala-online-only`, `shala-my-roles`, `shala-edit`.

## 9. Cross-cutting checks
- **Migration: none.** `setup` and `classes_total` are derived; a split uses existing columns.
- **Time zones ✔.** Start, Until and Ends are wall clock in the class zone, labelled per ADR-0044 (offset only outside my zone). `from` and the dates are rule dates in the class zone; the earliest is the shala's today (`todayIn(shala.zone)`), while the server still accepts the caller's yesterday. For an online class timed in another city the "apply from" date is named with that city. A split keeps wall clock on both sides of a daylight-saving change. The cancel draft carries the full label (`07:00 Almaty (UTC+5)`): its readers are in many zones and the text is frozen.
- **Privacy ✔.** `setup` goes to the owner and is built from counts the owner already sees. The cancel draft names the class, day and time, never a person; it is not offered for 1:1 classes (Q121). Titles stay plain text. No log data is read; attendance rows move only between two ids of the same shala.
- **i18n ✔.** Every string in `app.ftl`, en + ru, key and variable parity; minutes as an abbreviation (no Russian plural needed); weekday names from `Intl`.
- **Responsiveness ✔.** The create forms open with no request (cities load when "Online" is opened); the edit form adds one read. `PATCH` stays at three statements, the card at its current count. Writes wait for the server, buttons are disabled meanwhile, haptics as today.
- **Layering ✔.** `split_start` and `setup_steps` are pure; the merge moves from the route into the use case; no aiogram; `application.classes` still imports no log port.

## 10. Tests to write first
- **Domain.** `split_start`: weekly; every 2 from an on week and from an off week; `every` changed; a date before the start. `setup_steps`: each of the eight count combinations; `next_steps` cases unchanged.
- **Use case (fakes).** `UpdateClass`: only sent fields change; `null` clears the four nullable ones; a series ended before `from` → `NotFound`; `from ≤ starts_on` and a one-off change whole; the snapped date is what is written.
- **DB (Postgres).** Split carries marks with `key ≥ from` that the new rule produces and leaves the others; earlier marks stay; the unique key holds; a second split of an already ended series writes nothing; statement count is one.
- **API.** `PATCH` with `from`: new id, earlier dates unchanged in `GET schedule`, today's roster still shows its marks; 404 for a gone or ended class; Assistant 403; `ShalaOut.setup` for the owner at each stage and null for a Manager and a student; the OpenAPI snapshot. Q338: the owner sets own roles, not Manager; a Manager still cannot touch the owner.
- **Bot.** One test: an old `c1:o` button for a date after a split re-renders with `class-gone`. No handler changes.
- **Vitest (also `TZ=UTC`).** `ui/`: label and error wiring, `aria-expanded`, chips pressed state. `ClassForm`: the three visible fields; Mysore saves in two taps with the same body as today; length chips and "Other"; start change keeps the length; weekly with no day refuses without a request; one-date mode; the summary line; an error in "More options" opens it; edit sends only changed fields with `from` = the tapped date; a not-started class sends `starts_on` and no `from`; 404 shows `class-form-gone`. Sheet: two groups, `class-edit`, no Delete; Delete in the form after the confirm; `occurrence-tell` only after a cancel, with the right, not for 1:1. Teacher select lists an owner without roles. `CreateShala`: two fields, body with `roles: ["teacher"]`. `SetupList`: one highlighted step per state, skip remembered, blocked storage counts as skipped, absent for a Manager.
- **Existing tests that pin what changes:** `Schedule.test.tsx` ("the class form", all six; the sheet's cancel and substitute cases stay green), `Shalas.test.tsx` ("the create form": the sent body; "lets the owner edit a staff member's roles"), `Announcements.test.tsx` (compose props), `i18n/bundles.test.ts`, `tests/api/test_classes_api.py` (the `PATCH` cases near line 422), `tests/application/test_classes.py` (the two `UpdateClass` cases: new signature), `tests/domain/test_journey.py` (must stay green untouched).

## 11. Order of work, and what waits for the tab shell
- **Before the shell (all of this spec):** backend (§3, §6); `ui/`; the class form, the sheet, editing; two-field create; the setup list; "Tell students". These are lazy chunks opened from the shala screen, which exists today under Settings → Teachers and students, and `?open=new-shala` already reaches the create form.
- **Waits for the Shala tab (part B):** where the list of shalas and the create button sit on the tab root and its empty state; the Today card's `start: shala:<id>` landing; `launchNav` targets; the `[tab-shala, …]` click paths.

## 12. Guides and screenshots
- **Pages (each with its `ru/` twin):** `staff/create-shala` (steps 2–3: two fields; roles and online afterwards; the setup list), `staff/classes` ("Add a class": the short form; "Change or delete a class": `class-edit`, "from the date you tapped", Delete inside the form, no "all dates"; "Good to know" with Q339), `staff/closures-and-swaps` (cancel: "Tell students"; the sheet's two groups), `staff/announcements` (Q339), `reference/whats-new`. `/guide-update UI-06` after the build.
- **Screenshots (en + ru):** `app-class-form` (new form), `app-shala` (button moved; the demo shala is set up, so no list). New: `app-shala-new` (`?open=new-shala`), `app-shala-setup` (needs a demo owner with a fresh shala), `app-class-edit` (`shoot.mjs` must tap a schedule row, then `class-edit`).
- **Notes on acceptance (not done by this spec):** SC-01, SC-02 and UI-06 rows in `02 Requirements.md`; Q337–Q340 in `03 Open Questions & Decisions.md`; "Amended by ADR-0048" lines in ADR-0034 and ADR-0039; a note under SC-02 §11 that editing is built; `09 Roadmap.md`.

## 13. Questions for the owner (the bold recommendations are what this spec builds)
- **Q337. "All dates" when changing a class.** The guide promises "for all dates, or from a date you choose". **Recommended: no "all dates" choice. A change to a class that has started applies from a date (the one you tapped, or one you pick); earlier dates stay as they were. A class that has not started simply changes.** Alternative: offer both; "all dates" also changes last week's schedule and people's calendars, and can leave attendance marks on days the class no longer has.
- **Q338. The owner's own roles after two-field creation.** Teacher is set without asking, and today nobody, the owner included, can change an owner's roles later. **Recommended: keep Teacher as the silent default and let the owner change their own roles from their row in "Teachers and staff"** (one policy branch). Alternative: a "More options" fold on the create form with the roles, and no change afterwards.
- **Q339. "Tell students" after cancelling one date.** Q122 kept cancellations silent. **Recommended: in this stage, in the app only: after the cancel the sheet offers "Tell students…", which opens the announcement with the text filled in; the person edits and sends it, it counts toward the three a day, and it is not offered for 1:1.** Alternative: leave it out; the note keeps pointing to announcements.
- **Q340. The optional third step.** A person who teaches alone would keep "Invite teachers" forever. **Recommended: after a class and a first student, the third step is highlighted with a quiet "I teach alone", remembered on this device (as "Not now" in stage 2); the list leaves when someone joins the team or on that tap.** Alternative: the list leaves as soon as a class and a student exist, with "Invite teachers" only as its quiet third row until then.

## 14. Review fixes (2026-11-17, before merge)
What the code review and the copy review changed in this spec's design. Where a line above says otherwise, this section is the current one.
- **The edit form trusts only a fresh list.** "Gone" and the form's base come from a class list fetched after the form opened, read once (`ClassForm`): a cached list may lack a class added since, and the list refetched after one's own delete is not news.
- **A class with a last date.** The form says how far a change reaches (`class-form-applies-last`), and Delete names the dates it removes (`class-delete-ask-range`). No link to a later series is shown: none is stored (ADR-0048).
- **One sentence instead of the date field** (`class-form-applies-on` + `class-form-applies-hint`), with `class-form-applies-other` ("Another date") bringing the field. The default date is the tapped one, or **the class's next date when that date's class has already begun** (`classForm.defaultFrom`), so a class that ran keeps its place and its marks.
- **Form:** two chips `class-form-weekly` / `class-form-once` under `class-form-when` (no link that flips); "Other" takes minutes (`class-form-minutes`, `NumberInput`; `class-form-ends` is gone); a last date before the first date, or before the apply date, stops at the field (`class-form-end-early`, `class-form-end-before-applies`); a title example; Back asks before dropping typed input (`class-form-discard-*`); one request per press (a ref); the focus returns to the row that opened the form.
- **Sheet:** `occurrence-tell` stays on a cancelled date and is not offered when the shala has no other member; the announcement opens as a layer over the card (week, open date and scroll kept). **`class-end` ("End this class from this date")** in "The whole class", on a date that has not begun: it reads the class as it is now, then sets its last date to the day before through `PATCH` (`ends_on` only). A date outside the series answers 404 to cancel, hold and restore; the sheet then closes and the week shows `class-form-gone`.
- **Backend.** `set_override` / `clear_override` require the date within the series' span (`NotFound` from the use cases; the bot's extra read is gone). `ScheduleRepository.update` takes `read_ends_on`: a split requires the last date that was read. A series with no date before `from` changes whole (no predecessor without dates). A claim's guard knows the span (`NotAttendable` when the class changed between read and write). `RemoveMyAttendance` returns whether a mark was removed; the bot re-renders its list when none was. "Regulars" on the roster match the shala and the class type, not the series id.
- **Setup list:** `setup-staff` is two or three words with `setup-staff-note` ("Optional") as a quiet second line; from that step the role picker opens with Teacher marked and focused (nothing is made until a role is tapped).
- **Copy:** `occurrence-cancel` reads "Cancel this date" in English; the Russian sheet says «Преподаватель на эту дату» / «Обычный преподаватель»; the cancellation draft ends "See you next time 🙏".
