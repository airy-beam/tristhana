# PR-10 + NT-01 (practice category) + NT-02: daily practice reminder with a one-tap log

- Status: **accepted** (owner: all yes, 2026-10-19; ashtanga-expert reviewed) · Date: 2026-10-19 · **§9 overrides §2–§8 where they differ**
- Requirements: **PR-10** (quick log from a reminder: one tap "✅ Same as last time"), **NT-01** (the *practice reminder* category: on/off, time of day), **NT-02** (quiet hours and the daily cap, already built for moon, now shared), **UI-01** (only the opt-in offer). Builds on PR-01/02 (`SetDayStatus`, `CopyLastPractice`, `d1:`/`p1:` screens) and MD-03 (tick, ledger, `Notifier`, settings). Budget: < 300 ms p50 per tap (warm).
- Related: ADR-0005 (time), 0008 (stateless callbacks), 0012 (webhook reply), **0018** (scheduler tick; this adds a category and changes no decision, so there's **no new ADR**).

## 1. Scope
**In:** an opt-in daily **log prompt** at a local time the user picks, on chosen weekdays. It's skipped on days already logged and on moon days of the followed calendar. Quick-log buttons on the reminder, a combined use case `QuickLogSameAsLast`, a bot `/remind` settings screen, a one-time offer on the "practice saved" screen, a `practice` block in `/me/notification-settings`, and a Mini App toggle in a Reminders section.
**Out:** the weekly recap, milestones (GM-01), class reminders (SC-06), teacher announcements (NT-03), **PR-09 auto-fill** (we don't nudge on a moon day, but we don't log it either), a second nudge or follow-up, a "last time" summary inside the reminder (it would cost a lookup per send; the confirmation shows it), and the ID-06 settings page (quiet hours/cap UI).
**Cut if time is short:** the Mini App section (the bot and API cover it).

## 2. Flows and copy
- **Model (⚑ expert): an after-practice "how was your day?" prompt, not a "time to roll out the mat" nudge.** Ashtangis practise at 4–7 am. A pre-practice ping is redundant for them, would sit inside quiet hours (22–07), and PR-10's value is the log. Default **20:00** local (practice is done for morning and evening practitioners alike). Chips `[08:00] [10:00] [13:00]` / `[18:00] [20:00] [21:00]`. The API accepts any 15-minute slot outside quiet hours.
- **Opt-in offer (once).** On screen V (after ✓ Done, PR-02), only for **today's** practiced day and only while the choice is still unmade (`practice_on IS NULL`), V adds `remind-offer` with `[🔔 Yes, remind me] [No, thanks]`. Yes turns the reminder on (20:00, Sun–Fri) and opens screen R, where the time is visible and changeable. No records "off" and re-renders V without the offer. The offer never appears again. It's also reachable via `/remind` (command menu + `/help`).
- **`/remind` → screen R:** text `remind-status-on` "🔔 Practice reminder: Mon, Tue, Wed, Thu, Fri, Sun at 20:00 Almaty (UTC+5)" (all 7 days = "every day") or `remind-status-off`, then `remind-explain`. Buttons: the 6 time chips (✓ on the current one) · weekday toggles `[✓ Mon] [✓ Tue] [✓ Wed] [✓ Thu]` / `[✓ Fri] [Sat] [✓ Sun]` (Babel short names; the last remaining day can't be turned off) · `[🔕 Turn off]` / `[🔔 Turn on]` · `[🌙 Moon reminders]` (→ `m1:r`). The moon screen R gains `[🧘 Practice reminder]` (→ `r1:v`). With no zone, settings still save, plus `moon-zone-needed` and `[Open the app]`.
- **The reminder** (a new message from the tick): `remind-practice` "🌿 { $day }: how was your day? One tap is enough." Buttons:
  `[✅ Practiced, same as last time]` (full width) · `[🧘 Practiced…] [😌 Rest day]` · `[📅 Other…] [🔕 Turn off]`.
  ✅ = `QuickLogSameAsLast`, and the message is **edited in place** into PR-02's screen V ("✓ Today, Mon 19 Oct: 🧘 Practiced. Practice done 🙏" + "Mysore · Primary → Navasana" + `[📝 Details] [✏️ Change] [📅 Another day]`). With no earlier practice, the status still saves and P (details) opens. 🧘… = the existing `d1:s:<date>:p` (→ P). 😌 = `d1:s:<date>:r`. Other… = `d1:o:<date>` (the full picker: moon, 🌸, sick, travel, no practice). 🌸 deliberately stays one tap deeper, since the reminder stays in chat history. 🔕 re-renders the reminder plus `remind-off-note`, with `[🔔 Turn back on]`. There's **no "Not today" button**: ignoring the message is fine and nothing follows up.
- **Failures:** a future date (stale keyboard after a zone change) → PR-01's week picker with `log-date-future`; DB down → `error-temporary`.
- **Copy (new keys; RU «ты», no gendered past tense; ⚑ ashtanga-expert + ux-writer).** `bot.ftl`: `remind-practice` (above / «🌿 { $day }: как прошёл день? Хватит одного нажатия.»), `remind-same` "✅ Practiced, same as last time" / «✅ Практика, как в прошлый раз», `remind-practiced` "🧘 Practiced…" / «🧘 Практика…», `remind-other` "📅 Other…" / «📅 Другое…», `remind-turn-off` "🔕 Turn off" / «🔕 Выключить», `remind-turn-on`, `remind-turn-back-on`, `remind-off-note` ("🔕 Practice reminders are off. You can turn them on any time in /remind." / «🔕 Напоминания о практике выключены. Включить снова можно в /remind.»), `remind-status-on` ("🔔 Practice reminder: { $days } at { $time }" / «🔔 Напоминание о практике: { $days }, в { $time }»), `remind-status-off`, `remind-every-day`, `remind-explain` ("Once a day I'll ask how it went, with one-tap buttons. Never on moon days or days you've already logged." / «Раз в день спрошу, как прошла практика, с кнопками в одно нажатие. В лунные дни и в уже отмеченные дни не напоминаю.»), `remind-offer` ("Want a gentle evening prompt to log your day in one tap?" / «Напоминать вечером отметить день одним нажатием?»), `remind-offer-yes` "🔔 Yes, remind me" / «🔔 Да, напоминай», `remind-offer-no` "No, thanks" / «Нет, спасибо», `remind-practice-link` "🧘 Practice reminder" / «🧘 Напоминание о практике», `remind-moon-link` "🌙 Moon reminders" / «🌙 Лунные напоминания»; `help-text` gains /remind. `app.ftl`: `remind-card-title`, the status/explain keys, `remind-save-failed`. Never "missed", "don't forget", "you haven't".

## 3. Design
**Domain (`domain/notifications.py`, pure).**
- `PracticeReminder(on: bool | None, at: time, days: frozenset[int])`: ISO weekdays 1–7. `on=None` = never chosen (treated as off; drives the one-time offer). `enabled` = `on is True`. `NotificationSettings` gains `practice`. `DEFAULTS.practice` = `(None, 20:00, {1,2,3,4,5,7})` (Saturday off, as in Mysore; 01 Domain Context). `PRACTICE_TIMES` = the 6 chips.
- `check_settings` also checks: days non-empty and ⊆ 1..7, `at` on the 15-minute grid, and, when enabled, not inside quiet hours.
- `practice_key(d) = f"practice:{d.isoformat()}"`.
- `Candidate` gains `logged: frozenset[date]` (the account's logged dates around today).
- `due_practice_reminder(now, c, picked=0) -> DuePractice(key, local_date) | None`. For d in (local today, local yesterday): `send_at = send_instant(d, at, zone)`, due iff `send_at ≤ now < send_at + GRACE`, d's weekday ∈ days, `now` local isn't in quiet hours, the key isn't sent, `d ∉ logged`, d isn't a date in `moon_days`, and `sent_today + picked < cap`. Checking yesterday covers a late slot whose grace crosses midnight. The reminder is always about d, the send date. The caller passes `picked = len(moon reminders chosen this tick)`, so **one cap covers both categories** and moon goes first.

**Application.**
- `MoonCandidate` → `ReminderCandidate` (+ `logged`). `NotificationRepository.moon_candidates` → `candidates(since, utc_today, defaults)`: accounts with moon **or** practice enabled. `patch_practice(account_id, PracticeReminderPatch(on, at, days), defaults)`. `save` takes `practice: PracticeReminder | None` (None = keep).
- `RunTick._send_to`: moon reminders as today, then `due_practice_reminder` with the same claim → deliver → finish loop (category `"practice"`). Moon calendars are already loaded per city for the window. Practice candidates with moon off still need their city's days (same cache).
- `Notification` = `MoonReminder | PracticeReminder(local_date, today)`. `Notifier.deliver(recipient, n)` dispatches by type. `bots/telegram/notifier.py` renders via `remind.practice_reminder_screen`.
- Use cases (Principal, own data): **`QuickLogSameAsLast(principal, date) -> QuickLog(day, practice | None)`** = `SetDayStatus(practiced)` then `CopyLastPractice`. `NoPreviousPractice` → `practice=None`. `DateInFuture` propagates. **2 statements**, the same as PR-02's 🧘 tap: a single CTE statement is unsafe, because the copy's "day is practiced" guard can't see a row inserted earlier in the same statement. It's an explicit tap, so it overwrites like any `/log` tap. `UpdatePracticeReminder(principal, patch)` validates via `check_settings` (like `UpdateMoonReminders`). `NotificationSettingsUseCase` covers the API.

**Infrastructure.** `candidates` keeps its single connection and adds **one statement per tick** (not per account): `SELECT account_id, local_date FROM day_log JOIN notification_settings USING (account_id) WHERE practice_on AND local_date BETWEEN utc_today−2 AND utc_today+1` (PK range per account). Claim, finish, stale claims, retries and blocked handling are unchanged.

**API** (extends MD-03's endpoints; initData auth).

| Method, path | Request | Response |
|---|---|---|
| `GET /api/v1/me/notification-settings` | none | 200 adds `practice: {on: bool, chosen: bool, at: "HH:MM", days: [1..7]}` |
| `PUT /api/v1/me/notification-settings` | adds **optional** `practice: {on, at, days}` (omitted = unchanged, so cached older Mini App bundles keep working) | 200 same; 422 `invalid_settings` (empty days, off-grid, in quiet hours) |

There's no quick-log endpoint: the Mini App logs with the existing `PUT /me/days/{date}` + practice PUT.

**Bot** (`bots/telegram/remind.py`, `remind_callbacks.py`, prefix **`r1:`**; the same tap protocol: answer in parallel, edit as the webhook reply).

| Data | Meaning | Max bytes |
|---|---|---|
| `r1:v` | screen R | 4 |
| `r1:o:1` / `r1:o:0` | on / off (absolute) | 6 |
| `r1:t:2000` | send time | 9 |
| `r1:w:123457` | weekday set (absolute ISO digits, ≥ 1) | 12 |
| `r1:y:20261019` / `r1:n:20261019` | the offer on V: yes (→ R) / no (→ V without the offer) | 13 |
| `r1:s:20261019` | quick log: practiced + same as last time (→ V) | 13 |
| `r1:q:20261019:0` / `…:1` | from a reminder: off / back on (re-renders the reminder) | 15 |

Plus the reused `d1:s:…:p`, `d1:s:…:r`, `d1:o:…`. **Round trips:** ✅ = middleware + 2. Settings taps = middleware + 1 (upsert `RETURNING` renders R). The V offer adds one PK read on V for today only.

**Mini App.** A "🔔 Reminders" section below MoonCard: a practice on/off switch, the time chips, weekday chips (hidden while the zone is unknown, with `moon-zone-needed-app`), via the existing `useNotificationSettings` / optimistic `useSaveNotificationSettings` (scope `"settings"`). ~+1.5 KB gzip.

## 4. Ops
No GCP steps ☁️. On merge, migrate applies `0005`. Afterwards the owner runs `python3 tools/telegram/set_webhook.py` (adds `/remind` to the command menu).

## 5. Migration `0005_practice_reminder`
- `notification_settings` add `practice_on boolean null` (null = never chosen), `practice_at time null`, `practice_days smallint[] null check (practice_days <@ '{1,2,3,4,5,6,7}' and cardinality(practice_days) > 0)`. Null = domain default.
- `notification_delivery_category_check` → `category in ('moon','practice')` (drop + add; wider, so safe while the old revision serves).
- Downgrade: delete `practice` deliveries, restore the narrow check, drop the columns.

## 6. Cross-cutting checks
- **Time zones:** wall clock + the **account zone**, recomputed every tick (DST and moves need no rewrite). The provisional zone is **never** used: no zone, no reminder. The dedupe key is the local date, so a same-day flight doesn't double it. The moon-day skip uses the followed calendar's date as a local date (as MD-03 does). Every shown time goes through `TimeArg`. Tests: Kolkata +5:30, Kathmandu +5:45 (20:00 = 14:15 UTC → sent 14:20), Berlin DST both ways, a late slot crossing midnight with quiet hours off, east of the date line.
- **Privacy:** the reminder carries no personal data; 🌸 isn't on the reminder (one tap deeper). The ledger stores keys only. Logs: account uuid + counts. Account delete cascades.
- **i18n:** all copy in `bot.ftl`/`app.ftl` with en/ru parity; weekday names and dates via Babel; no plurals needed.
- **Responsiveness:** ✅ ≤ 2 short statements + a concurrent callback answer; settings taps 1. The tick adds one statement per run, and ≤ 1 message per opted-in account per day. No new dependency or job.

## 7. Test plan
- **Domain:** `due_practice_reminder`: exact minute, 9 min late, after grace, quiet hours, already sent, day logged, moon day (followed calendar), weekday off, `on=None`/`False`, cap reached by a moon reminder in the same tick (`picked`), the yesterday window across midnight, the zones above; `check_settings` (empty days, off-grid, in quiet hours only when enabled); defaults.
- **Use case (fakes, fixed clock):** `QuickLogSameAsLast` sets practiced + copies, with no history → status saved and practice None, future date raises; the tick sends moon then practice under one cap, claims before delivering, skips a logged day, and `blocked`/`retry_after` behave as for moon; `UpdatePracticeReminder` patches one field.
- **Infrastructure (real Postgres):** candidates include practice-only and moon-only accounts, `logged` dates, `practice_on` null vs false; settings round trip with nulls = defaults; CHECKs; the `practice` category accepted; upgrade → downgrade → upgrade; `alembic check`.
- **API contract:** GET includes `practice` with defaults; PUT with and without `practice` (omitted keeps stored values); 422s; OpenAPI regenerated.
- **Bot handler (fake use cases, fake notifier):** the reminder keyboard (5 buttons, absolute date); ✅ edits into V with the summary; ✅ without history → P; 🔕 / back on re-render; R toggles (the last weekday can't be removed), time ✓, zone-needed note; the offer only on V for today while unchosen, gone after yes or no; links `r1:v` ↔ `m1:r`; malformed data ignored; **every `r1:` callback ≤ 64 bytes**; the notifier dispatches by type; en/ru keys exist.
- **Mini App (Vitest):** the switch saves optimistically and rolls back; chips hidden without a zone.
- **Architecture:** import-linter (domain pure, aiogram only in `bots`); bundle check.

## 8. Open questions for the owner (recommendations)
1. **Scope** as §1 (practice log prompt + one-tap log now; recap, milestones, class/teacher reminders, PR-09 later)? Recommended: yes.
2. **Opt-in**, offered once on the "practice saved" screen (today only) plus `/remind`, not on by default like moon? Recommended: yes. A daily message is more intrusive than ~4 moon messages a month.
3. **After-practice prompt at 20:00 default** (chips 08/10/13/18/20/21) rather than a morning "roll out the mat" nudge? Recommended: yes ⚑ ashtanga-expert.
4. **Days:** per-weekday toggles, default Sun–Fri (Saturday off)? Recommended: yes. Sunday-off people tap two chips; PR-09's weekly day off is a separate setting later.
5. **Skip** moon days of the followed calendar and any already-logged day (no auto-fill)? Recommended: yes.
6. **Buttons:** ✅ same as last time · 🧘 Practiced… · 😌 Rest day · 📅 Other… · 🔕 Turn off; no "Not today", no 🌸 on the reminder? Recommended: yes.
7. **✅ overwrites** an existing status/details for that date (an explicit tap, like `/log`)? Recommended: yes.
8. **One shared daily cap (3)**; on the eve of a moon day, two evening messages (19:00 moon, 20:00 practice)? Recommended: accept now; merge them later if beta testers find it noisy.
9. **Surfaces:** a separate `/remind` screen linked both ways with `/moon`'s reminders, not one merged screen? Recommended: yes; merging belongs to ID-06 settings.
10. **API `practice` optional in PUT** (omitted = unchanged)? Recommended: yes. Q25 (PUT freezes defaults) stays open for ID-06.
11. **Copy ⚑** (reminder line, "Practiced, same as last time", offer wording, RU) settled by the ashtanga-expert + ux-writer before release? Recommended: yes.

## 9. Decisions (owner: all yes, 2026-10-19, after the ashtanga-expert review)
1. Scope as §1. 2. Opt-in: offered once on V (today, `practice_on IS NULL`) + `/remind`.
3. **Default time: 10:00 if the offer's Yes is tapped before 14:00 local, else 20:00** (pure `default_practice_time(local_time)`; the account's effective zone, provisional allowed only for this guess). `DEFAULTS.practice.at` = 10:00 (API/`/remind` turn-on with nothing stored). **Chips 09·10·12 / 18·20·21.** Expert: 20:00 lands at bedtime for morning practitioners and stacks with the 19:00 moon reminder; 08:00 falls inside Mysore windows.
4. **Days Sun–Fri** default, plus one-tap presets `[Day off: Sat] [Day off: Sun]` (= `r1:w:123457` / `r1:w:123456`) above the per-day toggles.
5. Skip moon days and logged days (no auto-fill).
6. Buttons as §2.
7. **Replaces §8.7: ✅ never overwrites.** `QuickLogSameAsLast` inserts the practiced status **only if the day has none** (`INSERT … ON CONFLICT DO NOTHING RETURNING`); if the day is already logged it returns `AlreadyLogged(day)` and the bot shows V for the stored status with `[✏️ Change]` (protects a 🌸 record). 🧘/😌 keep using `d1:` (the next screen shows the status).
   **"Same as last time" from a reminder copies the newest non-Led practice** (fallback: newest of any class type); V shows the copied context/length, plus the copied practice's date when it is more than 14 days old. (The PR-02 details screen keeps its current "newest" rule; aligning it is a follow-up question.)
8. Shared cap 3, moon first; accepted (10:00 default keeps them apart).
9. **After 10 unanswered reminders in a row** (a reminded day that is still unlogged), the tick sends **one gentle note instead of the 11th reminder** and sets `practice_on = false`; `/remind` turns it back on. Needs `logged` and deliveries over a longer window (LOOKBACK 12 → 21 days). "Pause for N days" after 🌸/sick/travel: later, with multi-day LH.
10. `/remind` its own screen, linked with the moon reminders. PUT `practice` optional.
11. Copy: the expert's lines (`remind-practice` "🌿 { $day }: practice or rest? One tap to log it." / «🌿 { $day }: практика или отдых? Отметить можно одним нажатием.», `remind-offer` without "evening", `remind-explain`), then ux-writer polish. Rest button reuses PR-01's label.

## 10. Implementation notes and review fixes (2026-10-19)
- **Migration 0005** found that 0004's CHECK constraints were named through the naming convention twice (e.g. `notification_delivery_notification_delivery_category_ch_2931`, also on prod). 0005 drops either spelling with `IF EXISTS` and recreates the category check under the clean name.
- **Pause note** has its own key `practice-pause:<date>`, so it ends a run of unanswered reminders: turning reminders back on starts a fresh count (code-review blocker, regression tests in domain and tick).
- **Stale taps:** an old offer Yes/No is a no-op once a choice exists; a send time inside (default) quiet hours is refused even while the reminder is off.
- **API:** a PUT without `practice` validates against the stored practice but no longer writes the practice columns (no lost bot change, no frozen defaults).
- **Responsiveness:** ✅ = account lookup + 2 statements (insert-if-absent, copy); the offer's settings read is skipped on the reminder path; an already-logged day reuses the row it read.
- **Mini App:** Reminders card with on/off, time chips (with the zone label), "Day off: Sat/Sun" presets and weekday chips; moon taps never send the practice block.
- **Copy (ux-writer):** RU `/remind` help and `remind-explain` neutral ("как прошёл день"); `remind-paused` points to its button; RU `remind-copied-from` «Скопировано из практики { $date }».
- **Known limits / follow-ups:** 🧘/😌 on an old reminder go through `d1:` and can still overwrite a day logged since (accepted §9.7; ✅ never does); a reminder whose grace crosses midnight counts toward the previous day's cap (only with custom quiet hours); the PR-02 details screen keeps "newest" for "same as last time".
