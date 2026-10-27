# PR-07: diary note per day (private, sealed, text only)

- Status: **accepted** (owner, 2026-10-27: all as recommended, plus a confirm step for Remove and gentle examples on the empty screen; ashtanga-expert fixes applied) · Date: 2026-10-27 · Size S, Phase 2
- Requirements: **PR-07** (a diary note per practice/day, private by default, text first). Touches **ST-09** (export decrypts notes, delete cascades) and **ST-06** (teachers never see notes; the matrix says "per entry" sharing later). Builds on PR-01 (`d1:` day picker), PR-06 (check-in screen K: PR-06 decision 6, "PR-07 adds a note button on K") and ADR-0016 (field encryption).
- Related: ADR-0005, 0007, 0008, 0012, 0016, 0021, 0024. New: **ADR-0025** (one sealed note per day, independent of the status; bot input by ForceReply; accepted).

## 1. Scope
**In:** one optional free-text note per **local day**, on any day up to today (practiced, rest, moon, 🌸, sick, travel, skipped, or not logged at all). Bot: a `[📓 Note]` button on the day picker and on K, a note screen N, writing by replying to a prompt. Mini App: a note block in the Today card and the DayEditor. API: the note on `GET /me/days`, `PUT`/`DELETE` on the day's note.
**Out (later):** a diary list/history or search (needs its own screen, Phase 3), voice notes (§9 Q6), photos, formatting, sharing with a teacher (ST-06, per entry), reminders or prompts to write, any word counts or "you wrote N days" stats, server-side search or previews. **No parsing, keyword detection, inferences or advice from note text** (e.g. pain, injury, an asana name, cycle). A note mentioning a new asana never changes the last given asana.
**Tone:** always optional, never asked for. An absent note gets only a quiet Add link or button: no "yet", no question marks, no counts. Never offered in pushes, reminders, the PR-10 saved screen (V) or the onboarding greeting. The icon is 📓, never a flower, 🪷, 🙏 or 📖.

## 2. Domain (pure) `domain/diary.py`
```python
MAX_CHARS = 2000                                 # code points, after normalising
class NoteTooLong(ValueError)
def normalize_note(text: str) -> str | None      # CRLF → LF, drop C0/C1 controls except \n \t,
                                                 # strip ends; "" → None (= delete); > MAX → NoteTooLong
@dataclass(frozen=True, slots=True)
class DiaryNote: text: str | None                # None = present but unreadable (lost key)
```
- **Per day, not per slot**, and **independent of the day's status**: no FK to `day_log`, no status column. Changing the status, clearing the day, rest periods and auto-rest **never touch the note**. So the stored row is identical for 😌 and 🌸 (and every other status), and a note never reveals 🌸. Removing the note is always explicit.
- Dates follow the logging rules: `check_loggable(day, now, zone)` (≥ 2000-01-01, not after the caller's local today, provisional zone allowed). Errors reused: `DateInFuture`, `DateTooEarly`.
- Plain text only: the bot reads `message.text` (entities ignored); the bot sends with no `parse_mode` (as today), so the text is never interpreted. A test guards this.

## 3. Application and infrastructure
- Port **`DiaryRepository`** (`application/ports/diary.py`, on `Storage.diary`), one statement per method:
  - `save(account_id, date, text) -> None`: `INSERT … ON CONFLICT (account_id, local_date) DO UPDATE SET sealed_text, updated_at`.
  - `get(account_id, date) -> DiaryNote | None`: PK select (bot screen N only).
  - `delete(account_id, date)`: idempotent.
- Use cases `application/diary.py` (own data, `Principal`): **`SaveDiaryNote(principal, date, text) -> str | None`** (normalises; `None` → delete; raises `NoteTooLong`, `DateInFuture`, `DateTooEarly`), **`GetDiaryNote`**, **`ClearDiaryNote`**. Reads for screens go through the existing **`GetDays`**: `RangeView` += `notes: dict[date, DiaryNote]`, filled in `range_with_moon` by two scalar subqueries (`array_agg(local_date)`, `array_agg(sealed_text)` over the PK range), like `period_arrays`: **still one statement**. `list_range` (reminders) and `history` (stats) **don't read notes**.
- **Sealing** in `infrastructure/db/diary.py` with ADR-0016's `FieldCipher`: AAD `b"diary_note.sealed_text|" + account_id.bytes + local_date.isoformat().encode()`. Active key seals, all keyring keys open. **`UnreadableSeal` → `DiaryNote(None)`**: the row is kept (a restored key brings it back), shown as "can't read this note", and can be overwritten or removed; a warning logs the account uuid only. `MissingCipher` (dev, no key) → `StorageUnavailable`, as for rest rows.
- **Policy:** `can_view_diary(viewer, student) -> bool` = viewer is the owner (named now so ST-06 has one place to extend). Teacher projections and shala aggregates never select `diary_note`; ST-06 adds a test.
- **ST-09:** the export decrypts each note (`{"date", "text"}`, unreadable → `{"date", "unreadable": true}`); account delete cascades.

## 4. API (initData auth; additive; regenerate the client with `gen:api`)
| Method, path | Request → Response |
|---|---|
| `GET /api/v1/me/days` | `Days` += `notes: [DayNoteOut]`, `DayNoteOut {date, text: string \| null, unreadable: bool}`, only days that have a note (any status, also unlogged days, so not on `Day`) |
| `PUT /api/v1/me/days/{date}/note` | `{text: string}` → 200 `DayNoteOut` (blank text deletes and returns `text: null, unreadable: false`); 422 `note_too_long`, `date_in_future`, `date_too_early` |
| `DELETE /api/v1/me/days/{date}/note` | → 204, idempotent |

- The text travels **only in bodies**, never in a URL or query. The length is checked in the domain (no Pydantic `max_length`, whose default 422 echoes the `input`); `api/errors` also strips `input` from every validation error. A body over 16 KiB → 413. Responses carrying notes get `Cache-Control: no-store`. `ErrorCode` += `note_too_long`.

## 5. Bot (prefix **`n1:`**, stateless, ≤ 17 bytes; answer first; ADR-0025)
| Data | Meaning |
|---|---|
| `n1:o:20261027:d` / `…:k` | open N (origin: day picker `d` or check-in K `k`, for Back) |
| `n1:w:20261027:d` | send the write prompt |
| `n1:y:20261027:d` | ask to confirm removal (`diary-clear-confirm` [Remove] [‹ Back → N]) |
| `n1:x:20261027:d` | remove the note → N with `diary-removed` |
| `n1:b:20261027:d` | back to the origin screen |

- **Entry:** the day picker (`d1:o`, any day) shows a preview line `diary-preview` (first 100 characters + "…") when a note exists and a `[📓 Note]` button (from the existing `range_with_moon` read: **no new statement**). K gets `[📓 Note]` (`…:k`) with no preview, so K stays one statement.
- **N:** the day label (**date only, no status emoji**), the full note (or `diary-empty` / `diary-unreadable`), then `[✏️ Write]` (`diary-write`, or `diary-rewrite` when one exists), `[Remove note]` (when one exists or is unreadable; goes to the confirm step), `[‹ Back]`. Opening N = + 1 PK read. The confirm step renders with no statement; `n1:x` = 1 delete, no read.
- **Writing (ForceReply, ADR-0025):** `[✏️ Write]` sends a **new** message (Telegram can't attach ForceReply to an edit): line 1 is a fixed token **`📓 2026-10-27`** (ISO date, locale-independent), then `diary-prompt` (+ `diary-prompt-replace` when a note exists), with `ForceReply(input_field_placeholder=diary-placeholder)`. 0 statements.
- **The reply** (`F.reply_to_message`): accepted only when `reply_to_message.from_user.id == bot.id` and its text matches `^📓 (\d{4}-\d{2}-\d{2})\n`. The account always comes from the sender (middleware, private chats only); the token carries **only a date**, so a reply can only ever write the sender's own day. Text → `SaveDiaryNote` (1 upsert) → a new message: `diary-saved` (a short confirmation) + the N buttons, **never the text echoed back**. Too long → `diary-too-long` (nothing saved, the person's message stays in the chat to copy). Voice, photo, sticker or a caption → `diary-text-only`. A reply to an old prompt saves to **that prompt's date** (explicit) and replaces the note. A reply to any other message, or plain text → the existing `fallback-text`. Edits aren't delivered (`allowed_updates` = message, callback_query): N says "to change it, tap ✏️ Rewrite".
- **Failures:** future/too-early date → the day picker with `log-date-future`; DB outage → `error-temporary`; malformed `n1:` ignored.

## 6. Mini App `DiaryNote.tsx`
- In `TodayCard` (below the check-in, **any status or none**) and `stats/DayEditor`. Collapsed: the note clamped to 3 lines + `diary-edit`, or a `diary-add` link. Unreadable: `diary-unreadable` + Remove. Remove asks `diary-clear-confirm` inline before the DELETE, then shows `diary-removed`.
- **Editing:** a `<textarea>` with **explicit Save / Cancel** (not save-on-blur: in Telegram's WebView blur fires on keyboard hide and app switch). Counter from 1800 chars (`[...text].length`, code points). While dirty, `enableClosingConfirmation()`. `useSaveDiaryNote`: PUT in mutation scope `"note"` (independent of status taps), **not optimistic for the text**: on error the textarea stays open with the text + `diary-save-failed`; on success the server value goes into the days cache. Blank Save sends DELETE. No drafts in `localStorage`. ~+1 KB gzip, no dependency.

**Copy (new keys in `bot.ftl` and/or `app.ftl`; «ты»; ux-writer polishes).** 📓 not 📝 (📝 is /log in `help-text`); «дневник» is this feature (2026-10-18 naming decision).
- `diary-button` "📓 Note" / «📓 Заметка» · `diary-title` "Diary" / «Дневник»
- `diary-empty` "No note for this day. Write anything you'd like to keep: how the practice felt, what your teacher said, a new asana, or just a thought." / «Заметки за этот день нет. Можно записать что угодно: как прошла практика, что сказал преподаватель, новая асана или просто мысль.»
- `diary-prompt` "Write your note for { $day } as a reply to this message. It's private, just for you." / «Напиши заметку за { $day } в ответ на это сообщение. Она личная, только для тебя.» (`$day` = the relative day label; RU «за сегодня / за вчера / за вт, 27 окт.» checked)
- `diary-prompt-replace` "It will replace the current note. Copy the note above to edit it." / «Она заменит текущую. Текст заметки выше можно скопировать и поправить.»
- `diary-placeholder` "Your note…" / «Твоя заметка…» · `diary-saved` "📓 Saved to your diary." / «📓 Сохранено в дневнике.»
- `diary-write` "✏️ Write" / «✏️ Написать» · `diary-rewrite` "✏️ Rewrite" / «✏️ Переписать» · `diary-clear` "Remove note" / «Удалить заметку»
- `diary-clear-confirm` "Remove this note?" / «Удалить заметку?» · `diary-clear-yes` "Remove" / «Удалить»
- `diary-removed` "Removed from your diary. Earlier messages in this chat stay until you delete them." / «Заметка удалена из дневника. Сообщения выше в чате остаются, их можно удалить в Telegram.»
- `diary-too-long` "That's a bit long for one note: up to { $max } characters. Your text is still above, so you can shorten it and resend." / «Для одной заметки длинновато: до { $max } символов. Текст остался выше, можно сократить и отправить снова.»
- `diary-text-only` "Notes are text for now. Type your note as a reply to the prompt above." / «Пока заметки бывают только текстом. Напиши её ответом на сообщение выше.»
- `diary-unreadable` "This note can't be read right now. You can write a new one or remove it." / «Эту заметку сейчас не получается прочитать. Можно написать новую или удалить старую.»
- `diary-preview` "📓 { $text }" · App: `diary-add` "Add a note" / «Добавить заметку», `diary-edit`, `diary-save`, `diary-cancel`, `diary-counter` (`$n`/`$max`, plural-free), `diary-save-failed`, `diary-private-hint` "Your diary is private: teachers don't see it." / «Дневник личный: преподаватели его не видят.»
- Reused: `log-back`, `log-date-future`, `error-temporary`, `fallback-text`.
- **Words to avoid in `diary-*`** (test grep): PR-06's list plus EN journal, wrong, mistake, fail, improve, progress, goal, performance, achieve, lazy, excuse, "keep up", "don't forget", "remember to", "every day", habit (and no "only"/"again" in EN); RU журнал, ошибк, неудач, прогресс, цель, результат, лень, оправдан, не забудь, каждый день, привычк, должен/должна. No gendered past tense in RU.

## 7. Migration `0013_diary_note` (expand-only, down_revision `0012`)
`diary_note(account_id uuid not null references account on delete cascade, local_date date not null, sealed_text bytea not null, created_at/updated_at timestamptz not null default now(), primary key (account_id, local_date))`. CHECK `octet_length(sealed_text) BETWEEN 42 AND 8041` (1 key id + 24 nonce + 16 tag + 1..8000 bytes = 2000 code points × 4). CHECK `local_date >= '2000-01-01'`. The old revision ignores the table; downgrade drops it; no data change, no owner step.

## 8. Cross-cutting checks
- **Time zones:** a note belongs to a local `date`; "today" is the caller's local today from the clock and account zone (provisional allowed), the Mini App uses the payload's `today`. No time is displayed, so no zone label. `updated_at` is audit only. Tests: Kiritimati vs Honolulu on one instant, provisional zone, a note on an unlogged auto-moon day.
- **Privacy:** sealed at rest (AAD binds account and date: a ciphertext moved to another row fails), owner-only by policy, absent from teacher views (not even "has a note") and aggregates, independent of status (never reveals 🌸). **No note text or "has note" marker** on the week picker, stats heatmap, month summary, or any push/reminder; note text appears only on the single-day screens (the day picker, N, the Today card and DayEditor). After a reply the bot never echoes the text, and `diary-removed` says honestly that earlier chat messages stay until the person deletes them. **Never logged:** webhook logs keep update id/type only and exception frames without messages (already); API logs no bodies; no note text in exceptions (`NoteTooLong` carries the length only). Ciphertext length reveals the approximate note length (accepted, ADR-0025). Key rotation: new key first in the keyring, old keys stay until no row starts with their id byte (`get_byte(sealed_text, 0)`); a re-seal job is out of scope.
- **i18n:** all copy in `.ftl` (en/ru parity test); the length uses a number, no plural forms; the note itself is never translated.
- **Responsiveness:** picker and K: 0 new statements; N open: 1 read; reply save: 1 upsert; remove: 1 delete; write prompt: 0. Callbacks answered first (`answered`), edits in place, new messages only for the prompt and after a reply. Decrypting is microseconds. No dependency, no startup cost.

## 9. Test plan
- **Domain:** `normalize_note` (CRLF, controls, trim, blank → None, 2000 ok, 2001 code points rejected, emoji count as 1, Cyrillic).
- **Use case (fakes, fixed clock):** blank deletes; future and too-early dates raise; `GetDays` carries notes for unlogged days; status change and `ClearDayStatus` leave the note.
- **DB (real Postgres):** round-trip; **the stored bytes don't contain the plaintext** (ASCII and UTF-8 probes) and are a valid seal; the AAD binds (a row's `sealed_text` copied to another date/account reads as unreadable); a retired key → unreadable and the row kept; `range_with_moon` stays one statement with notes; `history`/`list_range` don't touch `diary_note`; a 🌸 and a 😌 day's note rows are indistinguishable; CHECKs; account delete cascades; 0013 up → down → up; `alembic check`.
- **API:** 401; PUT 200 / blank → `text: null` / 422 `note_too_long` **without the text in the body** / future date; DELETE 204 twice; `/me/days` `notes` incl. an unlogged day and an unreadable one; `no-store`; OpenAPI lists `note_too_long`; the TS client builds.
- **Bot (fake use cases):** the picker preview and button, also right after a status change that deleted the check-in; K button; N with/without/unreadable note, its label has no status emoji; Remove → confirm (no statement) → `n1:x` deletes → `diary-removed`; the prompt starts with the token and carries ForceReply (+ the replace line when a note exists); a reply saves to the token date and the confirmation **doesn't contain the text**; no note text or marker on the week picker, V or reminders; a reply to a non-bot message, a bot message without a token, or plain text → `fallback-text`, nothing saved; a voice reply → `diary-text-only`; too long → nothing saved; a reply with a future token date → `log-date-future`; no `parse_mode` on N; every `n1:` round-trips, ≤ 64 bytes; malformed ignored.
- **Mini App (Vitest):** collapsed/expanded, the empty state is a quiet Add link, Remove asks to confirm, explicit Save PUTs, Cancel discards, a failed save keeps the text, blank Save sends DELETE, the counter counts code points, an old payload without `notes` renders, closing confirmation while dirty.
- **i18n/architecture:** en/ru keys exist and format; RU `diary-prompt` with today/yesterday/other labels; the extended avoid-word grep over `diary-*`; import-linter.

## 10. Decisions (owner + ashtanga-expert, 2026-10-27; all questions resolved)
1. ✅ **Scope:** one note **per day, any status, independent of status**; kept when the status changes or the day is cleared; removal is explicit.
2. ✅ **Input:** bot = **ForceReply reply to our own prompt** with the `📓 YYYY-MM-DD` token (ADR-0025), plus the Mini App editor.
3. ✅ **Remove needs a confirm step** (`n1:y` → `n1:x`, Mini App inline confirm); no extra statements.
4. ✅ **Empty screen with gentle examples** (`diary-empty`, §6).
5. ✅ **2000 characters**, plain text, trimmed, blank = delete; too long is refused, never cut.
6. ✅ **Unreadable seal:** keep the row, show "can't read" (with write-new / remove).
7. ✅ **Where it shows:** as §5–6; a diary history list later.
8. ✅ **Voice notes out** (audio storage, retention, blob encryption, export size; transcription would send private audio to a third party). Revisit after usage.
9. ✅ **Teacher sharing** decided at ST-06 (per entry, off by default); `can_view_diary` is owner-only now.
- **Expert fixes applied:** avoid-word-compliant copy (`diary-prompt`, `diary-private-hint`, `diary-too-long`); no echo of the text after a reply and an honest `diary-removed`; the confirm step; §1 no parsing/inference from note text; §8 single-day screens only; the tone rule for absent notes; `diary-empty` with examples; `diary-text-only`; the 📓 icon rule; the replace/copy line; `diary-unreadable` actions; the extended avoid-word list and tests.

## 11. Build and review notes (2026-10-27)
- **✏️ Rewrite is `n1:r`** (Write stays `n1:w`): the "replaces the current note" line rides in the button, so the prompt still needs no read.
- **The reply handler is registered last**, just before the fallback, and matches only replies to our own prompt that aren't commands: ForceReply keeps the input in reply mode, so `/log` sent as a reply must run `/log`, never become the note (code review blocker).
- **Body cap:** a small ASGI middleware (`api/body_limit.py`) on `PUT …/note` refuses over 16 KiB before the body is read (also for chunked bodies); a route dependency would only run after the body was read and parsed.
- **One statement, small rows:** `range_with_moon` sends the note arrays on the first row only (up to 8 KB per note must not repeat per (day, slot) row).
- Lone surrogates are dropped in `normalize_note` (valid JSON, not encodable as UTF-8).
- The day picker's preview line sits under the day's question line. `GetDiaryNote` always takes the clock (dates follow the logging rules).
- Mini App: the note block is keyed by its date (no draft or confirm carried to another day); Save is disabled past 2000 code points, with the counter as an alert.
- **Copy (owner, 2026-10-27, Q49):** EN "Type your note as a reply…", "It will replace the current note…"; RU «…или удалить старую», «Напиши её ответом…». The Mini App's `diary-removed` is its own: "Removed from your diary." / «Заметка удалена из дневника.» (the chat-history line belongs to the bot only).

