# NT-03: announcements from a teacher to their students, or to a shala

- Status: **accepted** (owner, 2026-11-09: all as recommended except **Q165** (ashtanga-expert must-fix: silent in quiet hours, never held) and **Q173** (deleted ones don't count); plus the closure note in §9 and the expert's copy fixes; ux-writer pass before release) · Size S, Phase 3
- Requirements: **NT-03** ("Teacher announcements to their students / a shala group, with optional pinning"). Also covers the **NT-01** "teacher announcements" category (a toggle) and how it fits **NT-02** (quiet hours, daily cap). Builds on ID-04 (`teacher_link`, the consent; ID-04 §11 planned "a per-link mute column, through the tick and the ledger"), SC-01 (members and roles, ADR-0033), SC-02 Q118 (who manages the schedule), MD-03/PR-10 (the tick, ledger and `Notifier`, ADR-0018), ID-06 (Settings, ADR-0021), ST-09 (export, delete).
- Related: ADR-0008, 0012, 0016, 0018, 0030, 0033. New: **ADR-0038** (accepted). It covers fan-out through the tick from live membership, silent delivery in quiet hours, in-app pins, and plain text that can't be edited.

## 1. Scope
**In:**
- A **teacher** sends one announcement to **all their linked students**.
- A **shala's owner, manager, teacher or front desk** sends one to **everyone in the shala**: students and staff, except the author.
- Plain text, up to 1000 characters. Composed in the Mini App.
- Delivered as a **bot message** by the 10-minute tick through the delivery ledger. Never held: during the recipient's quiet hours it arrives **silently** (Q165).
- An optional **in-app pin**: one per source, 1 week or 1 month.
- A **feed** for recipients: the last 30 days plus the pin, in the Mini App and in the bot.
- **Mute per source**: a button on every message and on the feed. Plus one **NT-01 switch** in Settings.
- The sender's **sent list**, with pin/unpin and delete.
- A per-source rate limit. Export and delete coverage. One new line in each consent.

**Out (later):**
- One student or one class's attendees as the audience (needs SC-04/05 attendance).
- Replies or chat.
- Photos, files, formatting and link previews.
- Editing after sending.
- Deleting messages already delivered in Telegram (would need the message id stored per recipient).
- Telegram `pinChatMessage`.
- Read receipts and delivered counts.
- Scheduled ("send at") announcements.
- Automatic notices of cancelled classes (SC-02 Q122).
- **A shala closure announcement never marks anyone's day as rest** (owner, 2026-11-09). Announcements are text only: nothing is parsed, and no day, auto-rest or reminder changes. Revisit with Q122. Closures that affect days stay SC-02 `shala_closure` data.
- Telegram groups and channels (Phase 4).
- Composing in the bot (ForceReply + a draft row).
- A `/news` command.

**Tone:** an announcement is the teacher's voice, relayed. The app adds no urgency, counts or nudges ("3 students haven't read…" never exists).

## 2. Flows and copy
**Sender (Mini App, lazy chunk `announcements`).**
- Entry points:
  - `Students.tsx`: `📣 Announce`, shown with at least one student.
  - `ShalaScreen.tsx`: `📣 Announce`, shown per `can_announce_to_shala`.
  - Bot web_app buttons with the same label: on My students (`t1:s`) and on the shala card (`h1:c`).
- **Compose:**
  - The audience line (`ann-to-students` / `ann-to-shala`, with the count from the data already loaded: `/me/links`, `ShalaOut`).
  - A textarea with a live `n / 1000` counter.
  - Pin select: No / 1 week / 1 month.
  - `ann-hint`, plus `ann-hint-shala` for a shala source.
  - `[Send]` opens a native `showConfirm` (`ann-send-ask`, naming the count), then the POST, then `ann-sent` as `role="status"`.
- **Sent list** below the form: the last 30 days, each with the date, the first 2 lines, `ann-sent-to` (the audience size at send time), `📌 until …`, and `[📌 Pin]`/`[Unpin]` and `[🗑 Delete]` (`confirmDestructive`, `ann-delete-ask`).
- 409 `announcement_limit` shows `ann-limit` and keeps the text.

**Recipient (bot message, sent by the tick):**
```
📣 Ashtanga Almaty · Anna          (teacher: 📣 Anna · your teacher)
<text, as written>
[🔕 Mute announcements]  [📣 Announcements]
```
- **Mute** (`b1:m:…:n`) edits only the markup, to `[🔔 Send announcements again]` plus a one-line toast (`ann-muted`, `show_alert=false`).
- `[📣 Announcements]` opens the feed screen for that source (`b1:l`).
- The **shala card** (`h1:c`) and **my teacher's card** (`t1:c`) gain `📌 <pinned text, first 200 chars>` (when pinned) and `[📣 Announcements]`.
- **Feed screen** (bot):
  - Title `ann-list-title`, then up to 5 items per page, newest first, the pin on top.
  - Each item is `📅 Mon 9 Nov · Anna`, then the text.
  - The page stops at ~3800 characters with "…"; older items go on the next page.
  - `[🔕 Mute]`/`[🔔 Unmute]`, `‹ ›` paging, `[‹ Back]` to the card.
- **Mini App feed:**
  - A section on `ShalaScreen` (that shala).
  - A `📣 Announcements` row under Settings → Teachers and students (all sources, filter chips per source).
  - Each source has a switch "Send these to me in the bot" (mute).

**Copy** (⚑ = draft for the ux-writer; «ты»; RU gender-neutral verbs; names and shala names never declined; «учитель» for the ID-04 relationship, «сотрудники шалы» for staff, per the SC-01 glossary):

| Key | EN | RU |
|---|---|---|
| `ann-head-teacher` ⚑ | 📣 { $name } · your teacher | 📣 { $name } · учитель |
| `ann-head-shala` | 📣 { $shala } · { $name } | same |
| `ann-mute` / `ann-unmute` ⚑ | 🔕 Mute announcements / 🔔 Send announcements again | 🔕 Не присылать объявления / 🔔 Снова присылать объявления |
| `ann-muted` | Muted. You'll still find them under 📣 Announcements. No one is told. | Объявления больше не будут приходить. Они остаются в разделе 📣 Объявления. Об этом никому не сообщается. (expert) |
| `ann-list` / `ann-list-title` | 📣 Announcements / 📣 Announcements: { $source } | 📣 Объявления / 📣 Объявления: { $source } |
| `ann-list-empty` | Nothing in the last 30 days. | За последние 30 дней объявлений нет. |
| `ann-item` / `ann-pinned` | { $date } · { $name } / 📌 Pinned | same / 📌 Закреплено |
| `ann-announce` ⚑ | 📣 Announce | 📣 Сделать объявление |
| `ann-to-students` | To: all your students ({ $count }) | Кому: всем твоим ученикам ({ $count }) |
| `ann-to-shala` | To: everyone in { $shala } ({ $count }) | Кому: всем в шале { $shala } ({ $count }) |
| `ann-hint` ⚑ | Name the day and time (e.g. Mon 10 Nov, 6:00), not "tomorrow": it may be read later. Everyone it goes to sees this text and your name. Keep other people's personal details out. It can't be edited after sending. | Укажи день и время (например, пн 10 ноя, 6:00), а не «завтра»: сообщение могут прочитать позже. Все получатели увидят этот текст и твоё имя. Не пиши здесь личных данных других людей. После отправки текст изменить нельзя. |
| `ann-hint-shala` ⚑ | It goes to everyone in the shala: students and staff. | Объявление получат все в шале: ученики и сотрудники. |
| `ann-send-ask` ⚑ | Send to { $count -> [one] { $count } person *[other] { $count } people }? It arrives within about 10 minutes. | Отправить { $count -> [one] { $count } человеку *[other] { $count } людям }? Сообщение придёт примерно в течение 10 минут. |
| `ann-sent` / `ann-sent-to` | ✅ Sent. / Sent to { $count } (Fluent plural) | ✅ Отправлено. / Получателей: { $count } |
| `ann-limit` ⚑ | That's 3 announcements to this group in the last 24 hours. You can send the next one later. | Этой группе уже отправлено 3 объявления за последние 24 часа. Следующее можно будет отправить позже. |
| `ann-pin-none` / `-week` / `-month`, `ann-pinned-until`, `ann-unpin` | No pin / 📌 1 week / 📌 1 month, 📌 until { $date }, Unpin | Не закреплять / 📌 на неделю / 📌 на месяц, 📌 до { $date }, Открепить |
| `ann-delete-ask` ⚑ | Delete this announcement? It disappears from the app. Messages already delivered stay in people's chats. | Удалить объявление? Оно исчезнет из приложения. Уже доставленные сообщения останутся в чатах. |
| `settings-announcements` | 📣 Announcements from teachers and shalas | 📣 Объявления от учителей и шал |
| `invite-consent` +bullet | • { $name } can send announcements to all their students through the bot. You can mute them. | • { $name } может отправлять объявления всем своим ученикам через бота. Их можно отключить. |
| `shala-join-consent` +bullet | • The shala's staff can send announcements to members through the bot. You can mute them. | • Сотрудники шалы могут отправлять участникам объявления через бота. Их можно отключить. |
| `settings-privacy-sharing` +sentence ⚑ | Teachers on your list and your shalas can send you announcements; you can mute each one. | Учителя из твоего списка и твои шалы могут присылать объявления; каждый источник можно отключить. |

## 3. Domain, use cases, ports
**Domain** `domain/announcements.py` (pure):
```python
TEXT_MAX = 1000; PER_SOURCE_PER_DAY = 3; STALE = timedelta(hours=24)  # a safety bound after a tick outage, not a hold
FEED_DAYS = 30; KEEP = timedelta(days=90); PIN_DAYS = frozenset({7, 30})
class SourceKind(StrEnum): TEACHER = "t"; SHALA = "h"
@dataclass(frozen=True, slots=True) class Source: kind: SourceKind; id: UUID   # teacher account id or shala id
def normalize_text(raw: str) -> str | None   # strip; drop control chars except \n; ≤ 2 blank lines in a row; 1..TEXT_MAX code points, else None
def announcement_key(id: UUID) -> str        # "ann:<uuid>" (the ledger's dedupe key)
def due(now, created_at, zone: str | None, quiet: QuietHours) -> Send | None
    # None only if now ≥ created_at + STALE (never held for quiet hours, Q165).
    # Send(silent = zone is None or quiet.contains(local now), local_date).
    # The daily cap is not consulted (Q166).
def pinned(pinned_until: datetime | None, now) -> bool
```
**Policies** (`application/policies.py`), mirrored by SQL guards in the same statement (the `Guarded` pattern):
- `can_announce_to_students(actor)`: always the caller's own students. An empty audience → `InvalidAnnouncement`.
- `can_announce_to_shala(m: Membership | None)`: staff and (owner, or roles ∩ {admin, teacher, office}), the same set as `can_manage_schedule` (Q163).
- `can_manage_announcement(actor, author_id, m)`: the author, or for a shala source `_manages(m)` (owner or manager, for moderation).
- `can_view_announcements(source, …)`:
  - teacher source: a current link with me as the student;
  - shala source: any member.
  - Non-members and unlinked callers get `NotFound`.

**Use cases** `application/announcements.py` (the bot uses the read and mute ones; the API uses all):
- `SendAnnouncement.execute(principal, source, text, pin_days) -> Sent(id, audience, pinned_until)`. `normalize_text`, then one guarded insert, which does all of this:
  - checks the policy;
  - checks the rate limit: `count(*)` of the source's rows in the last 24 h < 3, soft under a race like the other caps. Delete is a hard delete, so **deleted announcements don't count** (Q173: delete and resend fixes a typo);
  - counts the **audience** (current members, muted ones included, the author excluded);
  - unpins the source's earlier pin when this one pins.

  It sends nothing itself; the tick delivers.
- `GetAnnouncements.execute(principal, source | None, page) -> Feed(items, muted: frozenset[Source])`:
  - my current sources, the last 30 days plus the live pin, pin first, then newest first;
  - each item carries the author's display name while they're still the teacher or staff, else none.
- `GetSentAnnouncements.execute(principal) -> tuple[SentItem, …]`: mine, the last 30 days, with `audience`.
- `PinAnnouncement.execute(principal, id, days: 0 | 7 | 30)` and `DeleteAnnouncement.execute(principal, id)` (a hard delete, idempotent).
- `MuteAnnouncements.execute(principal, source, muted: bool)`: keyed on the caller, so a forged id matches nothing.
- **Tick step** `DeliverAnnouncements` (called by `RunTick` after reminders, before the moon top-up, under the same deadline):
  1. `due(now, since=now−STALE, limit=2000)`: one statement, below.
  2. Per row, the domain `due`, then the existing `claim → Notifier.deliver(Announcement) → finish` (category `announcement`, key `ann:<id>`).
  3. `BLOCKED` → `mark_unreachable`; `RETRY_AFTER` stops the run.

**Ports:**
- `AnnouncementRepository` (`Storage.announcements`), one statement each: `create`, `feed`, `sent`, `set_pin`, `delete`, `set_mute`, `due`, `prune(before)`.
- `due` is one statement. It takes announcements with `created_at > since`, lateral-joined to the **live** audience:
  - teacher: `teacher_link` by `teacher_id`;
  - shala: `shala_student ∪ shala_staff` by `shala_id`, the author excluded.

  Each audience row must also meet three conditions:
  - its `created_at ≤ announcement.created_at`, so people who joined later get no push;
  - not muted;
  - `coalesce(notification_settings.announcements_on, true)`.

  It is joined to `account` (zone, locale), the Telegram `identity` and the reachable rule from `candidates`, minus final ledger rows. Order: `(created_at, account_id)`.
- `Notification` += `Announcement(id, source: Source, source_name, author_name, text, silent, local_date)`. The Telegram adapter renders it as plain text, with no `parse_mode`, `link_preview_options.is_disabled`, `disable_notification=silent` and the 10 s timeout. `RunTick.prune` also prunes announcements older than `KEEP`.

## 4. API (initData; `{code}` errors; `no-store`; additive; regenerate with `gen:api`)
| Method, path | Request → Response | Policy |
|---|---|---|
| `GET /api/v1/me/announcements` | `?source=t:<id>\|h:<id>&offset&limit≤20` → `{items: [AnnouncementOut {id, source: {kind, id, name}, author_name: str\|null, text, created_at, pinned: bool}], muted: [SourceRef]}` | own sources; 404 for a foreign `source` |
| `GET /api/v1/me/announcements/sent` | → `[SentOut {id, source, text, created_at, pinned_until: str\|null, audience}]` | own |
| `POST /api/v1/me/announcements` | `{source: {kind: "students"} \| {kind: "shala", id}, text, pin_days: 0\|7\|30}` → 201 `SentOut`. 404 (not a member). 403 `not_allowed` (a member without the role). 409 `announcement_limit`. 422 `invalid_announcement` (text, `pin_days`, empty audience) | `can_announce_*` |
| `PATCH /api/v1/me/announcements/{id}` | `{pin_days: 0\|7\|30}` → `SentOut` | `can_manage_announcement`; 404 |
| `DELETE /api/v1/me/announcements/{id}` | → 204, idempotent | `can_manage_announcement` |
| `PUT /api/v1/me/announcement-mutes/{kind}/{id}` | `{muted: bool}` → 204 | own link or membership; 404 |
| `PATCH /api/v1/me/notification-settings` | `+ announcements: bool \| null` (ADR-0021 partial write) | own |

- `ErrorCode` += `announcement_limit`, `invalid_announcement`.
- A shala manager's DELETE/PATCH of another author's item uses the same routes. `sent` lists only the caller's own items; managers moderate from the shala feed, where `AnnouncementOut` += `can_manage: bool`.
- Times are UTC instants. The client shows dates in the device's zone.

## 5. Bot (prefix **`b1:`**, free; ids are 22-char base64url uuids as in `h1:`; answer first; edit in place)
| Data | Meaning | Longest |
|---|---|---|
| `b1:l:<k>:<id>:<page>` | feed screen for a source (`k` = `t`/`h`), page 0–99 | 32 |
| `b1:m:<k>:<id>:<w>` · `b1:u:<k>:<id>:<w>` | mute · unmute. `w` = `n` (on the message: edit the markup only) or `l` (re-render the feed) | 31 |

- Reused: `t1:c` and `h1:c` gain the pin line and `[📣 Announcements]`. `t1:s` and `h1:c` get the web_app `[📣 Announce]` (by policy).
- A foreign or forged id, or an ended link → `NotFound`, which re-renders `/teachers`.
- Statements (middleware 1 included): feed 2, mute 2, card unchanged + 1 scalar subquery for the pin.

## 6. Migration `0024_announcements` (expand-only, down `0023`)
- `announcement(id uuid PK default gen_random_uuid(), author_id uuid NOT NULL → account ON DELETE CASCADE, shala_id uuid NULL → shala ON DELETE CASCADE, text text NOT NULL CHECK (char_length(text) BETWEEN 1 AND 1000), audience int NOT NULL CHECK (audience >= 0), pinned_until timestamptz NULL, created_at timestamptz NOT NULL DEFAULT now())`.
  - `shala_id` NULL means a teacher source.
  - Indexes: `(author_id, created_at)`, `(shala_id, created_at) WHERE shala_id IS NOT NULL`, `(created_at)` (tick, prune).
  - "One pin per source" is kept by the write statement, not an index, because pins expire.
- `teacher_link`, `shala_student`, `shala_staff` += `announcements_muted boolean NOT NULL DEFAULT false` (metadata-only on PG ≥ 11; dies with the link or membership).
- `notification_settings` += `announcements_on boolean NULL` (NULL = on, the default).
- `notification_delivery` category CHECK += `'announcement'`. Drop either spelling `IF EXISTS` and recreate (the 0005 pattern).
- Housekeeping:
  - FK names via `op.f()`; `is_account_gone` learns `announcement_author_id_fkey`.
  - Grants come from the default privileges.
  - The export coverage guard lists the table (§7).
  - Downgrade deletes the `announcement` ledger rows, then drops the columns and the table and restores the CHECK.

## 7. Cross-cutting checks
- **Time zones ✔:**
  - `created_at` and `pinned_until` are UTC instants.
  - Quiet hours are checked in the **recipient's** IANA zone at the tick. They decide only the sound, never the timing (Q165): inside them the message goes at once with `disable_notification`, outside them with sound. Mysore rooms open 5:30–6:30, so a closure note held until 07:00 would come too late. A recipient with no known zone (the provisional zone is never used for sends, as in `domain/notifications.py`) gets it at once, silently.
  - `STALE` = 24 h is a safety bound only: after a tick outage, anything older is never pushed (it is still in the feed).
  - The ledger's `local_date` is the recipient's date, or the UTC date with no zone.
  - The rate limit is a rolling 24 h, so it needs no zone.
  - Only **dates** are shown (the item date, "📌 until"): the viewer's local date in the bot, the device's in the Mini App. No time of day is shown, so no zone label is needed. If a time is ever added, it carries the `07:00 Almaty (UTC+5)` label.
- **Privacy ✔:**
  - **The text is not encrypted** (ADR-0038). It is authored for broadcast to up to ~1000 people, it is copied into each recipient's Telegram chat, it isn't data about the reader, and ADR-0016 seals only the owner's private data (🌸, diary, check-in notes). `ann-hint` asks authors to keep others' personal details out.
  - **The sender learns nothing new:** `audience` counts muted people too and is fixed at send time. There are no delivered or read counts: with a 1-student audience they would reveal a mute or a blocked bot.
  - A recipient sees the author's name and the source, already visible to them through the link or the shala card.
  - **Co-students are never revealed:** no recipient list, and no count is shown to recipients.
  - Leaving or being removed stops pushes at the next tick and closes the feed.
  - The text is never logged; the adapter logs only the id and the status.
  - Plain text with no `parse_mode`, so names and text can't inject markup. Telegram auto-links bare URLs; previews are off.
  - **Export:** `announcements_sent: [{to: "students"|"shala", shala, text, created_at, pinned_until}]` for my own. Received ones aren't exported (someone else's text). Mutes appear as a flag on my links and shalas. The ledger's rows already export as `reminders` (category `announcement`, no text).
  - **Delete:** the author's account cascades their announcements, which leave every feed, and pending pushes stop. A shala delete cascades its announcements.
  - **Retention:** 90 days, then pruned by the tick.
- **i18n ✔:**
  - The message renders in the **recipient's** locale (the header and buttons; the text stays as written). The sender's screens use the sender's locale.
  - RU plurals for counts. Names are never declined (colon/dot forms).
  - en + ru parity in `bot.ftl` and `app.ftl`.
  - The banned-word list (no guilt, no urgency) applies.
- **Responsiveness ✔:**
  - Sending is 1 guarded statement (+ the principal load); no outbound call in the request.
  - The bot feed and mute are 2 statements each.
  - The tick adds 1 `due` statement + 2 per recipient (claim, finish), sequential like reminders.
    - Expected at ~15–25 sends/s: a 1000-person shala spans 2–3 ticks, so the last recipients wait ≤ ~30 min. A 429 stops the run and the next tick resumes.
    - **Measure** with 1000 seeded members and Telegram stubbed (statements, the tick time per 100 sends). If a big shala needs > 3 ticks, batch the claims (`INSERT … VALUES (…×50) ON CONFLICT … RETURNING`) or allow ≤ 8 concurrent sends (already allowed by ADR-0018).
  - Mini App: a new lazy chunk (≈ 2–3 KB gzip), initial JS unchanged except the entry buttons; `check:bundle`; RU at 320 px.

## 8. Test plan
- **Domain:**
  - `normalize_text`: blank; 1000 vs 1001 code points (an emoji counts as one); control chars dropped, `\n` kept; 3+ blank lines collapsed.
  - `due`:
    - inside quiet hours (across midnight, e.g. 05:30 with quiet 22–07) → sent now, silent; outside → sent now, with sound; never None for quiet hours;
    - the quiet-hours boundary (07:00 exactly → sound);
    - a DST day (Berlin 02:30);
    - no zone → silent;
    - exactly 24 h → None;
    - the cap is never consulted.
  - `pinned` at the boundary; the key format.
- **Policies (role × action matrix):**
  - owner, manager, teacher and front desk can send to the shala; an assistant and a student get `NotAllowed`; a non-member gets `NotFound`;
  - manage = the author or the owner/manager;
  - a teacher sends only to their own students;
  - a co-student, the teacher's teacher (one hop) and a reversed link can't read a teacher feed.
- **Use case (fakes, fixed clock):**
  - **Send:**
    - the 4th within 24 h → `AnnouncementLimit`; after deleting one of the 3, a resend succeeds;
    - the audience counts muted members and excludes the author;
    - a pin unpins the previous one of the same source only;
    - an empty audience → `InvalidAnnouncement`;
    - **no `Notifier` call during send**.
  - **Feed:** pin first; 30-day window; a removed author's name → None; a foreign source → `NotFound`.
  - **Tick:**
    - Who is pushed: a member who joined after the send gets nothing; a muted one or one with the global switch off gets nothing; a blocked one → `mark_unreachable`.
    - A recipient in quiet hours (05:30 local) gets it **in the same tick, silently**; one outside quiet hours with sound; both in one run. A 25 h old item never sends.
    - No day, rest or reminder state changes after a closure-like announcement (§1).
    - The cap: an announcement sends with `sent_today = cap`, **and counts** (a later practice reminder that day is skipped).
    - Running: `RETRY_AFTER` stops the run; the deadline is respected; a second tick sends no duplicates.
    - Kiritimati vs Honolulu quiet hours on one instant.
- **DB (real Postgres):**
  - `due` is one statement with the live audience (leave/remove between ticks → no push; author deleted → no rows).
  - The ledger claim makes it at most once under two concurrent ticks. The CHECK accepts `announcement`.
  - Rate-limit race: at most one overshoot. Cascades (author, shala, member).
  - The mute columns default false. Prune at 90 days.
  - App role: create, pin, delete, mute, tick.
  - 0024 up/down/up; `alembic check`.
  - Export: own sent only; no received text and no other person's id.
- **API:**
  - 401; exact key sets; 201/403/404/409/422 per §4; a non-member 404 equals an unknown id.
  - A shala manager can delete another's item; a teacher can't.
  - Mute PUT idempotent; the `notification-settings` partial write.
  - `no-store`; OpenAPI → the TS client builds.
- **Bot (through the webhook, fake use cases):**
  - The rendered message in EN/RU, both heads, plain text, preview off; `disable_notification` exactly when the `Send` says silent.
  - Mute and unmute edit the markup in place; `b1:l` paging and the ~3800-character stop.
  - The pin line and the button on `t1:c`/`h1:c`; `[📣 Announce]` only per policy.
  - A forged id or an ended link → `/teachers`; every value ≤ 64 bytes (assert 32); `answered` first.
  - Consent screens with the new bullets ≤ 4096 with 64-character names; the banned-word and RU gendered-ending greps.
- **Mini App (Vitest, also `TZ=UTC`):**
  - Compose: counter, 1000 limit, pin select, the date hint, the shala hint only for a shala source, confirm/cancel, 409 keeps the text, success clears it.
  - The sent list: pin/unpin, delete confirm.
  - The feed: pin first, source chips, the mute switch, empty state.
  - The Settings switch; RU 320 px; `check:bundle`.
- **Architecture:** import-linter: `application.announcements` imports no practice/diary/check-in/progression/teacher-view port; aiogram only in `bots/telegram`.
- **Owner on a phone:** a teacher announces to 2 test students; one mutes; a shala front desk announces with a 1-week pin; a recipient in quiet hours gets it at once without a sound.

## 9. Later
Single-student and class-attendee audiences (SC-04/05) · automatic cancellation notices, and any link from an announcement to rest days (Q122; a closure announcement never counts as rest today) · edit, and deleting delivered messages (store `message_id` per ledger row) · photos · bot compose (ForceReply + draft) · scheduled sends · Telegram group/channel posting (Phase 4) · a Home row for unseen announcements.

## 10. Decisions (owner, 2026-11-09: all as recommended except Q165 and Q173, changed)
- **Q162 Audience.** ✅ A teacher → **all** their linked students; a shala → **everyone in it** (students + staff, minus the author). No single student (that's a chat) and no class attendees (no attendance data until SC-04/05).
- **Q163 Who sends for a shala.** ✅ The owner, Manager, Teacher and Front desk (the SC-02 Q118 schedule set); not Assistants.
- **Q164 Delivery path.** ✅ Through the existing 10-minute tick and delivery ledger (≤ 10 min, a 1000-person shala ≤ ~30 min), not an immediate send in the tap. Cloud Run can't fan out after the response, and the ledger gives at-most-once, retries and blocked-bot handling for free (ADR-0038).
- **Q165 Quiet hours (changed, ashtanga-expert must-fix).** ✅ **Never held.** During the recipient's quiet hours it is delivered at once with `disable_notification=True`; outside them with sound; with no known zone at once, silently. Mysore rooms open 5:30–6:30, so a closure note held until quiet hours end would arrive too late. (The draft held it, with a 24 h grace.)
- **Q166 Daily cap.** ✅ Announcements **ignore** the cap (a person, not the app, is speaking) but **count toward it**, so that day's later reminders may yield.
- **Q167 Opt-out.** ✅ A **per-source mute** (on every message, the feed and the Mini App) plus one **global NT-01 switch** in Settings. Muting stops only the push; the feed still shows them; the sender is never told.
- **Q168 Pinning.** ✅ **In-app only**: one pin per source, 1 week or 1 month, expiring by itself; the author can unpin any time. No Telegram `pinChatMessage` (a second call per recipient, a stored message id, and a teacher taking over the top of the student's own chat).
- **Q169 Content.** ✅ **Plain text, ≤ 1000 characters**, line breaks allowed; bare URLs work (Telegram auto-links them), previews off; no formatting, photos or files.
- **Q170 Edit and delete.** ✅ **No editing.** Delete (author, or the shala's owner/manager) removes it from every feed and stops pending pushes; messages already delivered stay, and the confirm says so. A typo means delete and send again.
- **Q171 Feed.** ✅ Recipients see the **last 30 days plus the pin** of their current sources, including items sent before they joined (useful for "closed in August"); pushes go only to people who were members when it was sent.
- **Q172 Sender stats.** ✅ Only "Sent to N" (the audience at send time, muted included). No delivered or read counts: they would expose mutes and blocked bots.
- **Q173 Abuse limit (changed).** ✅ **3 per source per rolling 24 h**, plus the 1000-character cap; no per-author global cap. **Deleted announcements don't count** toward the 3 (delete and resend fixes a typo); a hard delete gives this with no extra column.
- **Q174 Privacy and retention.** ✅ **Not encrypted** (broadcast text, already in every recipient's Telegram chat; ADR-0016 is for the owner's private data). Pruned after **90 days**. The author's own sent items are in their export; received ones aren't.
- **Q175 Consent.** ✅ Add one bullet each to `invite-consent` and `shala-join-consent`, plus the Settings privacy line. **No re-consent**: nothing about the student is exposed, and every message carries Mute.
- **Q176 Surfaces.** ✅ **Compose in the Mini App only** (bot web_app buttons open it, as SC-01 Q103). The bot receives, lists and mutes. **No new slash command** (no `set_webhook.py` run).
- **Closure announcements (owner, new).** ✅ An announcement never marks a day as rest or changes any day, auto-rest or reminder state; text only. Revisit with Q122 (§1, §9).
- **Copy (ashtanga-expert, accepted).** ✅ `ann-hint` asks for a named day and time, not "tomorrow"; `ann-hint-shala` says it goes to everyone in the shala; the RU `ann-muted` wording is the expert's; `ann-send-ask` no longer mentions quiet hours.

## 11. Build notes (2026-11-09, reviewed)
Deviations from §2–§8, all reviewed (code-reviewer, ux-writer):
1. **API shape.** `POST /me/announcements` takes `{to: "students" | "shala", shala_id?, text, pin_days}`; the feed filter is `?kind=teacher|shala&id=<uuid>&offset&limit≤20`; `FeedOut` is `{items, sources: [{kind, id, name, muted}], more}` (the mutes ride on `sources`); `AnnouncementOut.pinned_until` (live pins only) replaces `pinned: bool`. `ShalaMeOut.announce` tells the Mini App who may announce. `NotificationSettingsOut.announcements` is the NT-01 switch. FastAPI's own 422s (e.g. `pin_days: 5`) carry `detail`, not `invalid_announcement`.
2. **Pin rights.** Pin/unpin = a shala owner or manager, or the author *while still speaking for the source* (`can_pin_announcement`): an ex-front-desk or a teacher demoted to assistant can delete their item but not pin it over the shala's current pin. Delete stays `can_manage_announcement`. Both guards are built from the policies' membership codes and re-checked in the use case.
3. **Bot feed page = 3 items**, never cut: three whole 1000-character items always fit one message, so the §2 "~3800 characters" stop isn't needed and nothing is lost between pages.
4. **Cards.** `t1:c` and `h1:c` read the live pin through the feed use case in parallel with the card (`asyncio.gather`, as `/teachers` already does), not a scalar subquery: one more round trip, no added latency. Mute answers the callback with its toast after the write (3 statements with `w=l`).
5. **Mini App.** Compose and the sent list live in one lazy chunk (`Announcements`); entry points: My students `📣 Announce`, the shala card (`📣 Announcements`, `📣 Announce` per `me.announce`), Teachers and students `📣 Announcements` (with a teacher), and the bot's web_app `?open=announce[&shala=<id>]`. Chips refetch per source; "Show more" pages by 20. Managers unpin/delete from the feed (`can_manage`). The Settings switch shows once there is a teacher or a shala.
6. **Copy.** The staff consent got the same mute bullet as the student consents. ux-writer: short Mute/Unmute labels (`🔕 Mute` / `🔕 Не присылать`); RU `ann-send-ask` uses «Получателей: N» (no inflected count); `ann-limit` says the text is kept; `ann-delete-ask` says pending sends stop.
7. **Edge case (accepted).** A student promoted to staff gets a new membership row: their mute resets, and announcements sent before the promotion aren't pushed to them (they stay in the feed).
