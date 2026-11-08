# SC-06: ICS calendar subscription (my classes + my moon days)

- Status: **accepted, built** (architect, 2026-11-08; owner accepted Q145–Q156 as recommended and the ashtanga-expert review on 2026-11-08, see §10; built + reviewed 2026-11-08, §11) · Size S, Phase 3
- Requirements: **SC-06** ("ICS calendar subscription (classes + moon days)"). Builds on SC-03 (`GetMySchedule`, `member_windows`, ADR-0035), SC-02 (`expand`, ADR-0034), MD-01/02/03 (stored `moon_day`, `moon_follow_of`, ADR-0019/0032), ADR-0016 (sealing), ST-09 (cascade delete, ADR-0027).
- Related: ADR-0005, 0008, 0015, 0016, 0034, 0035. New: **ADR-0036** (accepted): capability-URL feed, hashed + sealed token, expanded UTC instances, hand-written serializer.

## 1. Scope
**In:** one personal, read-only **subscription URL per account** that a calendar app (Google, Apple, Outlook) polls. It contains (a) the rows of **My schedule, filter All** (SC-03: every shala where I'm a member; 1:1 only where I'm staff), as expanded instances over a bounded window, and (b) **my own moon days** (effective calendar, MD-02) as all-day events. Turn on, show/copy, make a new link (rotate), turn off; on both surfaces. Offered to **everyone** (moon days alone are useful; Q146).
**Never in the feed:** anything from the log, diary, check-ins, rest periods, day off, 🌸, progression; other people's data beyond what members already see (staff names, Q106); a followed teacher's shalas I haven't joined (Q135); 1:1 class titles (Q150); my name or Telegram id.
**Out:** per-filter or per-shala feeds, public shala feeds, CalDAV / two-way sync, Google Calendar API push, VALARM reminders (Q155), shala 🌙 / day-off day markers (Q142, Q154), "I'm coming" (SC-04), attendance (SC-05).

## 2. Flows and screens
**Entry points:** Mini App My schedule footer card "📅 Add to calendar" + Settings card; bot `/schedule` row `[📅 Add to calendar]`, `/moon` row (same screen), `/settings` row. All open one **feed screen** (bot callback `c1:f:<a>`; Mini App sub-screen in the My schedule lazy chunk).

**Bot (plain text; answer first; edit in place; callback ≤ 12 bytes):**
```
📅 Calendar subscription
Your classes and moon days in Google, Apple or Outlook Calendar. It updates by itself (Google can take up to a day).
                                                   — off —
[📅 Create my link]                                  c1:f:n
                                                   — on —
https://…/ical/v1/Xy…43chars….ics                  (plain text: tap-to-copy / long-press)
🔒 Anyone with this link sees your schedule. Don't share it.
Last checked by a calendar: Sat 7 Nov               (or "Not used by a calendar yet")
[Add to Google Calendar]   → url button (https Google `cid=` link)
[Add to Apple / Outlook]   → url button (https …/subscribe → 302 webcal://)
[🔄 New link]  c1:f:r → confirm c1:f:R      [Turn off]  c1:f:x → confirm c1:f:X
```
- Telegram URL buttons and Mini App `openLink` accept only http(s), never `webcal://`. So: Google gets `https://calendar.google.com/calendar/r?cid=<webcal URL, encoded>`; Apple/Outlook get our `GET /ical/v1/{token}/subscribe` → **302** `Location: webcal://<host>/ical/v1/{token}.ics`, which iOS/macOS Safari hands to Calendar as a subscription (Q152). The https `.ics` URL is always shown for copy ("From URL" in Google, "Add subscription" on Apple, "Subscribe from web" in Outlook).
- Confirm screens: rotate "The old link stops working. Calendars that use it need the new one." · off "Your calendar apps will stop updating. They may keep the last copy until you remove the calendar."
- The link message stays in my own chat (like the ST-09 export); `feed-private` says so (Q151).

**Mini App:** the same states; `[Copy link]` (`navigator.clipboard`, haptic, "Copied"), Google and Apple/Outlook buttons via `openLink(https…)`, `[🔄 New link]` / `[Turn off]` with Telegram's native confirm popup. The URL is never put in `localStorage` or logs. 320 px: the URL wraps (`overflow-wrap:anywhere`), monospace hint style.

**Copy** (⚑ drafts, «ты», ux-writer polishes; reuse `moon-phase-long`, `class-type`, `time-label`, `day-label`, `schedule-covering-for`):

| Key | EN | RU |
|---|---|---|
| `feed-open` | 📅 Add to calendar | 📅 Добавить в календарь |
| `feed-title` / `feed-explain` | 📅 Calendar subscription / Your classes and moon days in Google, Apple or Outlook Calendar. It updates by itself (Google can take up to a day). | 📅 Подписка в календаре / Твои занятия и лунные дни в Google, Apple или Outlook Календаре. Обновляется само (в Google — до суток). |
| `feed-moon-only` | Join a shala to see its classes here too. | Когда вступишь в шалу, здесь появятся и её занятия. |
| `feed-create` / `feed-copy` / `feed-copied` | 📅 Create my link / Copy link / ✓ Copied | 📅 Создать ссылку / Скопировать ссылку / ✓ Скопировано |
| `feed-google` / `feed-apple` | Add to Google Calendar / Add to Apple / Outlook | Добавить в Google Календарь / Добавить в Apple / Outlook |
| `feed-private` | 🔒 Anyone with this link sees your schedule. Don't share it; if it got out, make a new one. | 🔒 По этой ссылке видно твоё расписание. Не пересылай её; если она попала к кому-то, создай новую. |
| `feed-checked` | `{ $day -> [none] Not used by a calendar yet *[other] Last checked by a calendar: { $day } }` | … «Календарь последний раз обновлялся: { $day }» / «Календарь ещё не подключён» |
| `feed-rotate` / `-confirm` | 🔄 New link / The old link stops working. Calendars that use it need the new one. | 🔄 Новая ссылка / Старая ссылка перестанет работать. В календаре нужно будет подписаться заново. |
| `feed-off` / `-confirm` / `-done` | Turn off / Your calendar apps will stop updating… / Turned off. | Отключить / Календарь перестанет обновляться… / Отключено. |
| `ics-calendar-name` | Tristhana: my schedule | Tristhana: моё расписание |
| `ics-class` | `{ $what } · { $teacher }`: `$what` = the class's own title if set, else `class-type` (expert item 4); 1:1 → type only (Q150). `$teacher` = whoever **teaches that date** (the substitute on a covered date; expert item 2) | same |
| `ics-moon` | SUMMARY `moon-phase-long` (no kshaya label); DESCRIPTION = the existing **`moon-calc-note` verbatim** ("Dates are calculated for 📍 { $city } (lunar day at sunrise). Your shala's calendar may differ by a day; follow your teacher.") | `moon-calc-note` verbatim («Даты рассчитаны по городу 📍 { $city } (лунный день на восходе). Календарь твоей шалы может отличаться на день: ориентируйся на своего учителя.»); no new moon wording (expert item 1) |
| `ics-desc-*` | shala · "Online" · class time `{ $time }` (when its offset differs from mine) · `schedule-covering-for` · "🔁 instead of { $day }" · "🌙 held on the moon day" · "↪ moved from { $day } { $time }" | … |

## 3. Domain, use cases, ports
- **Domain (pure)** `domain/calendar_feed.py`: `FeedWindow` constants (`CLASSES_BACK=14`, `CLASSES_AHEAD=56`, `MOON_BACK=30`, `MOON_AHEAD=365` days; `MAX_EVENTS=2000`, furthest-future dropped first, Q148); `FeedEvent(uid, summary, description, location, start: datetime|date, end, all_day)`; `uid_class(class_id, key) = f"{class_id}-{key:%Y%m%d}@tristhana"` (the ADR-0034 rule-date identity: a moved or swapped occurrence keeps its UID), `uid_moon(day, phase)`; `TOKEN_RE` (43 base64url chars).
- **Refactor, no behaviour change:** the per-window loop of `GetMySchedule` moves into `application/classes.py::_my_rows(found, zone, first, end, me, only)`; `GetMySchedule` and the feed both call it. `member_windows` gains `moon_end: date | None` (moon dates read over `[start, moon_end or end]`) and `MyWindows.my_moon_kinds: Mapping[date, MoonDayKind]` (the same scalar subquery aggregates `date, kind`; `my_moon` stays for SC-03).
- **Use cases** `application/calendar_feed.py`:
  - `GetFeedLink.execute(principal) -> FeedLink | None` · `CreateFeedLink.execute(principal) -> FeedLink` (create or rotate: always a new token, the old one dies in the same statement) · `RevokeFeedLink.execute(principal)` (idempotent). `FeedLink(token, created_at, fetched_on)`; policy `can_manage_calendar_feed(actor, owner)` = owner only.
  - `GetCalendarFeed.execute(token: str) -> Feed | None`: malformed → None (no DB); `feeds.account_by_token(sha256(token), today_utc)` → `Account | None` (None → 404); `principal = Principal(account)` (the token **is** the authentication; membership policies still apply per window); `member_windows(me, first−2, end+2, moon_city=moon_follow_of(...).city.slug, moon_end=today+365)`; `_my_rows(..., Only.ALL)`; **drop every cancelled row** (moon, closure and staff cancellations alike, incl. kept swap originals; Q147, owner); SUMMARY names the date's actual teacher, DESCRIPTION adds `schedule-covering-for` ("Dana (for Anna)") on a covered date; events built with `Translator` in `account.locale` (titles, descriptions; the class's wall-clock label only when its offset differs from the account zone at that instant); moon events from `my_moon_kinds`. Returns `Feed(name, stamp=link.created_at, events)`.
- **Ports:** `CalendarFeedRepository` — `get(me) -> FeedLink | None` (unseals), `replace(me, token_hash, token) -> FeedLink` (upsert, seals), `delete(me)`, `account_by_token(token_hash, today) -> Account | None` (one statement: `_COLUMNS` of the account joined to `calendar_feed`, plus a data-modifying CTE that sets `fetched_on = today` only when it differs: ≤ 1 write per feed per day). `TokenSource.new() -> str` (`secrets.token_urlsafe(32)`, 256 bits). Hashing is stdlib `hashlib.sha256` in the use case (no salt or pepper needed at 256 bits of entropy).
- **Serializer (adapter, pure function)** `api/ics.py::render(feed) -> bytes`: hand-written, ~80 lines, no runtime dependency (ADR-0036): `VCALENDAR` (`VERSION:2.0`, `PRODID:-//Tristhana//SC-06//EN`, `CALSCALE:GREGORIAN`, `METHOD:PUBLISH`, `X-WR-CALNAME`, `REFRESH-INTERVAL;VALUE=DURATION:PT6H`, `X-PUBLISHED-TTL:PT6H`); per event `UID`, `DTSTAMP` = link `created_at` (stable, so the body and ETag only change when content does), `DTSTART/DTEND` in **UTC `…Z`** (classes) or `;VALUE=DATE` with `DTEND` = next day and `TRANSP:TRANSPARENT` (moon), `SUMMARY`, `DESCRIPTION`, `LOCATION`; no `SEQUENCE` (full replacement on every poll), no `VTIMEZONE`, no `RRULE`. TEXT escaping `\\ ; , \n`; control characters stripped from user-entered names/titles; **CRLF**; folding at **75 octets** on UTF-8 boundaries (emoji-safe).

## 4. API
| Method, path | Request → Response | Auth / policy |
|---|---|---|
| `GET /api/v1/me/calendar-feed` | → `CalendarFeedOut {on, url?, google_url?, subscribe_url?, created_at?, fetched_on?}` | initData; owner; `no-store` |
| `POST /api/v1/me/calendar-feed` | → `CalendarFeedOut` (create; an existing link comes back unchanged) | initData; owner; `no-store` |
| `POST /api/v1/me/calendar-feed/rotate` | → `CalendarFeedOut` (a new link; the old one stops working) | initData; owner; `no-store` |
| `DELETE /api/v1/me/calendar-feed` | → 204 (idempotent) | initData; owner |
| `GET`, `HEAD /ical/v1/{token}.ics` | → 200 `text/calendar; charset=utf-8`, `ETag` (SHA-256 of the body, 16 hex), 304 on `If-None-Match`, `Cache-Control: private, max-age=1800`, `Content-Disposition: inline; filename="tristhana.ics"`, `X-Robots-Tag: noindex`, `Referrer-Policy: no-referrer`; **404** identical (body, headers, no timing branch beyond the format check) for malformed, unknown, rotated or revoked tokens and deleted accounts | the token; outside `/api/v1` auth, CORS and OpenAPI (`include_in_schema=False`); versioned path |
| `GET /ical/v1/{token}/subscribe` | → 302 `webcal://…/ical/v1/{token}.ics` (no DB read; a bad token just gets a dead link) | none |

URLs are built from a new setting **`PUBLIC_API_URL`** (https; empty = feature hidden: `GET` says `on: false, available: false`). Changing the host later breaks subscriptions, so the `run.app` host must keep serving `/ical/v1` after a custom domain arrives (§9).

## 5. Bot
Callbacks `c1:f:<a>`, `a` ∈ `s` show · `n` create · `r`/`R` rotate ask/confirm · `x`/`X` off ask/confirm; unknown → `nothing()`. Stateless (ADR-0008): a stale `R` or `X` re-reads and acts on the current link only. The handler calls the same use cases; the URL text and both URL buttons come from `FeedLink` + settings.

## 6. DB: migration **0023 `calendar_feed`** (expand-only)
`calendar_feed(account_id uuid PK → account ON DELETE CASCADE, token_hash bytea NOT NULL UNIQUE CHECK (length = 32), sealed_token bytea NOT NULL /* ADR-0016, AAD = account_id ‖ "calendar-feed" */, created_at timestamptz NOT NULL DEFAULT now(), fetched_on date NULL)`. One per account (Q149). Grants by default privileges (0001, 0015). In `export.py::EXCLUDED_TABLES` ("a secret; shown in the app, never exported"). Account delete (ST-09) cascades → the next poll gets 404.

## 7. Cross-cutting checks
- **Time zones ✔.** Instants as **UTC `Z`** (expanded by `wall_to_utc` in the class zone, so 06:30 Berlin stays 06:30 across DST); the client shows them in the device zone, matching SC-03's "my zone first". The class's own clock and label go in `DESCRIPTION` when the offsets differ ("Class time: 17:30 Berlin (UTC+1)"). No `TZID`/`VTIMEZONE`: we would have to generate RFC VTIMEZONE rules from tzdata, and clients that ignore them misplace events. Moon days are **floating all-day dates** of my moon city (same rule as MD-02/SC-03: a moon day is a date, so a traveller sees it on that date). Window bounds use the UTC date (no viewer bucketing needed). Kathmandu +5:45 / Kolkata +5:30 class zones tested.
- **Privacy ✔.** Capability token: 256 bits, stored as SHA-256 (lookup) + sealed copy (re-show); never logged, never in `localStorage`. If leaked it reveals: my shalas' names, class times, staff names, my staff roles (covering lines), roughly my moon city (from the dates); not my name, Telegram id, log, rest, 🌸, diary, or 1:1 titles (Q150). Rotation and revoke take effect on the next request (no cache keyed by token). Membership is re-read on every poll: leaving or being removed from a shala drops its classes. **Logs:** our own line per fetch carries the route template, status, events, duration and `sha256(token)[:8]`; Cloud Run's platform request log records the full URL, so a Logging **exclusion filter** on `/ical/` (☁️ owner, Q153) removes it from `_Default`. Import-linter: `application.calendar_feed` imports no `ports.practice/diary/check_in/rest_periods/progression/teacher_view` (direct imports, as SC-03).
- **i18n ✔.** Event text in the account's language at poll time (a language change shows on the next refresh); keys in `bot.ftl` (feed + bot screen) and `app.ftl` (Mini App), en + ru parity; dates via `DateArg`; RU plurals not needed (no counts).
- **Responsiveness / cost ✔.** Poll = **2 statements** (token→account with the daily touch; `member_windows`) + expansion over ~74 days; no new imports (stdlib `hashlib`, `secrets`); body built once, ETag from it, 304 saves bandwidth only. Clients poll every 3–24 h, so load is tiny; no app rate limit (Cloud Run max-instances bounds cost; a leaked hammered link is fixed by rotating). Management taps: 1 statement after the principal load.
- **Measure before done:** realistic (2 shalas × 10 series) and worst case (15 × 40 daily series × 20 overrides): statement p50/p95, expansion + render time, body bytes. Targets: realistic server p50 < 50 ms, body < 100 KB; worst case < 1 s or the `MAX_EVENTS` cap engages. Record in §11.

## 8. Test plan
- **Serializer (golden):** fixed `Feed` → byte-exact `.ics` fixture: CRLF everywhere, a 75-octet fold inside a RU title with emoji (no split UTF-8 sequence), escaping of `,;\` and newlines in a staff name, a stripped control char, all-day moon event with `DTEND` next day, `DTSTAMP` stable across renders, same input → same ETag. Parse the fixture with `icalendar` as a **dev-only test dependency** (validates, not shipped).
- **Domain:** UID stability: a moved occurrence and a swapped B keep `class-key` UID; `MAX_EVENTS` drops the furthest; token format check.
- **Use case (fakes):** DST: Berlin Mysore 06:30 across 25 Oct 2026 and 28 Mar 2027 → `05:30Z` / `04:30Z`; an Almaty account sees the Berlin label in `DESCRIPTION`, a Berlin account does not; RU titles («Майсор · Анна», «🌕 Полнолуние (Пурнима)») for a `ru` account; a class with its own title shows the title, not the type; moon events from my inherited city (MD-02) incl. a kshaya date (same SUMMARY as a regular one, no kshaya label), DESCRIPTION = `moon-calc-note` in EN and RU; cancelled (moon, closure, staff) rows absent, held-on-moon present with the line; **substitute:** a date Dana covers for Anna has SUMMARY "Mysore · Dana" and "Dana (for Anna)" in DESCRIPTION; **moon dates differ by a day:** the shala cancels on its moon date (Fri) while my moon city has Sat → Fri's class is simply absent and my all-day 🌕 is on Sat (pinned as expected behaviour); 1:1 present for staff with type only, absent for a student; **privacy:** a followed teacher's non-member shala absent; no log/rest/🌸 port called (fake raises if touched); a non-member gets moon days only; deleted/unknown token → None.
- **Token lifecycle (DB, real Postgres):** create → fetch 200; rotate → old 404, new 200; revoke → 404; account delete → 404 and row gone; `token_hash` unique; `fetched_on` written once per day (statement counter: 2 per poll); sealed round-trip; app-role grants.
- **API contract:** 401 on the three `/me/calendar-feed` routes without initData; key sets; `/ical` 404 bodies and headers identical for malformed/unknown/revoked; `HEAD` = `GET` headers without body; 304 on matching `If-None-Match`; content type; not in OpenAPI; `/subscribe` 302 to `webcal://`; feature hidden when `PUBLIC_API_URL` is empty; a log-capture test asserts the token never appears in our logs.
- **Bot (webhook):** `c1:f:s` off/on states EN + RU; create shows URL + 2 URL buttons (https only); rotate and off need the confirm; stale `R`/`X` safe; forged `c1:f:z` ignored; answered first; entry rows on `/schedule`, `/moon`, `/settings`.
- **Mini App (Vitest, also `TZ=UTC`):** states, copy, confirm popups, `openLink` called with https only, RU at 320 px, no URL in storage; `check:bundle`.
- **Owner on a phone:** subscribe in Google Calendar and Apple Calendar from the bot; see a week of classes in local time and the next moon days; rotate and see the old one stop.

## 9. Risks
- When the shala's moon date and mine differ by a day, a moon-cancelled class just disappears from its day with no marker there (cancellations are omitted, Q147), while my 🌕 sits on the next day. Accepted by the owner; the moon event's `moon-calc-note` ("may differ by a day; follow your teacher") and the app's 🌙-led row explain it.
- Google refreshes subscriptions on its own schedule (often 8–24 h); copy says "up to a day". Nothing we can do server-side.
- Host change breaks every subscription: keep the `run.app` host serving `/ical/v1` (or 301 it) forever once published.
- A leaked link exposes the schedule until rotated; bounded by the content rules above; links in chat history and in Google's servers by design.
- Worst-case expansion over ~74 days; mitigated by measurement and `MAX_EVENTS`; fallback: shorten `CLASSES_AHEAD` for very large accounts.
- Platform request logs hold the token until the exclusion filter exists (☁️).

## 10. Questions for the owner (answered 2026-11-08: all as recommended, and the ashtanga-expert review accepted)
- **Q145 Scope.** ✅ One feed per account = My schedule (All filter) + my own moon days; no per-filter or per-shala feeds.
- **Q146 Who gets it.** ✅ Everyone, including people without a shala (moon days only, with a "join a shala" line); entries on My schedule, `/moon` and Settings.
- **Q147 Cancelled classes.** ✅ Omitted, never `STATUS:CANCELLED`. Owner: this holds for **every** cancellation (moon, closure, staff cancel); no "Cancelled" events.
- **Q148 Window.** ✅ Classes 2 weeks back to 8 weeks ahead; moon days 1 month back to 12 months ahead; at most 2000 events.
- **Q149 Link storage.** ✅ Hash + sealed copy (ADR-0016), re-showable, one link per account.
- **Q150 1:1 classes.** ✅ Staff only, "1:1 · teacher" without the custom title.
- **Q151 Bot delivery.** ✅ Bot + Mini App; the bot posts the link in my own chat with the 🔒 line.
- **Q152 One-tap add.** ✅ Google `cid=` button, Apple/Outlook via the https → `webcal://` redirect, plus copy.
- **Q153 Logs.** ✅ Cloud Logging exclusion filter for `/ical/` (☁️ owner action after deploy); our line keeps a hash prefix.
- **Q154 Day markers.** ✅ None (no shala 🌙, day off, my day off or any rest).
- **Q155 Alarms.** ✅ No `VALARM`.
- **Q156 "Last checked".** ✅ `fetched_on` stored ≤ once a day and shown.
- **ashtanga-expert review (owner, accepted):** (1) the moon event's DESCRIPTION is `moon-calc-note` verbatim in EN and RU ("…Your shala's calendar may differ by a day; follow your teacher."); the draft RU «Лунный день для 📍…» is dropped (ambiguous with tithi); no kshaya label. (2) SUMMARY names the teacher actually teaching that date (the substitute), with `schedule-covering-for` ("Dana (for Anna)") in DESCRIPTION; tested. (3) The shala-cancels-Fri / my-moon-Sat case (class silently gone) is in the tests and §9 risks. (4) A class's own title wins over the type name.

## 11. Build notes
Built 2026-11-08 on `sc-06/ics-feed`.
- **Measured** (local Postgres 17, warm, 30 polls, use case + render): worst case 15 shalas × 40 daily series → 2000 events (capped), 449 KB, **133 ms** p50 (target < 1 s ✔); "realistic" 2 shalas × 10 daily series → 1280 events, 287 KB, **52 ms** p50 (target < 50 ms / < 100 KB: slightly over; clients poll every 3–24 h and get 304 when unchanged, so accepted); a typical student (2 shalas × 3 classes, 3 days a week) → 168 events, 38 KB, **15 ms**. A first build measured 1.46 s / 94 ms; fixed by (1) a no-fold fast path in the serializer, (2) choosing the nearest `MAX_EVENTS` before building events and memoizing translations per poll, (3) `_expansion_end`: when classes would clearly overflow the cap, expand only the days that hold them (counted per series from its own start; a quarter to spare), and expand the whole window again when cancellations or closures leave room (review fix).
- **Statements:** a poll is 2 (`account_by_token` with the daily `fetched_on` CTE, `member_windows`); a dead token 1; a malformed token 0. Pinned by DB tests.
- **Deviations:** `member_windows` also takes `moon_start` (moon days reach −30 while classes read from −16); `account_by_token` returns `FeedOwner(account, created_at)`; `type_name` moved from the bot to `application/classes.py` (the bot and the feed share it); `icalendar` is a dev dependency that parses the golden body (not in the image).
- **Review fixes (code-reviewer):** link previews are disabled on the link screens (Telegram's crawler would fetch the secret URL and stamp "last checked"); **create is idempotent** (a stale "Create" returns the current link) and rotation is explicit (`POST /me/calendar-feed/rotate`, bot `R`); the expansion bound re-expands after closures; the moved-from time carries its zone label; `/subscribe` checks the token format and sends `no-store` + `no-referrer`; `If-None-Match` accepts weak and `*`; with no `PUBLIC_API_URL` the feed routes 404 (off, not only hidden); the Mini App card shows an error line. Nits left: event length from wall-clock times (wrong by an hour only for a class spanning a DST jump), "last checked" is a UTC date shown as a day name (may read a day early for +10…+14), dev uvicorn's access log shows the token locally.
- **ashtanga-expert re-check:** items 1–4 as agreed; the 2025 Mysuru test now uses our generator's dates (27 Feb and 4 Dec kshaya), not SYC's posted list.
- **ux-writer:** unpinned copy polished (confirm "✅ Yes" / "‹ Back", "✓ Copied", "Shala time: …", RU held-on-moon line without «лунный день»).

