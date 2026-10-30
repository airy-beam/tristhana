# MD-04 + ID-06: "🏙 My city" drives the zone, and a gentle local moon-day FYI

- Status: **accepted** (owner, 2026-10-30: §10 answered as recommended) · Size **M** (~3 days), Phase 2
- Requirements: **MD-04** (gentle FYI when the person's own location differs by a day), **ID-06** (profile: time zone → city). Touches **UI-01** (zone capture), **ST-09** (export), **MD-03** (moon city picker). MD-05 is postponed (appendix).
- Related: ADR-0005 (time model), 0008 (stateless callbacks), 0019 (cities in YAML, no FK), 0021 (partial writes, explicit choices), **ADR-0029 (new, proposed): the home city drives the zone**.

## 1. Goal and scope
**Bug today:** the bot picker (`settings.py` `zones()`/`_zone_city`) and the Mini App (`Settings.tsx` `Zone`, `zones.ts` `zoneCity`) list the cities from `cities.yaml`, but only `account.timezone` is stored. Tapping Astana marks Almaty, and Moscow/Sochi/Kazan behave the same way.
**In:** `account.home_city`. Picking a city writes the city and its zone together. "My city isn't listed" sets the zone only: the device zone in the Mini App, or a shared location in the bot (not stored). The time label uses the city name. The moon picker offers "Same as my city". MD-04 shows an ℹ line on `/moon` and on the Mini App moon card. There is a gentle nudge to pick a city.
**Out:** MD-05 (appendix); the FYI in reminders, Today or auto-rest; guessing the city from the zone; backfill; storing coordinates; a free IANA search; teacher visibility of `home_city` (MD-02/ST-06); localised zone names in the Mini App label when no city is set (it keeps the Latin IANA city, as today).

## 2. Domain (pure)
- `Account.home_city: str | None`. Values: **None = never chosen** (this drives the nudge), **`"-"` = chosen: not listed / not now**, or a city slug. This mirrors `day_off` (NULL vs 0). `domain/moon.py`: `Cities.find(slug) -> City | None` returns None for None and "-" (`get(None)` returns Mysuru, which is a trap here). The cities loader rejects a slug "-".
- **Invariant** (ADR-0029): if `home_city` is a city, then `timezone == city.tz`. It is enforced in one place, `resolve_profile(account, patch, client, cities)`, and `ProfilePatch` gains `home_city: str | None | KEEP`:
  - slug → `UnknownCity` if unlisted. Zone = `city.tz` (a different `timezone` in the same patch raises `InvalidTimezone`). Writes `{home_city, timezone}`.
  - `None` → store "-", and the zone stays as patched (or unchanged).
  - KEEP plus a zone change → `home_city` becomes "-" when the stored city's tz ≠ the new zone (travel, the UTC choice, or a location zone). It is kept when the tz is equal (Astana → the phone says Asia/Almaty).
  - `set_timezone_if_unset` (device report, `UseCityTimezone`) never touches the city: a slug needs a zone (DB CHECK), so it is NULL or "-" there.
- **Time label place:** `label_city(home: City | None, zone: str) -> City | None` returns `home` iff `home.location.tz == zone`. A removed city (slug no longer in YAML) reads as no city: no label, no FYI, nothing marked. The next zone write normalises it to "-".
- **MD-04:** `home_dates(followed: list[MoonDay], home: list[MoonDay]) -> dict[date, date]`. For each followed day, it finds the home day of the **same phase** (`kind.phase`, so kshaya_* = the same phase) within ±1 day, and keeps only pairs whose dates differ. Unpaired or ambiguous days are left out and never guessed. The FYI exists iff the home city is set and its slug ≠ the followed city's.
- **"Same as my city"** is stored as the **slug (a snapshot)**, not a link (ADR-0029). With a link, travel clearing the city would silently move moon days back to Mysuru.

## 3. Application, ports, infrastructure
- `UpdateProfile` passes `Cities` to `resolve_profile`, which is still one `UPDATE … RETURNING`. `AccountRepository.update_settings` writes `home_city` when it is in `fields`. Account `_COLUMNS` += `home_city`. **The account is already loaded once per interaction**: the bot middleware and the API `CurrentPrincipal` both go through `EnsureAccount.find_by_identity` (one SELECT of `_COLUMNS`). So the city reaches every label with **0 extra queries**, and the city names come from the in-memory `Cities`.
- `GetMoonView`: `MoonCalendarRepository.days_for(locations, start, end) -> dict[str, list[MoonDay]]` is one statement (`location = ANY(:locs)`, window start−1 … end+1; the followed days are then trimmed to start … end). `MoonView` += `home: City | None`, `home_dates: dict[date, date]`. Statements stay at 2 (days + settings), as today.
- New port `ZoneLookup.zone_at(lat, lon) -> str | None` and use case `ZoneFromLocation(principal, lat, lon)`. It runs the lookup, then `UpdateProfile` with `ProfilePatch(timezone=zone, home_city=None)`. Coordinates are never stored or logged; the log line is `zone_from_location found=<bool>`. The adapter `infrastructure/zone_lookup.py` uses **tzfpy** (ADR-0029: MIT code, ODbL data, ~3 MB wheel, no numpy). It is **lazy-imported on the first location** and not preloaded (about 15 ms first build, +~40 MB RSS of the 512 MiB). import-linter: `tzfpy` is allowed only in that module.
- `ExportAccount`: the profile gains `"home_city": {"slug": str | null, "chosen": bool}` (additive; `tristhana.export/1` unchanged).

## 4. Flows, callbacks and copy (drafts; ux-writer polishes; RU «ты»; city names never inflected)
**Bot `/settings`:**
- Status line, one of:
  - `settings-city-line` "🏙 My city: { $zone }" → "🏙 My city: Astana (UTC+5)"
  - `settings-city-unlisted-line` "🏙 My city: not in the list · 🕐 { $zone }"
  - `settings-city-unset-line` "🏙 My city: not chosen yet"
- While `home_city` is None, add `settings-city-nudge` "Pick your city: times will carry its name." plus `[Not now]` (`settings-city-not-now`). This is **one-time**: any answer, including Not now, stores "-". There is no extra column, no write on view, and the nudge is never shown again (§10.1).
- `[🏙 My city]` (`settings-city-button`, replaces `settings-zone-button`) opens the picker `settings-pick-city` "Which city do you live in? Reminders and times follow its clock." It lists the cities sorted by localised name (12 per page), with **✓ on the stored slug**, then `[📍 My city isn't listed]` (`settings-city-unlisted`), `[🌐 UTC]` (`settings-city-utc`) and `[← Back]`.
- **Not listed:** a **new message** (a reply keyboard can't be edited in): `settings-share-location` "Send your location once and I'll set your time zone from it. I don't store it. Can't send it from this device? Open the app: it can use your phone's time." It carries a reply keyboard `[📍 Send my location]` (`request_location`, `one_time_keyboard`).
  - On `F.location` (private chat, no `live_period`), the bot replies with `ReplyKeyboardRemove` and `settings-location-zone` "🕐 Done: your time zone is { $zone }. Change it in /settings.", or `settings-location-unknown` when the lookup returns None (open sea).
  - Telegram Desktop/Web may not support the button; UTC and the app are the fallback.
- **Callbacks** (`s1:`, all ≤ 64 B, stateless):
  - `s1:cp:<page>` picker. `s1:zp:<page>` is still decoded, for old messages.
  - `s1:c:<slug>` set the city (≤ 29 B). `s1:z:<slug>` is still decoded as the same thing.
  - `s1:c:-` not listed (sends the location prompt).
  - `s1:u` UTC.
  - `s1:n` Not now.
  - CI test: every city slug encodes ≤ 64 B.
- `_zone_city` and `zoneCity` are deleted.

**Bot `/moon`:**
- In the city picker, the first row is `[📍 Same as my city (Astana)]` (`moon-same-as-city`). It shows when the home city is set and differs from the followed one, and it sends the existing `m1:s:<slug>`.
- Under each of the 4 shown days that has a paired date, add the line `moon-home-fyi`: "ℹ In 📍 { $city } it falls on { $date }" / «ℹ 📍 { $city }: { $date }» (`DateArg`, e.g. "Sat, Oct 25" / «сб, 25 окт.»).
- `m1:z` (zone unset) stays zone-only (§10.3).

**Mini App ⚙️ Settings:**
- The `Zone` card becomes **"🏙 My city"** (`settings-city`). It shows "07:00 Astana (UTC+5)" (`settings-zone-now`) and a native `<select>` with:
  - the sorted cities (value = slug, selected = `me.home_city.slug`) → `PATCH {home_city: slug}`;
  - "My city isn't listed" (`settings-city-unlisted-option`), which reveals the chip "Use my phone's time: Bangkok (UTC+7)" (`settings-city-use-device`) → `PATCH {home_city: null, timezone: device}`, and `UTC` → `PATCH {home_city: null, timezone: "UTC"}`.
- Nudge: while `home_city_chosen` is false, show `settings-city-nudge` + `[Not now]` → `PATCH {home_city: null}`. Saves are optimistic with rollback (`settings-save-failed`).
- In the moon `<select>`, the first option is `moon-same-as-city` when the home city is set and differs.
- `MoonCard`: the ℹ line under a day with `home_date` (`moon-home-fyi`).
- **TravelPrompt:** "Switch" sends `{timezone: device}`. The server clears a mismatching city, and `here` = the home city name when set.

**Onboarding (UI-01):** the bot `/start` never sets a zone. The Mini App's first open fills an empty zone from the device (`RecordDeviceTimezone`, city stays NULL), and the Settings nudge then invites a city pick. No onboarding screen changes.

**Time labels (decision A):** the city name is used when `label_city(home, zone)` returns the city, else the zone's own name as today.
- Backend: `TimeArg` += `place: City | None = None`, and `format_time_label` uses `label_city(place, zone).name(locale)`. Four call sites, each passing the home city resolved from the already loaded `Account` plus the in-memory `Cities` (injected where missing):
  - `settings.py` `_zone_label`
  - `moon.py` `moon_status`
  - `remind.py` `practice_status`
  - `practice.py` `summary_text`: for a past practice the zone is the stored `p.timezone`, so Astana is shown only while that zone equals the city's
- Tick pushes contain no time label, so the tick query is unchanged.
- Mini App: `zoneLabel(zone, day, time, place?)`, `labelOf(zone, me)` and `placeFor(me, zone, locale)` take the name from `me.home_city` (no `useMoonCities` dependency). Call sites: `Settings` (now), `PracticeReminderCard`, `PracticeDetails` (`useMe()` cache) and `TravelPrompt`.

## 5. API (initData auth; additive; regenerate `openapi.json` → `npm run gen:api`)
| Method, path | Change |
|---|---|
| `GET/PATCH /api/v1/me` | `Me` += `home_city: CityOut \| null` (slug, name_en, name_ru, timezone; null for none, "-" or a removed city) and `home_city_chosen: bool`. `MePatch` += `home_city: str \| null` (omitted = unchanged; slug = city and its zone; null = not listed/not now). Errors: 422 `unknown_city`, and `invalid_timezone` when `home_city` and `timezone` disagree. A zone-only patch may clear the city (§2). |
| `GET /api/v1/me/moon-days` | `MoonDays` += `home: CityOut \| null` (only when set and ≠ the followed city). `MoonDayOut` += `home_date: date \| null` (only when paired and different). |
| `POST /me/device-timezone` | unchanged (fills an empty zone only) |

`CityOut` moves to a shared schema module. Old clients ignore the new fields. Policy: own account only (no new rule).

## 6. Migration `0018_home_city` (expand-only, down_revision `0017`)
- `account.home_city text null`.
- CHECK `home_city ~ '^[a-z-]{1,24}$'` (covers "-").
- CHECK `home_city IS NULL OR home_city = '-' OR timezone IS NOT NULL`.
- **No FK:** cities live in YAML (ADR-0019, like `moon_location`); `city.tz == timezone` is a domain rule.
- No backfill. Downgrade drops the column; the old code ignores it. `test_db_app_role` covers the app role writing it.

## 7. Cross-cutting checks
- **Time zones:** still IANA only. The city only names the zone and never offsets it, and logged days keep their own `timezone`. A city is never inferred from a zone. The FYI shows a local date with no time, so it needs no zone label. Tests cover a half-hour zone (Goa vs Mysuru: same tz, the FYI can still differ) and DST cities (London, Berlin).
- **Privacy:** `home_city` is city-level, owner-only, not shown to teachers, included in the export and cascaded on delete. **Coordinates are never stored or logged.** The location message stays in the person's own Telegram chat, and the prompt copy says so. tzfpy runs offline: no third-party call.
- **i18n:** all new strings go in `bot.ftl` and `app.ftl` (en and ru), checked by the parity tests. City names come from YAML, dates from `DateArg`/`Intl`, and city names are not inflected (hence the «ℹ 📍 Астана: …» form).
- **Responsiveness:** answer first, then edit in place. Pickers and labels are pure CPU. Each tap is still one `UPDATE … RETURNING` with no extra SELECT. `/moon` stays at 2 statements. The location reply is one webhook reply, and tzfpy is lazy (a rare path). Image +~3 MB.

## 8. Test plan
- **Domain:** `resolve_profile`:
  - slug → zone; slug plus a conflicting zone → error; unknown slug;
  - None → "-";
  - a zone change clears a mismatching city and keeps a same-tz one (Astana + Asia/Almaty);
  - UTC clears.
  
  Also: `Cities.find` (None, "-", removed); `label_city`; `home_dates` (exact, ±1 both ways, ±2 unpaired, kshaya vs plain same phase, a phase mismatch never pairs, year edge, same city → empty).
- **Use case (fakes):** `UpdateProfile` home/zone combinations; `GetMoonView` with home unset, "-", equal or different, and the one `days_for` call; `ZoneFromLocation` (found → zone and "-"; None → no write; coordinates absent from the fake log).
- **Infrastructure (Postgres):** both CHECKs; `update_settings` writes city and zone in one statement; `days_for` returns two locations in one statement; 0018 up → down → up; `alembic check`; the app role; the tzfpy adapter (Almaty, Bangkok, Kolkata, sea → None).
- **API contract:** `Me.home_city`/`home_city_chosen`; the PATCH matrix (slug, null, slug + zone conflict 422, `unknown_city`, zone-only clears); moon-days `home`/`home_date`; regenerated OpenAPI and the TS client builds.
- **Bot (fake use cases):** the picker marks the stored slug (Astana, not Almaty; Sochi, not Moscow); old `s1:z:`/`s1:zp:` decode; every callback ≤ 64 B; not listed → a message with `request_location`; the location handler → `ReplyKeyboardRemove` and a zone line; nudge + Not now once; the "Same as my city" row rules; the ℹ line only on paired, different days; `time-label` says "Astana (UTC+5)" only when the zones match; en/ru keys exist.
- **Mini App (Vitest):** the select shows the stored city; not listed → device chip/UTC; nudge and Not now; rollback on error; `zoneLabel` with a place; the TravelPrompt `here` name; the MoonCard ℹ line; a payload without the new fields still renders; the bundle check.
- **Architecture:** import-linter (domain pure; `aiogram` only in `bots/telegram`; `tzfpy` only in `infrastructure/zone_lookup.py`).

## 9. Size estimate
**M, about 3 days:**
- backend domain, use cases, migration and API: 1.25 d
- bot picker, nudge, location and the FYI line: 0.75 d
- Mini App settings, labels, card, TravelPrompt and the client regen: 0.75 d
- notes and ADR: 0.25 d

## 10. Owner answers (2026-10-30: all as recommended)
1. **"Not now" on the nudge** stores the same "-" as "not listed", so the nudge never returns. The alternative is a separate `city_nudge_dismissed_at` column (not worth a column). Recommended: as stated.
2. **After a trip** the city is cleared (decision 5), so on return the Settings line reads "🏙 My city: not in the list" and one tap restores it. The alternative is to remember the previous city and offer "Back in Astana?" (a second column and more rules). Recommended: accept for now.
3. **The `/moon` "🕐 Time zone: 📍 Almaty" button** (shown only while no zone is set) stays **zone-only**, since a followed moon city isn't where someone lives. The alternative is to also set the home city. Recommended: zone-only; the nudge then asks for the city.
4. **tzfpy's ODbL data:** attribution (timezone-boundary-builder / OpenStreetMap) goes in the README's licences section and in `/privacy`. Recommended: yes.

## Appendix: Deferred: MD-05 sketch (postponed 2026-10-30; SYC has not published 2026)
- If revived: SYC dates are a reviewed data file (`data/seed/moon_official.yaml`) that the tick writes into `moon_day` with `source = official`. CI checks them against the generator (generator unchanged). No admin endpoint.
- **Phase matching** (ashtanga-expert): pair official and computed days by phase within ±1 day, treating **kshaya_* as the same phase** as the plain kind; SYC never marks kshaya. The `home_dates` pairing above is reused.
- **Season-range imports:** an import covers a date range (a season), not a calendar year. Validate only inside the range, and keep computed days outside it.
- **Label:** "📍 Mysuru (SYC)", kept **in Latin in RU too**; never "KPJAYI".
- **Source:** cite `https://sharathyogacentre.com/holidays` plus an archived snapshot (Wayback Machine URL) per import, in the file's `source:`.
- **Open question 10** (does SYC place kshaya Amavasya on the later day? 2025-02-27/28) **stays open**. Revisit when SYC publishes the next season.
