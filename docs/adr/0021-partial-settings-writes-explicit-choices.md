# ADR-0021: Settings writes are partial; explicit choices are never overwritten by client data
- Status: accepted
- Date: 2026-10-19

## Context
Settings come from three writers: the bot (one tap = one field), the Mini App (several controls), and implicit client data (Telegram `first_name` and `language_code` on every contact, the device time zone on every Mini App open). Two problems showed up before ID-06:
- `PUT /api/v1/me/notification-settings` replaces the whole row. It writes every default into the row, so the stored values become "frozen" (Q25), and a stale Mini App body can undo a change made in the bot meanwhile. PR-10 already had to make `practice` optional to avoid this.
- `profile_refresh` copies the Telegram name and language into the account on contact. Once people can choose a name or language, the next message would silently undo that choice. For the time zone, ID-01 already decided "captured silently if unset, never overwritten".

## Decision
1. **Settings writes are partial.** `PATCH /api/v1/me` and `PATCH /api/v1/me/notification-settings` change only the fields that are sent. **Omitted = unchanged; `null` = back to the default** (stored as NULL; for name/language, "back to Telegram"). The use case reads the stored row, applies the patch, validates the **merged** settings (`check_settings`), and upserts only the patched columns. The bot and the API share this use case. `PUT` stays for one release, marked deprecated, then it's removed. A one-time data migration nulls stored values that merely equal the current defaults.
2. **Explicit beats implicit.** The account stores `name_custom` and `locale_custom`. Provider refreshes don't touch a custom field, and SQL enforces this too (`CASE WHEN … THEN keep`), so a concurrent refresh can't race a choice. The time zone needs no flag: client data only ever fills an empty zone. A change is always a user action (Settings, the bot city picker, or the Mini App travel prompt).

## Consequences
- Defaults can evolve (e.g. a new moon send time) for everyone who never chose otherwise.
- Bot and Mini App edits no longer clobber each other. The cost is one extra read per settings tap (2 short statements instead of 1), well inside the 300 ms budget.
- Generated TS types must express "omitted vs null" (`?:` vs `| null`). The API uses Pydantic `model_fields_set`.
- Travelling users see a prompt instead of an automatic zone switch. That's slightly more friction, but no flip-flopping between devices with different zones.

## Alternatives considered
- **Keep PUT, add "reset to defaults".** It still freezes values and still lets a stale body overwrite bot changes.
- **JSON Merge Patch on a single settings document.** Same semantics, but a looser schema and a worse generated client.
- **`timezone_source = device | explicit`, updating device-sourced zones silently.** Rejected: two devices with different zones (a phone and a misconfigured desktop) would flip reminders back and forth. A prompt with a device-local "Keep" is simpler and needs no column.

## Known limits (accepted with the implementation, 2026-10-19)
- **Merged validation is read-then-write, not one transaction.** Two settings writes from different clients at the same instant (e.g. a bot tap moving the practice reminder to 22:00 while the Mini App sets quiet hours 21:00–07:00) can each pass against the row they read and together store a reminder inside quiet hours; it then simply doesn't fire until either is changed. Rare (one person, two surfaces, the same second) and harmless; a `SELECT … FOR UPDATE` inside one transaction is the upgrade if it ever matters.
- **Profile writes touch only the sent groups** (name + its flag, locale + its flag, zone), so two saves at once never undo each other; a Telegram refresh never overwrites a chosen name or locale (SQL `CASE`).
