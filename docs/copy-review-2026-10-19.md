# RU/EN copy review: Phase 1, before the private beta (2026-10-19)

Scope: every key in
`backend/src/tristhana/infrastructure/i18n/locales/{en,ru}/bot.ftl` and
`miniapp/src/locales/{en,ru}/app.ftl`, plus the open copy questions Q15, Q29, Q30, Q33, Q36 and Q37.
**No locale file was edited.** Answer "all yes" or by number (C1, C2, …).

"Tests" column: the test files that assert the exact current string. Each one must be updated together with the `.ftl` change. "—" means no test asserts it.

## 1. Summary

The copy is in good shape. The tone is warm and calm, and rest is framed as practice ("Rest is part of the practice" / «Отдых — тоже часть практики»). RU uses «ты» everywhere. I found **no gendered past tense** (every RU past-tense verb has an impersonal subject: «прошёл день», «закончилась практика»). Russian plurals all go through Fluent and resolve correctly. The bot and the Mini App use the same terms for statuses, series, moon phases, "in a row"/«подряд» and settings. Quotes (“” / «») and the ellipsis (…) are consistent. Both locales have the same keys.

There are five real errors:
- the double period «окт..» (Q29)
- two RU city-name case errors that show up for cities like «Москва», «Астана» and «Рига»
- mixed UK/US spelling in EN
- one ambiguous EN offset phrase ("a week and a day before" can read as 8 days)

The rest is polish:
- EN uses log/mark/note interchangeably, while RU consistently uses «отметить»
- a few buttons are too long for a phone
- one RU sentence frames moon days negatively («не практикуют»)
- one 🕒 that should be 🕐
- the open questions

## 2. Must fix

| # | Key | File | Current EN | Current RU | Proposed EN | Proposed RU | Reason | Tests |
|---|---|---|---|---|---|---|---|---|
| C1 | `log-cleared` | bot | Cleared: { $day }. | Отметка убрана: { $day }. | Cleared. | Отметка убрана. | RU renders «…18 окт..» (Babel's date already ends with a period; Q29). The day is also repeated: the same message continues with `log-prompt`, which starts with the same `{ $day }` line. Fluent ignores the now-unused `$day`, so no code change is needed. | `backend/tests/bots/test_days_bot.py:172` (`startswith("Cleared: Today, ")`) |
| C2 | `zone-travel`, `zone-travel-switch`, `zone-travel-keep` | app | (EN unchanged) | Телефон живёт по времени { $device }, а напоминания — по { $current }. · Перейти на { $city } · Оставить { $city } | (unchanged) | Время на телефоне: { $device }. Напоминания приходят по времени: { $current }. · Перейти: { $city } · Оставить: { $city } | Broken case: city names arrive in the nominative, so the current copy renders «по Москва (UTC+3)», «Перейти на Москва» and «Оставить Астана». Label style with a colon avoids declension entirely. | — (Settings.test.tsx asserts EN only) |
| C3 | `moon-calc-note` | bot + app | (EN unchanged) | Даты рассчитаны для 📍 { $city } (лунный день на восходе). Календарь твоей шалы может отличаться на день, ориентируйся на своего учителя. | (unchanged) | Даты рассчитаны по городу 📍 { $city } (лунный день на восходе). Календарь твоей шалы может отличаться на день: ориентируйся на своего учителя. | «для 📍 Майсур/Москва» is ungrammatical (needs the genitive). The apposition «по городу Москва» is correct for any name. This also fixes the comma splice. Shown on every /moon screen. | — |
| C4 | `length-pick-range` (bot), `stats-legend-away` (app) | bot, app | What did you practise? · Sick or travelling | (RU unchanged) | What did you practice? · Sick or traveling | (unchanged) | Mixed UK/US spelling. Every other EN string uses US spelling ("Practiced", "practiced"). | — |
| C5 | `moon-offsets` | bot | 7, 3 and 1 day · a week and a day · 7 and 3 days · 3 days and a day · a week · 3 days · a day | (RU unchanged) | 7, 3 and 1 day · 7 and 1 day · 7 and 3 days · 3 and 1 day · 7 days · 3 days · 1 day | (unchanged) | "Reminders: a week and a day before" reads as *8 days before*. "3 days and a day" is awkward. Numerals match `[731]` and the chips ("7 days"). RU «за неделю и за день» is unambiguous because «за» is repeated, so it stays. | `backend/tests/bots/test_moon_bot.py:146` ("a week and a day before, at 19:00 …") |

## 3. Should improve

| # | Key | File | Current EN | Current RU | Proposed EN | Proposed RU | Reason | Tests |
|---|---|---|---|---|---|---|---|---|
| C6 | `start-prompt` | bot | { $day }⏎How was today? Practice or rest, both go in your log. | { $day }⏎Как прошёл день? Практика или отдых — в журнал идёт и то, и другое. | { $day }⏎Practice or rest? Both go in your log. | { $day }⏎Практика или отдых? В журнал идёт и то, и другое. | Q36. The line above already says "Today, Sun, Oct 19", so the question doesn't need a time word. That makes it read naturally at 07:00 and at 21:00, and it is shorter on the first screen. | `backend/tests/bots/test_start_bot.py:106` |
| C7 | `error-temporary` | bot | Sorry, I've hit a small hiccup on my side. Please try again in a minute 🙏 | Прости, у меня небольшая заминка. Попробуй ещё раз через минуту 🙏 | Sorry, I've hit a small hiccup on my side. Please try again in a minute. | Прости, у меня небольшая заминка. Попробуй ещё раз через минуту. | Q15. 🙏 is our greeting/gratitude mark (Namaste, "Practice done 🙏"). On an error it can read as pleading. The Mini App's error lines have no emoji either. | — |
| C8 | `help-text` (lines 2–3) | bot | 📝 /log: today or an earlier day · /remind: a daily one-tap check-in | 📝 /log: сегодня или прошедший день · /remind: ежедневная отметка в одно нажатие | 📝 /log: today or an earlier day⏎🔔 /remind: daily practice reminder | 📝 /log: сегодня или прошедший день⏎🔔 /remind: ежедневное напоминание о практике | /remind was the only command without its own line and emoji. "check-in"/«отметка» was a third name for the same feature, which is called "practice reminder" in `command-remind`, `remind-card-title` and `remind-practice-link`. The RU line also wrapped on phones. | — |
| C9 | `moon-reminder-intro` | bot | (EN unchanged) | В аштанге в полнолуние и новолуние традиционно не практикуют. Я напомню { $offsets }, изменить можно одной кнопкой ниже. | (unchanged) | В аштанге в полнолуние и новолуние традиционно отдыхают. Я напомню { $offsets }: изменить можно одной кнопкой ниже. | Tone. «не практикуют» frames the day as a prohibition. EN says "we traditionally rest", so the RU now matches it. | — |
| C10 | `preset-short` (+ `length-pick`) | bot + app | ☀️ Short: sun salutations, standing, finishing · (length-pick) Where did your practice end? | ☀️ Короткая: приветствия солнцу, стоячие, завершающие · Где закончилась практика? | ☀️ Short (no series) · Where did your practice end?⏎☀️ Short: Surya Namaskara, standing and finishing. | ☀️ Короткая (без серии) · Где закончилась практика?⏎☀️ Короткая: Сурья Намаскар, стоячие и завершающие. | The button is 45/52 characters (limit ~24), so Telegram truncates it on a phone. Q20 was checked before the presets existed. The explanation moves to the prompt text, and the Mini App chip uses the short label. The catalog spells the opening «Сурья Намаскар», not «приветствия солнцу». ⚑ Confirm "(no series)" with ashtanga-expert. | `backend/tests/bots/test_practice_bot.py:143` |
| C11 | `settings-open-app` | bot | ⚙️ Name, quiet hours: in the app | ⚙️ Имя, тихие часы: в приложении | ⚙️ More in the app | ⚙️ Ещё в приложении | Q33. 32 characters (limit ~24). The settings text above already lists the quiet-hours line. | — |
| C12 | `home-first-hint`, `stats-legend-none`, `stats-unlogged`, `stats-month-empty` | app | Start by noting today: practice or rest. · Not marked · { $n } unmarked day(s): tap a day to add it · Nothing marked this month yet. Days you mark will show up here. | (RU unchanged: «отметить/отметка» is already consistent) | Start by logging today: practice or rest. · Not logged · `[one]` { $n } day not logged: tap a day to add it / `*[other]` { $n } days not logged: tap a day to add it · Nothing logged this month yet. Days you log will show up here. | (unchanged) | EN uses three verbs (log/mark/note) for one action. The bot, /log and "already logged" all say *log*, and the key itself is `stats-unlogged`. | `miniapp/src/screens/TodayCard.test.tsx:162`; `miniapp/src/screens/stats/Stats.test.tsx:166, 175, 238` |
| C13 | `stats-consistency-hint` | app | Unmarked days aren't counted. Rest, moon, sick and travel days keep the run going: rest is part of the practice. | (RU unchanged) | Days you haven't logged are left out. Rest, moon, sick and travel days don't reset the count: rest is part of the practice. | (unchanged) | Q30. "run" can read as jogging and is the only place it appears. This mirrors the RU «не сбивают счёт» and uses the C12 verb. | — |
| C14 | `moon-use-city-zone` | bot | 🕒 Time zone: 📍 { $city } | 🕒 Часовой пояс: 📍 { $city } | 🕐 Time zone: 📍 { $city } | 🕐 Часовой пояс: 📍 { $city } | Every other time-zone string uses 🕐. | `backend/tests/bots/test_moon_bot.py:141` |
| C15 | `remind-status-on`, `moon-reminders-on` | bot | 🔔 Practice reminder: { $days }, at { $time } · 🔔 Reminders: { $offsets } before, at { $time } | 🔔 Напоминание о практике: { $days }, в { $time } · 🔔 Напоминания: { $offsets }, в { $time } | 🔔 Practice reminder: { $days } at { $time } · 🔔 Reminders: { $offsets } before at { $time } | 🔔 Напоминание о практике: { $days } в { $time } · 🔔 Напоминания: { $offsets } в { $time } | Q29. With a weekday list the comma blends in: "Mon, Wed, at 10:00". Dropping it in both lines keeps them parallel. | `backend/tests/bots/test_remind_bot.py:153, 172, 221`; `backend/tests/bots/test_moon_bot.py:131, 146` |
| C16 | `remind-practice` (code, not copy) | bot | 🌿 Mon, Oct 19: practice or rest? … | 🌿 пн, 19 окт.: практика или отдых? … | 🌿 Today, Mon, Oct 19: practice or rest? … | 🌿 Сегодня, пн, 19 окт.: практика или отдых? … | The RU message starts lowercase. `remind.py:54` passes a bare `DateArg`; pass the `day-label` result (as the other screens do). The `.ftl` strings stay the same. | — (check `test_remind_bot.py` after the code change) |
| C17 | `series-name`, `series-lower`, `series-half` (n = 4) | bot + app | — | Четвертая · четвертая · четвертой | — | Четвёртая · четвёртая · четвёртой | Every other RU string writes ё («прошёл», «ещё», «счёт», «Объём»). The "no ё" decision applies to asana transliteration only. | — |
| C18 | `remind-off-note`, `moon-reminder-off` | bot | …You can turn them on any time in /remind. · …You can turn them on again in /moon. | (RU already parallel: «Включить снова можно в …») | …You can turn them back on in /remind. · …You can turn them back on in /moon. | (unchanged) | Two phrasings for the same message, while the RU is already parallel. Low priority. | `backend/tests/bots/test_remind_bot.py:300` |
| C19 | `stats-online` | app | 🌐 online: { $n } | 🌐 онлайн: { $n } | 🌐 Online: { $n } | 🌐 Онлайн: { $n } | Appears as its own list item. Capitalised everywhere else (`practice-online`). | — |
| C20 | `log-date-too-early` | bot | I keep days from the year 2000 on. | (RU unchanged) | I keep days from 2000 onwards. | (unchanged) | "from the year 2000 on" reads translated. Low priority. | — |

## 4. Keep as is (considered, rejected)

- **Gendered past tense, «ты», plurals:** checked every RU key. No «ты сделал(а)» constructions and no «вы». The RU plural selectors use `*[other]` in some keys (`moon-in-days`, `moon-offset`, `settings-cap`) and `*[many]` in others (`practice-days`, `stats-*`). Both resolve correctly because the default catches `many`. A future pass could standardise on `*[many]`, but nothing is broken.
- **"in a row"/«подряд»:** used consistently, with no "streak"/«серия» anywhere. The RU `stats-consistency` plural on `$y` («из 1 дня / 2 дней») is correct. EN has no plural on `$y`, but `y ≥ 2` whenever the line is shown, so it can't render "of 1 days".
- **`status-practiced` "🧘 Practiced" vs «🧘 Практика»:** the EN participle and the RU noun are each the natural form. Decided in PR-01.
- **«✈️ В дороге» (status) vs «поездка» (stats legend/hint):** each fits its spot (a state vs a category).
- **EN "📏 Length" next to "⏱ Duration":** I considered "How far". The emojis and the follow-up question ("Where did your practice end?") disambiguate. RU «Объём практики» is clear.
- **`remind-same` "✅ Practiced, same as last time" (30 characters):** over the limit, but it sits alone on a full-width row and the wording was decided in PR-10. ✅ (reminder) vs 🔁 (details screen) was also decided.
- **`preset-half-primary` «½ первой → Навасана»:** clipped, but it is how practitioners say it, and it fits on the button.
- **`log-private-note` / `settings-privacy-ladies` "Others see “Rest day”":** future-proof for Phase 3. 🌸 days are named only on the user's own screens, and the stats toggle "Show 🌸 days" stays discreet.
- **"phone" vs "device":** "phone" is the main case and reads warmer («телефон» vs «устройство»). `stats-show-ladies` says "this device" deliberately, because it is a device-local setting.
- **`practice-done` «Практика сделана 🙏»:** common practitioner phrasing.
- **`log-clear` / `today-clear` EN "Clear":** it sits next to the ✓-marked status, so the meaning is clear in context.
- **Comment «ее» (app.ftl RU line 13):** a comment, not user-facing. Fix whenever the file is next touched.

## 5. Open questions: recommendations

- **Q15 (🙏 in `error-temporary`):** drop it, see **C7**. Keep 🙏 in `fallback-text`, which is a friendly redirect, not an apology.
- **Q29:**
  - `command-remind`: keep **"Daily practice reminder"**. "Check-in" would add a new term; C8 aligns /help to it.
  - RU «🌙 Лунные напоминания»: **keep**. It is short (21 characters), paired on the same screen with «🧘 Напоминание о практике», and clear in context. «Напоминания о лунных днях» doesn't fit on a button.
  - EN comma in "Mon, Wed, at 10:00": drop it, see **C15**.
  - «окт..»: fix, see **C1**.
- **Q30:**
  - Keep "This month: no practice yet" **hidden**. An empty month already speaks for itself, and a zero line can feel like a tally.
  - Keep "practice on 0 of 2 days" **hidden** for the same reason.
  - The RU moon-marker legend «Полнолуние или новолуние · 📍 Майсур» (~35 characters): **keep**. It is a legend line, not a button, so wrapping on a narrow phone is fine. Shortening it to «Лунные дни» would clash with the logged status «🌙 Лунный день (отдых)».
  - "run": replace it, see **C13**.
- **Q33:**
  - "As in Telegram" capitalised after "Language:": **keep**. Capitalising a value after a colon is normal in a settings line.
  - Truncation: if "✓ As in Telegram" truncates in the 3-button row on a narrow phone, give it its own row (layout change, not copy). "Auto" is less clear.
  - Bot button "⚙️ Name, quiet hours: in the app": shorten it, see **C11**.
  - Quiet-hours line without a zone label: **keep**. The zone is on the line directly above, and repeating it would push the key action down.
  - Privacy line and name hint for Phase 3: add a Phase 3 task to rewrite `settings-privacy-sharing`, `log-private-note`, `today-private-note` and `settings-privacy-ladies` once teachers can see anything.
- **Q36 ("How was today?"):** use the time-neutral wording, see **C6**. It reads right both in the morning and in the evening.
- **Q37 (📱 on "Open the app"):** **no 📱**. The Mini App also opens on desktop Telegram, where 📱 is wrong, and the button already stands out next to the 🗣 language button. If you want an emoji, 📊 would match "📊 My practice", but I recommend leaving it plain.
