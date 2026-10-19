# UI-01 (Phase 1 slice): onboarding, `/start` → greeting → "How was today?" in one message

- Status: **accepted** (owner: all yes, 2026-10-19) · Date: 2026-10-19
- Requirements: **UI-01** (`/start` → greeting → "Log today's practice?" right away; language from Telegram `language_code`). Touches ID-06 (language/zone), PR-01 (day picker), PR-10 (reminder offer). Roadmap: "Onboarding: `/start` → language → 'log today?'". Budget: < 300 ms p50 per tap (warm).
- Related: ADR-0008 (stateless callbacks), 0012 (webhook reply), 0005 (time), 0021 (explicit choices). Earlier slice: `UI-01-telegram-webhook.md`. **No new ADR** (no lasting decision: no schema, no API).

## 1. Scope
**In:** `/start` becomes one message: the greeting, today's status picker inline, a one-button language switch and "Open the app"; an "Open the app" row on the saved screens while the zone is unknown; a grouped `/help`; a small first-log hint on the Mini App Home.
**Out:** the quick tour (UI-02, Phase 2), deep-link handling (ID-04, Phase 3: payloads are ignored now), asking for the time zone during onboarding, an "onboarded" flag or any migration, new API endpoints, a "today is a moon day" line on `/start`.

## 2. Flows and copy
- **New or returning person sends `/start`** (with or without a payload) → **one message**, the webhook reply (ADR-0012). It is the same for everyone (stateless, §3):
  ```
  Namaste 🙏
  I'm Tristhana, your Ashtanga practice companion. Glad you're here.

  Today, Mon, Oct 19
  How was today? Practice or rest, both go in your log.
  [🧘 Practiced]
  [😌 Rest day] [🌙 Moon day]
  [🌸 Ladies' holiday] [🤒 Sick / injury]
  [✈️ Travel] [🌱 No practice]
  [📅 Another day]
  [🗣 Русский] [Open the app]
  ```
  The grid is PR-01's (`d1:s:<date>:<code>`, absolute date, ✓ on today's status if it's already logged, so a returning `/start` works as a home screen). **First log = 2 taps** (Start, a status). A status tap **edits this message in place** into the existing saved screen (or, for 🧘, the PR-02 details screen with its PR-10 reminder offer). This replaces the 2026-10-18 "Log today opens a new message" row (Q1). The old `d1:t` handler stays for greetings already in chat history.
- **Language:** no confirm step and no extra line. The last row has **one button for the other language**, labelled in its own language (`[🗣 Русский]` on the EN message, `[🗣 English]` on the RU one). A tap → `o1:l:ru` → `UpdateProfile(locale="ru")` (explicit, `locale_custom = true`, ADR-0021) → the same message is re-rendered in place in the new language. "As in Telegram" stays in `/settings`. Telegram's `language_code` sets the first locale as before (ru/be/kk/ky → RU, else EN).
- **Next steps after the first log:** no new text. While the account's zone is **unknown** (bot-only person), the saved and details screens get a last row `[Open the app]` (web_app), right under the existing `log-zone-hint` ("open the app once so I know your time zone"). Opening it records the device zone silently (ID-01) and shows stats. Once the zone is known the row disappears. The reminder offer on 🧘 (PR-10) is unchanged; `/help` is in the menu.
- **Deep links:** `/start t_abc` behaves exactly like `/start`. The payload is not parsed, stored or logged. The `t_` prefix is reserved for ID-04 teacher invites, which will add a `CommandStart(deep_link=True)` handler in front of this one.
- **Mini App first open:** Home shows `home-first-hint` under the subtitle while today is unlogged **and** this device has never saved a day (`localStorage onboard.logged`, set on the first successful save). It uses the Today card's data, so there's no extra request.
- **`/help`** (grouped, one screen):
  ```
  I'm Tristhana, a companion for your Ashtanga practice.
  📝 /log: today or an earlier day · /remind: a daily one-tap check-in
  🌙 /moon: upcoming moon days and reminders
  ⚙️ /settings: language, time zone, reminders
  📊 Your practice log and stats are in the app: the button next to the message field.
  ```
  The command menu stays as it is (no `set_webhook` run needed).
- **Copy** (RU «ты», no gendered past tense, ⚑ ux-writer + ashtanga-expert for tone). `bot.ftl`: `start-greeting` stays as it is. New `start-prompt` "{ $day }\nHow was today? Practice or rest, both go in your log." / «{ $day }\nКак прошёл день? Практика или отдых: в журнал идёт всё.»; `start-switch-language` "🗣 { $language }" (`$language` = the existing `language-en` / `language-ru`, the same in both files). `help-text` is rewritten as above / RU: «Я Тристхана, спутник твоей практики аштанги. / 📝 /log: сегодня или прошедший день · /remind: ежедневный вопрос с ответом в одно нажатие / 🌙 /moon: ближайшие лунные дни и напоминания / ⚙️ /settings: язык, часовой пояс, напоминания / 📊 Журнал практики и статистика: в приложении, кнопка рядом с полем ввода.» `app.ftl`: `home-first-hint` "Start by noting today: practice or rest." / «Начни с сегодняшнего дня: практика или отдых?».

## 3. Design
- **Domain / application:** no changes. `GetDays.today` (provisional zone when unknown), `SetDayStatus` and `UpdateProfile` (ID-06) are reused as they are. No new port.
- **State: none.** The `/start` message is the same for new and returning people, the language button always offers the other language, and the "Open the app" row depends only on `account.timezone is None`. `EnsureAccount` is unchanged, there's no "onboarded" flag and no migration.
- **Bot:** new `bots/telegram/start.py` (moved out of `router.py`): `StartScreens.start(principal) -> Screen` = greeting + `DayScreens.status(principal, None)` text and grid + the language/app row. `on_start` uses `CommandStart()` (any payload). Callback prefix **`o1:`**: `o1:l:en` / `o1:l:ru` (7 bytes); malformed or other-version data → answer only. `DayScreens.saved_screen` and `PracticeScreens.details` append the app row when `not zone_known` and `miniapp_url` is set (one helper in `screens.py`).
- **Round trips:** `/start` = middleware (1 SELECT) + today's status (1). Language tap = middleware + UPDATE … RETURNING + today's status (callback answered in parallel). Status taps are unchanged.
- **API:** none. **Mini App:** `Home.tsx` gets a `firstHint` prop from the Today card's state, plus a `markLogged()` call in the Today save success path (< 0.2 KB).

## 4. Ops
None ☁️. The command menu is unchanged. Deploy as usual.

## 5. Migration
None.

## 6. Cross-cutting checks
- **Time zones:** onboarding never asks for a zone. "Today" comes from the provisional zone (Moscow for ru, UTC for en; never stored or used for reminders, 06 Time Zones), and logging uses `latest_loggable` (Kiritimati), so a real "today" is never refused. **Midnight edge:** near local midnight the provisional "Today" can carry the neighbouring date. An EN person in the Americas sees tomorrow's date in the evening (New York from 20:00 EDT); an EN person in Asia sees yesterday's in the early morning (Bangkok until 07:00); a RU person east of Moscow sees yesterday's just after midnight (Almaty until 02:00). The date is printed in the prompt, `📅 Another day` is one tap away, and the saved screen shows the zone hint plus the "Open the app" row, which fixes the zone for the future. Already-logged days keep their date. Reminders still ask for a zone on first need (`moon-zone-needed`, the remind flow), as today.
- **Privacy:** deep-link payloads are never logged or stored. 🌸 on the onboarding grid follows PR-01 (sealed reason, "Rest" for others, `log-private-note`). No new data.
- **i18n:** every string is in `bot.ftl` / `app.ftl` with en/ru parity. Language names appear in their own language. The re-render after a language tap uses the new locale.
- **Responsiveness:** one message, edited in place, webhook reply, ≤ 2 statements per interaction, no new imports. The Mini App hint costs no request.

## 7. Test plan
- **Domain / use case:** nothing new (existing `UpdateProfile` and `SetDayStatus` tests cover them). Add a check that `o1:l:*` sets `locale_custom`.
- **Bot handler:** `/start` renders the greeting, today's label, 7 status buttons carrying today's date, `📅 Another day`, the other-language button and "Open the app" (and none without `miniapp_url`); ✓ on an already-logged status; RU and EN variants; `/start t_abc` and `/start garbage` behave the same; `o1:l:ru` edits in place in RU and leaves the zone alone; forged `o1:` data only answers; a status tap from `/start` edits (not sends); saved and details screens show the app row only while the zone is unknown; old `d1:t` still opens a new message; every `o1:` value ≤ 64 bytes; `help-text` lists /log, /remind, /moon, /settings; ftl key parity.
- **API contract:** unchanged OpenAPI (contract check stays green).
- **Mini App (Vitest):** the hint shows while today is unlogged on a fresh device, hides after a save, and stays hidden on the next open; no hint once today is logged.
- **Architecture:** import-linter (aiogram only in `bots`).

## 8. Open questions for the owner (recommendations)
1. **One message:** `/start` shows the greeting **and** today's picker; a status tap edits it in place (2 taps to the first log), replacing the 2026-10-18 "new message" rule? Recommended: yes. It's the fastest path, and the menu button and the app row still reach the app.
2. **Language:** no confirm step, just one `[🗣 Русский]` / `[🗣 English]` button on `/start`, which sets the language explicitly? Recommended: yes. Telegram's language is usually right, and when it's wrong (e.g. Russian speakers with English Telegram) it's one visible tap.
3. **Time zone:** don't ask during onboarding; show "Open the app" under saved days while it's unknown; accept the provisional-zone midnight edge for beta? Recommended: yes. Asking up front adds a step for every tester, while the edge only touches a few late-evening logs.
4. **Returning `/start`:** the same message (greeting + today's picker with ✓), with no "onboarded" flag or migration? Recommended: yes. It's stateless and doubles as a home screen.
5. **Deep links:** ignore every payload now and reserve `t_` for ID-04, with payloads never logged? Recommended: yes.
6. **Mini App:** the one-line first-log hint (device-local)? And hide Home's Phase 0 "Check connection" main button in production, since it's the most prominent control a newcomer sees? Recommended: yes to both. Hiding it is a two-line change; dev keeps it.
7. **`/help`:** grouped as in §2, with the command menu unchanged (no `set_webhook` run)? Recommended: yes.
8. **Copy ⚑:** `start-prompt` ("both go in your log" / «в журнал идёт всё»), `home-first-hint`, and the new help lines go to ux-writer and ashtanga-expert before release? Recommended: yes.

## 9. Implementation notes and review fixes (2026-10-19)
- **Copy (ux-writer + ashtanga-expert; overrides §2):** RU `start-prompt` «Как прошёл день? Практика или отдых — в журнал идёт и то, и другое.»; RU `/remind` help line «ежедневная отметка в одно нажатие»; the 📊 help line reads "…live in the app (the button next to the message field)" / «… — в приложении (кнопка рядом с полем ввода)»; RU `home-first-hint` «Для начала отметь сегодня: практика или отдых.» (no nudge to practise). The expert approved showing 🌸 in the first grid (same as /log; disclosure only on a tap).
- **Mini App hint (overrides §3):** rendered inside the Today card, not under the Home subtitle; shown only while today is unlogged, nothing is logged in the window (people who already log in the bot never see it) and this device hasn't saved a day.
- **"Check connection"** shows in production only after the long-press that reveals server details; always in dev.
- **Review fixes:** the other-language button is derived from `LOCALES` (a third language can't break /start); the screen class takes an `ExternalProfile`, not an aiogram type; legacy `d1:t` comments updated; tests added for the details-screen app row, a forged `o1:` tap, a RU `/start`, garbage payloads, the language tap leaving zone and name alone, and the hint (isolated, persists, hidden for existing loggers).
- **Known edge:** for a person whose zone is unknown, tapping 🗣 near midnight can move the shown "Today" (the provisional zone follows the language: Moscow for RU, UTC for EN). The date is printed in the prompt; documented in 06 Time Zones.
