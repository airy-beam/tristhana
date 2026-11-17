# UI-06 stage 4, part B: the Shala tab (one list for every kind of person, asking a teacher from the app)

- Status: **accepted** (owner, 2026-11-18: QA–QF in §14 all as recommended, "All yes"; in the notes QA = Q353, QB = Q354, QC = Q355, QD = Q356, QE = Q357, QF = Q358; the Today "students waiting" card left out is Q359) · Size **L**, one pull request, branch `ui-06/stage-4b-shala-tab` from `main` at `05e28d1`
- Parent: `docs/specs/UI-06-simple-journey.md` (§1, §10 "Stage 4"). Sits in the shell of `UI-06-stage-2-app-shell.md` (ADR-0047); builds on part A (`UI-06-stage-4-shala-setup.md`, ADR-0048, merged) and ID-07 (`ID-07-one-link.md` §2, §10, Q321; ADR-0046). Requirements: **UI-06**, **ID-07** (asking from the app); touches ID-04, SC-01, ST-06, NT-03, ID-05, UI-05.
- Related: ADR-0030, 0031, 0044, 0045, 0046, 0047. New, proposed: **ADR-0049** (a consent given in the Mini App: the bot's texts, and the request names the consent it showed).

## 1. Scope
**In:** the Shala tab's root rebuilt as one ordered list whose sections appear by data; its empty state; the teacher's waiting list on the tab; the student's request part on the shala card (as the bot's); **asking a teacher from the app** (picker, both consent layers, every result, withdraw); two API routes (choices, ask); `?open=announce&shala=` landing on the shala's card; the request texts without "/teachers" (QB).
**Out:** part A's screens (create form, setup list, class form, sheet: unchanged); a "students are waiting" next step on Today (ID-07 §10 put it in stage 2; `NextStep` has no such kind, see §12); any view of requests for owners or managers (Q322); accepting a personal invite or joining a shala in the app (still the bot, ADR-0049); the wording sweep (stage 5). No migration, no tick change.

## 2. Inventory (read 2026-11-18)
**The root** (`screens/settings/Links.tsx`, lazy; reads `me` (cached), `GET /me/links` (links + `asked` + `waiting`), `GET /me/shalas`, `GET /me/directory-listing`), top to bottom: heading `tab-shala` · `links-load-failed` · **nobody** (no teacher, student, request, shala): `shala-empty`, `shala-starts-title`, `shala-start-invite`, `shala-start-shala` · else: `my-schedule-open` (any shala) · `ann-list` (has a teacher) · teachers card (`links-empty` when none; main line and `links-primary-hint` from two; each: name, ⭐ Make main, Remove…, directory line; each asked teacher: name, Withdraw…, `request-waiting-line` with the shala) · students card (`request-waiting-open` row → My students, `links-no-students` or `link-students-open`, **every student with Remove…**) · invite row `links-invite-first` / `links-invite` → inline card (QR, URL, Copy, Share, New link) · `listing-open` (ID-05 rule) · shalas card (`links-shalas-title`, one row per shala, `shala-create` → inline `CreateShala`).

| Kind of person | What the root shows today | What is wrong |
|---|---|---|
| No shala, no links | heading, `shala-empty`, two quiet starts | nothing (stage 2) |
| Student of one shala | My schedule · teachers card "No teacher… open the link they send you" · students card "No students on your list." · "I teach: invite students" · shalas card (1 row + Create) | 7 things; two empty cards; the teacher line is wrong for her (she can pick one), and picking is only in the bot |
| Student of several | the same with N rows | same |
| Teacher with students, no shala | empty teachers card · students card: waiting row, My students row, **up to 500 names with Remove** · invite · listing · shalas card with only Create | the list repeats My students; the people waiting are two taps down |
| Owner / staff | My schedule · two empty cards · invite · listing · shalas card | the shala is fifth |
| Teacher who is also a student | everything above, ~10 blocks | no main action |

**The shala card** (`shalas/ShalaScreen.tsx`) has **no ID-07 part**: the bot's card has, for a student, `request-open`, one `request-waiting-line` per asked teacher and `request-withdraw`, and for a teacher `request-waiting-open`. **My students** (`teachers/Students.tsx`) opens with the `Waiting` block (ID-07), then the list.
**Copy drift found:** the app's `request-waiting-line` (`$shala`) and `request-withdraw` ("Withdraw…") share keys with the bot's (`$name`; "Withdraw: { $name }…") but not text or variables; no test compares them. Both request consents say "any time in /teachers".

## 3. The root: one ordered list
Sections in **fixed order**; each shows only when it has content; **the first row present is the main action** (the existing primary row style, as the setup list's due step); everything else is a plain row. No empty card anywhere.

| # | Section | Shown when | Opens |
|---|---|---|---|
| 1 | result line (`role="status"`) | after an ask or a withdraw on this visit | – |
| 2 | **Waiting for your answer** (the `Waiting` block, inline, QC) | `links.waiting > 0` | answers in place; Confirm all |
| 3 | `request-open` "🤝 Pick a teacher", sub-line the shala's name when I am a student of two or more | QA: I am a student of a shala, no teacher linked, nothing asked, and its `offer` is not empty | the picker (§4) |
| 4 | `my-schedule-open` | any shala | `schedule` (pushed) |
| 5 | one row per shala, `shala-title` (no card title) | any shala | the card (layer, as now) |
| 6 | teachers card: teachers (⭐, Make main, Remove…, directory line), asked teachers (`request-waiting-line` + `request-withdraw`, bot text), `ann-list` last | a teacher or a request | – |
| 7 | `link-students-open` "👥 My students" (QD) | `links.students` not empty | `students` (pushed) |
| 8 | group `shala-starts-title` ("For teachers and shalas"): `links-invite` / `shala-start-invite` (inline invite card) · `shala-start-shala` (inline create form) · `listing-open` (ID-05 rule) | always (quiet, last) | inline / `listing` |

**First screen per kind:**
- **Nobody:** heading · `shala-empty` · the group. One thing to do: open the link the teacher sends (no button can do it); the group is for teachers. Unchanged from stage 2.
- **Student, one shala, no teacher:** **🤝 Pick a teacher** · My schedule · 🏛 the shala · the group.
- **Student, one shala, with a teacher (or asked):** **My schedule** · 🏛 the shala · teachers card (Anna ⭐ or "⏳ Waiting for an answer: Anna" + Withdraw) · the group.
- **Student of several:** **My schedule** (or a Pick row per shala with someone to pick) · N shala rows · teachers card · the group.
- **Teacher with students, no shala:** [waiting block] · **👥 My students** · the group (Invite students first).
- **Owner / staff:** [waiting block] · **My schedule** · 🏛 the shala(s) · [My students] · the group. The owner's setup list stays on the shala's card and Today's next step (part A).
- **Teacher who is also a student:** the union, same order; the waiting block leads when someone waits.

**Starts** (unchanged values): `create` opens the group's create form, focused (also from nobody: the full list shows); `invite` opens the group's invite card; `shala:<id>`, `class:<id>`, `join:<id>` open that card as now; new `announce:<id>` (§6, QF).

## 4. Asking a teacher from the app
**Where it starts:** row 3 on the root (QA) and, on the **shala card** of a student, the bot's part placed under the title: one `request-waiting-line` per teacher I wait for there, each with `request-withdraw` (one native confirm, `request-withdraw-ask`), then `request-open` while `offer` is not empty. Both read `GET /shalas/{id}/teacher-choices` (one cache key per shala). Staff never read it.

**The picker** (lazy `teachers/AskTeacher.tsx` + `ask.ftl`; a layer with its own Back, so the bar hides; focus on its heading), the bot's question screen line for line:
- `shala-title` as the heading · `request-ask`, or `request-ask-one` with the name when `offer` has one teacher.
- `request-consent-short` (`$me` = " (my name)", empty without one) · `request-until-yes` · `request-know-them`.
- One button per teacher name (`link-no-name` fallback), or one `request-yes`. **A tap is the consent** and sends the request; buttons are disabled while it runs.
- `consent-details` (`aria-expanded`) swaps the three lines for the full `request-consent`, with `consent-short-back`; the names stay under it (ADR-0045: the same tap from either layer).
- A quiet `invite-decline` ("Not now") closes the layer, as Back does.

**Results** (`AskOut.result`, the bot's `_ASKED` map): the layer closes; the screen it was opened from shows the line with the tapped name: `created` → `request-asked` · `linked` → `invite-already` · `waiting` → `request-waiting` · `recent` → `request-recent` · `too_many` → `request-too-many` · `full` → `request-full`. Then `links` and that shala's `teacher-choices` refetch (the new waiting line appears; the Pick row goes when nobody is left). QE: the app stays where the person asked (the bot goes to Today because a chat has no "where").
**Errors:** 404 `not_found` (left the shala meanwhile) → the layer closes, `/me/shalas` and `links` refetch, `shala-load-failed` · 403 `not_allowed` (that person has no Teacher role there now, or I am staff now) → choices refetch, the picker redraws without the name, `request-nobody` when nobody is left · anything else → `settings-save-failed`, `notify("error")`, the picker stays.
**Withdraw:** `DELETE /me/teacher-requests/{teacher_id}` as built (silent, idempotent); the line goes; `request-withdrawn` as the result line.
**No "no" can be read:** the line for a declined pair is `request-waiting`, as for silence; nothing shows a state, a date or a count; the picker never offers a pair with a row (the server's `offer` rule).

## 5. Teacher's waiting list and student's waiting line
| Thing | Today | After |
|---|---|---|
| `Waiting` block (rows, Yes, Not my student + Undo, Confirm all with `as_of`) | top of My students | **top of the Shala root** (QC), mounted only when `links.waiting > 0`, so nobody else pays its read |
| `request-waiting-open` row in the students card | opens My students | **removed**; the block's own heading carries the same key and count |
| My students | `Waiting` + list | the list only (the bot's My students keeps its row) |
| Student's waiting line + Withdraw | teachers card of the root, app's own text | teachers card (bot text, `$name`) **and** the shala card (bot's part) |

Confirm all is unchanged: the first page's `as_of` goes back to `POST /me/student-requests/approve-all`, so someone who asked after the list was drawn stays waiting. Undo lasts until the tab is left (pushing My students or a tab switch remounts the root; the bot's lasts until day 7; known limit Q345).

## 6. Launch links and old state
| Existing | Today | After |
|---|---|---|
| none, unknown, malformed; Telegram's menu button; `start-open-app` | Today | unchanged |
| `?open=practice` · `?open=settings` | Practice root · Today + Settings | unchanged |
| `?open=new-shala` (F3, M1, I1, old messages) | Shala root, `start: create` | Shala root, the group's create form open and focused; no Back |
| `?open=announce` (no `shala`; the bot's My students) | Shala tab + `announce` pushed; Back → root | unchanged |
| `?open=announce&shala=<uuid>` (the bot's shala card) | Shala tab + `announce` pushed; Back → root | **QF:** Shala tab, `start: announce:<id>`: that shala's card with the compose layer; Back → card → root. Not a member any more: the card's `shala-load-failed`, Back → root. A bad uuid: as no `shala` |
| `?open=listing` | Shala tab + `listing`; Back → root | unchanged |
| Today's next step: `invite`, `shala:`, `class:`, `join:` | as stage 2 / part A | `invite` opens the group's invite card; the others unchanged |
| Old "🏛 Create a shala" with the bare address | Today | unchanged (cannot be repaired, stage 1 §5) |
| `localStorage`: next-step "Not now", setup "I teach alone", schedule filter | – | untouched |
| Every bot callback | – | untouched; `test_stale_buttons_bot.py` stays green as it is |

## 7. Routes, chunks, budgets
- **Files.** `screens/settings/Links.tsx` → `screens/shalas/ShalaTab.tsx` (it is no longer a Settings screen; its test moves too). New: `screens/teachers/AskTeacher.tsx` (lazy, `lazyRetry`, opened by `ShalaTab` and `ShalaScreen`), `locales/{en,ru}/ask.ftl` (with it, `addMessages`). `Waiting` moves from the `Students` chunk to the `ShalaTab` chunk (both already import `requests.ts`). `nav.ts`: `ShalaOpen` gains `"announce"`; `ShalaScreen`'s `open` learns it.
- **Initial JS (144.0 of 150 KB): must not rise.** The first chunk gets one more `Start` value in `launchNav` (+ bytes). Headroom if needed: `links-*`, `invite-*` and `shala-start*` messages that only the tab uses move from `app.ftl` to a lazy `shala-tab.ftl` (verify by grep; `link-no-name` and anything Today uses stay).
- **CSS:** no new file expected; `requests.css` already rides with the lazy chunks; the picker uses card, row and chip classes. Initial CSS must not rise.
- The PR records `npm run check:bundle` before and after each slice.

## 8. API and backend
| Method, path | Request → Response | Errors | Use case · policy |
|---|---|---|---|
| `GET /api/v1/shalas/{id}/teacher-choices` | → `TeacherChoicesOut {offer: TeacherChoiceOut[], waiting: TeacherChoiceOut[]}`, `TeacherChoiceOut {id, name}`; oldest staff first | 404 `not_found` (unknown shala, not a member, or staff: one body) | `GetTeacherChoices` (exists) · the repository's guard: a student there |
| `POST /api/v1/me/teacher-requests` | `AskIn {shala_id, teacher_id, consent: "request-1"}` → 200 `AskOut {result: "created" \| "linked" \| "waiting" \| "recent" \| "too_many" \| "full"}` | 404 `not_found` (not a student there) · 403 `not_allowed` (no Teacher role there, or caller is staff) · 422 (unknown `consent`, bad body) | `AskTeacher` (exists) · `can_ask_teacher` in the SQL guard |

- Both `no-store`, initData auth, in `api/v1/teacher_requests.py`; the routes only map. `AskOut` has no state, date or name: `result` is what this tap came to, already projected (a declined pair gives `waiting` or `recent`, as silence does).
- **Consent (ADR-0049):** `domain/teacher_requests.py` gains `RequestConsent(StrEnum)` with `FIRST = "request-1"` and `grants_quiet_note(consent) -> bool`. `AskTeacher.execute(principal, shala, teacher_id, *, consent: RequestConsent)` replaces the `quiet_note_agreed` keyword and derives the flag; the bot's `h1:ta` passes `RequestConsent.FIRST` (the `QUIET_NOTE_AGREED` constant goes). `asked_on` = `caller_today` (the caller's local date; provisional zone without one), as the bot.
- The route awaits the teacher's note (direct, silent, ≤ 3 s, no retry; a failure fails nothing), as the bot's tap.
- **Then** `uv run tristhana-openapi` → `miniapp/src/api/openapi.json` → `npm run gen:api`; `useTeacherChoices(shala, enabled)`, `useAskTeacher()` in `teachers/requests.ts` (not `api/client`, so the first chunk carries none of it).
- **Copy (QB):** `request-consent-short` and `request-consent` lose "in /teachers" / «в /teachers», en and ru. No other bot change; no migration.

## 9. Copy (ux-writer settles; RU «ты», no gendered past tense; names nominative; no word for a refusal on the student's side)
- **New, `ask.ftl`, copied from `bot.ftl` under the same key (a test keeps them equal):** `request-ask`, `request-ask-one`, `request-yes`, `request-consent-short`, `request-until-yes`, `request-know-them`, `request-consent`, `consent-details`, `consent-short-back`, `invite-decline`, `request-asked`, `request-waiting`, `request-recent`, `request-too-many`, `request-full`, `invite-already`.
- **New, `requests.ftl`, copied the same way:** `request-open`, `request-nobody`, `request-withdrawn`.
- **Changed to the bot's text, same key:** `request-waiting-line` ("⏳ Waiting for an answer: { $name }" / bot's ru), `request-withdraw` ("Withdraw: { $name }…"). **Changed in both products (QB):** `request-consent-short`, `request-consent`.
- **App's own new keys: none.** **Removed** (if `check:guide` finds no quote): `links-shalas-title`, `links-empty` and `links-no-students` from the root (`links-no-students` stays on My students).
- **Must survive** (guides quote them): `tab-shala`, `link-students-open`, `my-schedule-open`, `shala-start-invite`, `shala-start-shala`, `shala-create`, `listing-open`, `request-waiting-open`, `request-yes-mine`, `request-not-mine`, `request-undo`, `request-all`, `request-withdraw`, `ann-announce`, `ann-list`, `links-remove`.

## 10. Cross-cutting checks
- **Time zones ✔.** `asked_on` is the student's local date, computed on the server (the client sends no date). No time of day on the root or the picker; the shala card's place line keeps ADR-0044. The 7- and 30-day rules are server-side UTC durations, never shown.
- **Privacy ✔.** The student sees names she could already see as a member; no state, date or count; one line for a "no" and for silence (an API test swaps `declined` for `waiting` and expects equal bodies from both routes and from `/me/links`). Choices only for a student of that shala; the waiting block only to the asked teacher. The consent record is the bot's text, shown in full behind Details; `quiet_note_agreed` is granted by the named consent, never sent as a flag.
- **i18n ✔.** Every string in `.ftl`, en + ru, key and variable parity (`ask.ftl` joins `bundles.test.ts`); Fluent plurals unchanged; names plain text; Russian buttons wrap at 320 px.
- **Responsiveness ✔.** Root: the same three reads; `student-requests` only when someone waits (it moved, not added); `teacher-choices` only in the QA case (one per student shala, at most five, usually one, cached 60 s). Ask: one POST (2 statements + the ≤ 3 s note), then two refetches. Haptic first on every tap; writes wait for the server (not optimistic, as all request writes).
- **Accessibility, touch, theme ✔.** Rows ≥ 44 px; the picker's names one per row; `aria-expanded` on Details; result line `role="status"`, errors `role="alert"`; dark theme through tokens; the main row differs by weight as well as colour.
- **Layering ✔.** Routes map only; the rule of who may be asked stays in the repository guard and `policies.can_ask_teacher`; the consent's grants in the domain; aiogram untouched but for the `h1:ta` argument; import-linter contracts unchanged.

## 11. Tests (vitest also under `TZ=UTC`; pytest with `TEST_DATABASE_URL`)
- **Domain** `test_teacher_requests.py`: `grants_quiet_note(FIRST)` is true; every `RequestConsent` value is mapped.
- **Use case** `tests/application/test_teacher_requests.py`: `AskTeacher` with `consent` stores the flag the domain grants; the two existing ask cases move to the new signature.
- **API** `tests/api/test_teacher_requests_api.py`: 401 on both; choices for a student, 404 with one body for staff, a non-member and an unknown shala; ask → each `result`; a double tap notifies once; a declined pair and a waiting pair give equal bodies (choices, ask, links); 403 when the person asked is an assistant, a manager, front desk or an owner without the Teacher role, and when the caller is staff; 422 for an unknown `consent`; `asked_on` is the caller's local date (Kiritimati vs Honolulu); schemas: `AskOut == {"result"}`, `TeacherChoicesOut`, no "state", "declin" or date words (extends `test_no_request_schema_could_carry_a_no`). **Pinned and turned round:** `test_the_routes_and_their_errors_are_in_the_contract` ("No ask route yet"); `test_the_mini_apps_contract_has_the_routes`.
- **Bot:** `tests/bots/test_teacher_requests_bot.py` (consent text byte for byte, the `h1:ta` call); `tests/infrastructure/test_i18n_teacher_requests.py`: `ITEMS` "any time in /teachers" → "any time"; line 344 `"/teachers" in withdraw` → "remove"; `test_both_layers_name_the_quiet_note_the_tap_agrees_to` reads the domain's consent. `test_stale_buttons_bot.py` untouched.
- **Words in step** `site/src/lib/guide.test.mjs`: the sixteen `ask.ftl` keys, the three new `requests.ftl` copies, `request-waiting-line`, `request-withdraw` and the existing teacher-side copies in `requests.ftl` read the same in app and bot, en and ru, with each variable value.
- **`shalas/ShalaTab.test.tsx`** (from `settings/TeachersAndStudents.test.tsx`): the order of §3 for each kind; the first row is the main one; no empty card; the waiting block on the root only when `waiting > 0` and no `student-requests` read otherwise; the Pick row only in the QA case; no student names on the root; the group last, with `listing-open` by its rule; `create` and `invite` starts. **Pinned and turned round:** "the screen offers no way to ask a teacher: that stays in the bot", "both lists, with a fallback for no name", "each empty list says so…", "removing a student confirms…" (moves to `Students.test.tsx`), "has a waiting line with the name and the shala".
- **`teachers/AskTeacher.test.tsx`** (new): one and several teachers; short layer, Details and back, names under both; the POST body; each `result` line in en and ru; 403 redraw and `request-nobody`; 404 close; disabled while pending; no state, date or count in the DOM; a long name and Russian at 320 px.
- **`shalas/Shalas.test.tsx`:** a student's card shows the waiting lines, Withdraw and `request-open`; staff never read choices. **`teachers/Students.test.tsx`:** "the waiting block" describe moves to `ShalaTab.test.tsx`; My students has no block. **`shell/nav.test.ts`, `App.test.tsx`:** `?open=announce&shala=` → card + compose, Back → card → root; the others of §6.
- **By hand:** 320 px wide in Russian and the dark theme: the root for each kind, the picker (both layers), the shala card's student part; one iPhone and one Android.

## 12. Guides and screenshots (`/guide-update UI-06`, each page with its `ru/` twin)
- **Pages:** `students/my-teacher` (pick and withdraw in the app; `:ftl[request-withdraw]{from=app}` now needs `name=`), `students/my-shala` (the Pick row on the tab and the card), `teachers/invite-students` (line 44: the list is at the top of the Shala tab), `teachers/what-you-see` (line 17), `staff/create-shala` (line 41 names a card row only the bot has), `start/bot-and-app`, `start/first-steps`, `reference/faq`, `reference/whats-new`. `features:` gains ID-07 where asking is shown.
- **Screenshots (en + ru):** `app-shala-tab` changes whole; `app-requests` becomes `click: [tab-shala]` with `top` on the waiting block; `app-student-card` and `app-announce` keep `[tab-shala, link-students-open, …]` (the row keeps that key, no count); `app-shala`, `app-class-form`, `app-occurrence`, `app-class-edit`, `app-shala-announce`, `app-shala-setup` keep `[tab-shala, =shala…]` (the shala row keeps its name); `app-shala-empty` and `app-shala-new` unchanged. **New:** `app-ask-teacher` (`as: member`, `click: [tab-shala, request-open]`; the demo member needs a shala teacher to pick, as `bot-ask-teacher`).
- **Notes on acceptance (not done by this spec):** UI-06 and ID-07 rows in `02 Requirements.md`; QA–QF numbered in `03 Open Questions & Decisions.md`; ADR-0049 into `04 Architecture.md`; "Amended by ADR-0049" lines in ADR-0031 and ADR-0045; ID-07 §10's Today card recorded as not built; `09 Roadmap.md`.

## 13. Build slices (each ends green: tests, ruff `--no-cache`, pyright, lint-imports, vitest, lint, typecheck, `check:bundle`)
1. **Backend.** `RequestConsent`, `AskTeacher(consent)`, `h1:ta`; the two routes and their tests; the consent texts without "/teachers" and their tests; `tristhana-openapi` + `gen:api`.
2. **The root.** `ShalaTab.tsx` (the order, the main row, the group, the inline `Waiting`, the students row); My students without the block; `announce:<id>` in `nav.ts` and `ShalaScreen`; key moves if `check:bundle` asks.
3. **Asking.** `AskTeacher` + `ask.ftl`; the root's Pick row and the card's student part; `request-waiting-line` / `request-withdraw` in the bot's words; the words-in-step test.
4. **Guides, screenshots, notes.**

## 14. Questions for the owner (the bold recommendations are what this spec builds)
- **QA. Where "Pick a teacher" starts.** **Recommended: on the shala's card (as in the bot) and, for a student with no teacher yet, as the first row of the Shala tab**: for someone who joined by the shala's QR that is the one thing left to do. Costs one small read in that case only. Alternative: on the shala's card only (one tap further, no extra read).
- **QB. "/teachers" in the request consent.** It points the app at a bot command, and the bot's own menu no longer lists it. **Recommended: say "You can remove a teacher from your list any time" in both products, so the app shows the bot's exact text** (same promises; ADR-0049). Alternatives: app-only consent texts naming the Shala tab (two records to keep in step), or the bot's text as it is.
- **QC. The teacher's waiting list.** **Recommended: at the top of the Shala tab, and no longer on My students** (one place in the app; the bot keeps its row on My students). Alternatives: on both; or as today (a row on the tab opens My students).
- **QD. Students on the tab.** Today the tab lists every student with Remove, the same names My students shows. **Recommended: one row "👥 My students"; names, their week and Remove stay on My students.** Alternative: keep the list on the tab.
- **QE. After asking in the app.** **Recommended: stay where you asked, with one line ("✉️ Request sent to Anna…") and the new waiting line under it.** Alternative: go to Today with the line on top, as the bot does.
- **QF. "📣 Announce" from a shala in the bot (`?open=announce&shala=`).** **Recommended: open that shala's card with the message form on top; Back returns to the card, where its announcements are.** Alternative: as today (the form over the tab; Back to the tab).
