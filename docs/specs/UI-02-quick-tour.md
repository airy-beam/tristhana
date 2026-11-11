# UI-02: quick tour, a bot carousel and Mini App coach-marks

- Status: **accepted** (owner: all as recommended, 2026-11-06) · Date: 2026-11-06 · Size **S/M** (~2 days), Phase 2
- Requirements: **UI-02** (interactive quick tour, bot carousel and Mini App coach-marks, re-openable from /help). Touches UI-01 (`/start`, `/help`, `home-first-hint`), UI-04 (layered Back), NF-09 (bundle). Budget: < 300 ms p50 per tap (warm).
- Related: ADR-0008 (stateless callbacks), 0012 (webhook reply), 0021 (explicit choices). **No new ADR:** no schema, no API, nothing hard to reverse. A later server flag would be purely additive.

## 1. Scope
**In:** a 5-step bot carousel, opened from a `[🧭 Quick tour]` button under `/help` and under `/start`; 5 coach-marks on the Mini App Home; a one-time Home offer card; a re-open row in Mini App Settings.
**Out:** any stored server state, migration, API change or use case; a `/tour` command (it would need a `set_webhook.py` run); a push or broadcast about the tour; forcing or auto-starting the tour; coach-marks on other screens (Stats, Settings, My asanas); handing over from the bot tour to the coach-marks (`?tour=1`); tracking who took the tour (the app has no analytics); a tour library.
**Left out of the steps on purpose** (`/help`, the screens themselves and first use cover these; 🌸 is found on the status grid, not in `/help`): language, city and location share, quiet hours and cap, check-in scales, export and delete, the practice-count milestones (better as a surprise), teachers (Phase 3), 🌸 (§2).

## 2. Flows and copy
**Principle:** the tour is a side door. It never replaces the log grid unless the person asks, and leaving it returns them to where they were.

**Bot**
- **Offer, stateless:** `/start` gets one new last row `[🧭 Quick tour]`. The grid, `📅 Another day` and the language/app row stay as they are, so the first log is still 2 taps. `/help` keeps its text, apart from "practice reminder" (owner decision 8), and gains the same button. Same message for everyone: no flag, as in UI-01.
- **Carousel:** a tap edits that message in place. Slash commands in the text are tappable by Telegram itself, so each step can be tried with no extra code; tapping one leaves the tour in place above.
  ```
  1 of 5
  📝 Your log
  Practice or rest? Both go in your log. …
  [Next ›]
  [✓ Done]
  ```
  Middle steps: `[‹ Back] [Next ›]` / `[✓ Done]`. Last step: `[‹ Back] [✓ Done]` / `[Open the app]`. ✓ Done is on every step, so leaving is always one tap.
- **Done returns to the origin:** the `/start` screen with today's grid (so logging is right there again), or the `/help` text with its button.

**Mini App**
- **Offer:** a small card under the Today card, "Want a quick look around?" `[Show me] [Not now]`. It is decided **when Home mounts**, never while a person is on the card, so nothing jumps under their thumb mid-log. Shown when all hold:
  1. `onboard.tour` is not set on this device;
  2. the person has logged: `days.length > 0` (`useDays` covers the last 7 days) or `onboard.logged`;
  3. no travel prompt is pending.

  Condition 2 is the exact opposite of `home-first-hint`'s condition, so the two can never show together. A newcomer gets hint → log → offer on the next time Home mounts. Logging is first, and only one question shows at a time (the PR-06 rule). Bot-first people get the offer on their first open, and beta users on their next one.
- **Show me or Not now** sets `onboard.tour = 1` straight away, so the offer never returns, finished or not. **Re-open:** a `🧭 Quick tour` row in Settings, above Privacy (not next to the delete card). It goes to Home and starts there. `/help` can't reach a Mini App-only person, so the row is needed.
- **Coach-marks:** a dimmed Home with a spotlight on one target, plus a sheet with the step text, "2 of 5" and `[‹] [Next] [Done]`. Targets can't be tapped and the tour writes nothing. Telegram's Back exits the tour; `‹` goes to the previous step. On exit the page scrolls back to the top, Today card in view.

**🌸 is not mentioned, in either tour.** It is a personal topic in a tour that everyone sees. Naming it adds nothing for those who need it (the button is already on the grid, and its own screen says "Only you see this"), and it singles it out for those who don't. Steps therefore never list the statuses, which also keeps them right for people using `hide_ladies`. The spotlight shows the Today card as it stands. The pause line names sick and travel only, because those are the plain examples; 🌸 gets the same question on first use. Privacy promises are limited to "private note", so nothing expires when teachers arrive (Q33).

**Copy** (drafts, ⚑ ux-writer + ashtanga-expert; RU «ты», no gendered past tense; EN Mini App says "log", never "run"; no streak/missed/skipped/«серия»).

`bot.ftl`: `tour-open` "🧭 Quick tour" / «🧭 Знакомство»; `tour-progress` "{ $n } of { $total }" / «{ $n } из { $total }»; `tour-next` "Next ›" / «Дальше ›»; `tour-back` "‹ Back" / «‹ Назад»; `tour-done` "✓ Done" / «✓ Готово».

| Key | EN | RU |
|---|---|---|
| `tour-log` | 📝 Your log. Practice or rest? Both go in your log. Mysore, led or on your own, short or full: it's all practice. After a practice you can add details, how it felt and a private note. An earlier day? /log takes you back. | 📝 Журнал. Практика или отдых? В журнал идёт и то, и другое. Майсор, лед-класс или самостоятельно, коротко или полностью: всё это практика. После практики можно добавить детали, самочувствие и личную заметку. Нужен прошлый день? Открой /log. |
| `tour-rest` | 🌿 Rest and moon days. Rest is part of the practice. Full and new moon days are traditional rest days: they fill in on their own, and so does your weekly day off once you set it in /settings. If a day goes differently, just log it. Dates and moon reminders are in /moon. | 🌿 Отдых и лунные дни. Отдых — часть практики. Полнолуние и новолуние — традиционные дни отдыха: они отмечаются сами, и твой выходной тоже, если выбрать его в /settings. Если день прошёл иначе, просто отметь его. Даты и лунные напоминания — в /moon. |
| `tour-remind` | 🔔 Reminders. If you'd like, /remind asks once a day how it went, with a one-tap log. It comes on your practice days, not on moon days. Out for a few days, say sick or traveling? Log the first day and I'll offer a pause. | 🔔 Напоминания. Если хочешь, /remind будет раз в день спрашивать, как всё прошло: ответить можно одним нажатием. Напоминание приходит в дни практики, но не в лунные дни. Несколько дней без практики, например болезнь или дорога? Отметь первый день, и я предложу паузу. |
| `tour-asanas` | 🧘 My asanas. /asanas keeps your last asana, so logging a practice takes fewer taps. New asana from your teacher? Mark it there 🎉 | 🧘 Мои асаны. /asanas помнит твою последнюю асану, и отмечать практику проще. Новая асана от учителя? Отметь её там 🎉 |
| `tour-app` | 📊 The app. Your year at a glance, month summaries and a calendar for earlier days. Everything you log here is there too. This tour stays in /help. | 📊 Приложение. Весь твой год на одном экране, итоги месяца и календарь для прошлых дней. Всё, что ты отмечаешь здесь, есть и там. Знакомство всегда можно открыть в /help. |

`app.ftl`: `tour-open` as in the bot; `tour-offer` "Want a quick look around? It takes a minute." / «Показать, что здесь где? Это займёт минуту.»; `tour-offer-yes` "Show me" / «Покажи»; `tour-offer-no` "Not now" / «Не сейчас»; `tour-progress`, `tour-next` "Next" / «Дальше», `tour-prev` "‹" with `.aria-label` "Previous step" / «Предыдущий шаг», `tour-done` "Done" / «Готово».

| Key (target) | EN | RU |
|---|---|---|
| `tour-today` (Today card) | Log today: practice or rest. After a practice you can add details, how it felt and a private note. | Практика или отдых? После практики можно добавить детали, самочувствие и личную заметку. |
| `tour-stats` (📊 My practice) | Your year at a glance, plus a calendar for filling in earlier days. | Весь твой год на одном экране и календарь, чтобы дополнить прошлые дни. |
| `tour-asanas` (🧘 My asanas) | Your last asana. Log a new one here when your teacher gives it. | Твоя последняя асана. Здесь же отмечается новая, когда её даёт учитель. |
| `tour-moon` (moon card) | The next moon days: full and new moons, traditional rest days. You pick the city in Settings. | Ближайшие лунные дни: полнолуние и новолуние, традиционные дни отдыха. Город — в настройках. |
| `tour-settings` (⚙️ Settings) | Your city, weekly day off, reminders and privacy. This tour lives here too. | Твой город, выходной, напоминания и приватность. Знакомство тоже здесь. |

## 3. Design
- **Domain, application, ports, infrastructure:** no changes. The tour is static presentation with no rule to enforce, so it needs no use case. The only data it touches is the `/start` screen, through the existing `StartScreens`.
- **State: none on the server.** The bot's offer is a permanent button. The Mini App uses `localStorage` `onboard.tour`, next to `onboard.logged`. A server column (migration, `Me` field, PATCH, client regen) would buy only "offered once across devices". The worst case without it is one extra dismissable card on a second device, or after Telegram clears WebView storage. Telegram `CloudStorage` also syncs, but it is async, adds a client-version fallback, and survives account deletion (ST-09 clears `localStorage` only). The two tours are tracked separately on purpose: they teach different things.
- **Bot:** new `bots/telegram/tour.py`, no aiogram outside `bots/telegram/`.
  - `STEPS` is a tuple of Fluent keys. `TourScreens.step(locale, n, origin) -> Screen` is pure.
  - Prefix **`q1:`** (free; `t_` stays reserved for ID-04): `q1:<n>:<origin>` shows step n, `q1:d:<origin>` is Done, origin `s` or `h` (≤ 6 bytes).
  - `n` above the last step clamps to the last one (old keyboards after a future change); malformed data only answers.
  - `on_help` moves here, and `register_start` returns `StartScreens` for Done and adds the row in `start()`. `register_tour` goes before the catch-all callback handler in `build_router`.
  - Handlers use `answered()` then `show()` from `screens.py`, as elsewhere. `[Open the app]` uses `app_button` and is hidden without `miniapp_url`. Tapping it also records the zone for bot-only people.
- **API:** none. OpenAPI unchanged.
- **Mini App:**
  - `screens/onboard.ts` (new, initial): `loggedBefore`/`markLogged` move here from `TodayCard`, plus `tourSeen`/`markTourSeen`. Blocked storage counts as seen ("never nag", as today).
  - `screens/tour/TourOffer.tsx` (initial, tiny). `zones.ts` gains `travelPending(zone)`, shared with `TravelPrompt`.
  - `screens/tour/Tour.tsx` (lazy, no dependencies): a `createPortal` into `body`, so `#root` can go `inert`. It renders a tap blocker, a spotlight and the sheet.
  - **Loading: plain `import()` with `.catch`, not `React.lazy`.** The app has no error boundary, so a failed chunk (offline, or a stale chunk name after a deploy) would blank Home, where logging lives. On failure nothing happens and Home stays usable.
  - **Spotlight:** one fixed element sized to the target's rect, using `box-shadow: 0 0 0 100vmax` for the dim and a `--c-accent` ring so it also reads in dark themes. Sheet colours are `--c-bg`/`--c-text`, so it follows the Telegram theme with no new palette.
  - **Targets:** `data-tour="today|stats|asanas|moon|settings"` on existing elements. The target is measured live (scroll, resize, and a `ResizeObserver` on `body`, rAF-throttled).
  - **Absent targets:** the tour waits for `useDays` and `useMoonDays` to settle (same cache keys, no new request), then keeps only the steps whose target exists, so the Today card on a load error or a moon card with no data simply drops out and the count stays honest. A target lost mid-tour shows its text with no spotlight. No targets at all: exit silently. No target depends on the zone, so "no zone yet" changes nothing.
  - **Below the fold:** `scrollIntoView({ block: "start" })` with a `scroll-margin-top`. The sheet is pinned to the bottom (`--tg-viewport-stable-height`, `env(safe-area-inset-bottom)`) and flips to the top when it would cover the target's upper part. Two positions, no popper maths, and a Today card taller than the screen still works.
  - **Back:** `useBackButton(exit)`. Tour is the newest layer, so it closes first, also over a dirty diary draft (Q68), which stays intact. The sheet's Done covers clients without Back.
  - **App wiring:** `App` holds the loaded component. The `settings` callback also closes the tour, so Telegram's ⋯ Settings item can't leave it half-open and restarting on return. `Settings` gets an `onTour` prop.
  - **TravelPrompt:** it hides the offer. A tour started from Settings just leaves it dimmed underneath; measuring live absorbs the layout.
  - **Accessibility:** `role="dialog"`, `aria-modal`, `aria-labelledby/-describedby`; focus moves to the step text (`tabindex=-1`) on each step, and Tab is kept inside the sheet; Esc exits, ←/→ change step; focus returns to the Home heading on exit. Reduced motion: instant scroll, no transition.

## 4. Migration and ops
- **Migration:** none.
- **Ops:** no new command. One optional ☁️ step: `command-remind` changed (owner decision 8), so the Telegram command menu keeps "Daily practice reminder" until `tools/telegram/set_webhook.py` runs; do it together with Q64. Deploy as usual. Optional owner action, no cloud: one line in the beta group ("/help → 🧭 Quick tour").

## 5. Cross-cutting checks
- **Time zones:** the tour shows no dates or times, so it needs no zone label. Done back to `/start` keeps UI-01's provisional-zone behaviour.
- **Privacy:** no new data. `onboard.tour` is one boolean-like flag, cleared by ST-09 delete, and nothing goes in the export. 🌸 per §2.
- **i18n:** all strings in `bot.ftl`/`app.ftl`, en and ru, under the existing parity tests. `tour-progress` numbers go through Fluent. Long RU text must fit a 320 px sheet.
- **Responsiveness:** see §7. Layering is unaffected: no new imports outside the adapters.

## 6. Test plan
- **Domain, use case, API contract:** nothing new. OpenAPI unchanged, so the contract check stays green.
- **Bot handler** (`tests/bots/test_tour_bot.py`, through the webhook like `test_start_bot.py`):
  - `/help` keeps its text, apart from the reminder line (owner decision 8), and has the button; `/start` has `[🧭 Quick tour]` as its last row, and the 7 statuses, `📅 Another day` and the language/app row are unchanged (`test_start_bot.py:110` moves to `rows[-2]`).
  - A status tap from `/start` still edits in place.
  - `q1:1:h` … `q1:5:h` edit in place (not send) with the right text and buttons in EN and RU: no Back on step 1, Next absent and app button on step 5, app button absent without `miniapp_url`.
  - Done from `s` renders the `/start` grid with ✓ on today's status; Done from `h` renders the help text.
  - A too-high `n` clamps; forged `q1:` data only answers; every value ≤ 64 bytes.
  - A step tap makes no storage call beyond the middleware's lookup.
  - No `tour-*` string in either locale contains 🌸 or the ladies' holiday wording, and none contains a word from `_AVOID` (test_i18n.py) or streak/missed/skipped/«серия» (not `_AVOID_COUNT`: RU «год» would match «сегодня»); ftl key parity.
- **Mini App (Vitest):**
  - Offer: hidden on a fresh device with the first-log hint showing, and never shown with it; shown after a log on the next Home mount, not mid-session on the same mount; shown on first open to someone with days logged in the bot; hidden while `travelPending`; Not now and Show me both persist; hidden when storage is blocked.
  - Tour: walks 5 steps forward and back; drops a step with no target and shows "1 of 4"; centres text when a target vanishes; `useBackButton` exit is called and the newest layer wins over a dirty diary draft; Esc and arrow keys work; focus moves and returns; `#root` is inert while open and restored after; reduced motion uses instant scroll; a rejected `import()` leaves Home rendered; ⋯ Settings closes the tour; the Settings row starts it on Home.
  - ST-09 delete clears the flag (existing test covers `localStorage.clear`).
  - `npm run build && npm run check:bundle`.
- **Architecture:** import-linter unchanged.
- **Owner, on a phone after deploy from `main`:** RU at narrow width, dark and light themes, iOS and Android, a Today card expanded by a logged practice, the last step's target at the page end.

## 7. Performance targets
- **Bot:** step tap = the middleware's 1 SELECT + pure rendering, 0 extra statements, answer first, webhook-reply edit; < 300 ms p50 warm. Done to `/help`: the same. Done to `/start`: the same statements as `/start` itself. `/start` and `/help` gain no statements. A double tap re-sends the same edit, as on every other screen.
- **Mini App:** 0 extra requests. Initial JS is estimated at +1.5 KB gzip, mostly the strings (`.ftl` files are in the entry chunk, both locales), so ~129 KB of the 150 budget. Tour chunk estimated at 2–3 KB gzip, fetched only on tap. CSS must stay under its 10 KB budget. Estimates, to be measured in the build. The offer's condition reads local data and the already-loaded days.

## 8. Open questions for the owner (recommendations)
1. **Bot offer:** a permanent `[🧭 Quick tour]` row on `/start`, plus `/help`, with no flag? It costs one quiet button forever on a message people also use as home. Hiding it after use would need a column and would end UI-01's "same for everyone". Recommended: yes, keep it stateless.
2. **Mini App memory:** device-local `onboard.tour`, no migration, accepting one extra offer on a second device or after Telegram clears storage? Recommended: yes. A server column is easy to add later if beta feedback asks for it.
3. **Offer timing:** never before the first log, and only when Home mounts (a newcomer sees it on the next visit to Home)? The alternative is offering at first open, which would compete with logging and the first-log hint. Recommended: as stated.
4. **Existing beta users:** the Mini App offer reaches them once on their next open with no code for them specifically. Bot-only people see the button on `/start` and `/help`, with no push, plus an optional line from you in the beta group? Recommended: yes. A broadcast would be the first non-reminder push, and that isn't worth it for a tour.
5. **🌸:** not mentioned in either tour, for the reasons in §2? The alternative is one neutral privacy line on the logging step. Recommended: not mentioned, confirmed by ashtanga-expert.
6. **Coach-mark reach:** Home only, targets not tappable, the Settings step describing what's inside? The alternative is walking into Stats and Settings, which adds navigation and loading states for little gain. Recommended: Home only.
7. **Copy ⚑:** the §2 drafts, including the name ("Quick tour" / «🧭 Знакомство», chosen by the owner 2026-11-06), go to ux-writer and ashtanga-expert before release? Recommended: yes.

## Amendment 2026-11-11: teachers and shalas

The tour was written before Phase 3. Owner decision (2026-11-11): add steps, no tour by role.

- **Bot:** six steps. New step 5, `tour-links` "👥 Teachers and shalas" (a link or QR code from a teacher or a shala, `/teachers`, `/schedule`, inviting students), between `tour-asanas` and `tour-app`. `tour-asanas` says a teacher can mark the asana too; `tour-app` says the guide is under `/help`. Callback data is unchanged (`q1:<n>:<origin>`); an old keyboard's step 5 now shows the new step, and a step past the end still shows the last one.
- **Mini App:** two more coach-marks, `tour-students` on the "My students" row and `tour-schedule` on the "My schedule" row. Those rows exist only for people who have students or are in a shala, so the existing rule (steps without a target drop out) keeps the count honest: most people still see five steps, a teacher in a shala sees seven. `tour-settings` names teachers, students and shalas.
- **Not changed:** no step for staff work (classes, attendance, announcements); the guide covers it. 🌸 stays unnamed.

