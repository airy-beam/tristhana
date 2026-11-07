# ID-04: teacher–student links (with the ID-03 teacher capability)

- Status: **accepted** (owner, 2026-11-07; ashtanga-expert fixes applied) · Date: 2026-11-07 · Size M, Phase 3 (first feature)
- Requirements: **ID-04** (graph, 0..n teachers, one primary, invite link/QR `t.me/bot?start=t_<code>`, either side unlinks). **ID-03** capability part only ("teacher" = has students). Touches UI-01 (`/start`), ID-06 (name, privacy copy), ST-09 (export, delete), NT-01/02, MD-03 (explicit Mysuru, §7). Prepares ST-06, MD-02, NT-03, SC-03, PR-08 teacher marks, SC-01 (§11).
- Related: ADR-0008, 0012, 0015, 0018, 0019, 0026, 0027. New: **ADR-0030** (accepted).

## 1. Scope
**In:** `teacher_link` and `teacher_invite` tables; a personal invite (link, QR, Telegram share, rotate); a student consent screen on `/start t_<code>`; lists of my teachers and my students; choosing the main teacher; removal from either side; a silent note to the teacher on a new student; export and delete coverage; copy that becomes false; storing an explicit Mysuru choice (§7).
**Out:** any read of another person's practice data (ST-06), so **`can_view_check_ins`, `can_view_diary`, `can_view_progression` stay owner-only**; moon inheritance (MD-02); announcements (NT-03); schedules (SC-03); teacher marks (PR-08 Phase 3); shalas and shala roles (SC-01); the ID-05 badge; student-created invites; a block list; invites through the REST API or the Mini App's `startapp`; a history table of ended links; co-students or a teacher's other teachers (never shown).
**The one new exposure (Q2):** linked people see each other's display name. Nothing else changes until ST-06.

**Consent model (ADR-0030):** a link exposes the *student's* data, so the student taps last, every time. The code only opens a confirm screen. It gives its holder nothing of the teacher's beyond a name, and nothing of anyone else's. This makes a leaked code a nuisance rather than a data leak, and it drives Q4 and Q9.

**Vocabulary (Q15, S3, S5):** "teacher" / «учитель» for the relationship, never guru, instructor or coach. «Преподаватель» only for formal titles and shala job roles; the verb «преподаю» is fine. The UI says "Main teacher" / «Основной учитель»; code keeps `primary`. RU copy avoids «отвязаться» and «связь». "Unlink" is an internal word; the UI says "Remove".

## 2. Flows and copy
**Student (bot).** The link or QR opens the bot; the middleware creates the account as usual (ID-01), in the negotiated language.
```
(consent text, §2 Copy)
[✅ Confirm] [Not now]
[🗣 Русский]
```
- **Stateless:** the code travels in `t1:y:<code>`, so a new person loses nothing, and no pending row exists. `[🗣]` re-renders this screen in the other language (`t1:l:<locale>:<code>`, the same `UpdateProfile`); the usual `o1:` would drop the invite.
- **The student's real name is shown** (decided): "sees your name ({ $me })". The consent then states the exact exposure, which is often a Telegram first name the person never chose here. It costs nothing (the account is already loaded). With no name, the parenthesis drops out.
- **Either answer edits in place into the normal `/start` grid**, with `invite-linked` on top after ✅. First log = 1 extra tap, nothing skipped. A decline stores nothing and tells no one.
- **Second and later links (S2):** `[⭐ Make main]` sits under `invite-linked`, above the grid. The default is unchanged if ignored.
- `/start t_<code>` states, each the `/start` grid with one line on top: `invite-invalid` (unknown or rotated), `invite-own`, `invite-already`, `invite-full` (either cap). Other payloads stay ignored.

**Teacher (bot).** `/teachers`, one screen for both sides: teachers as rows, `[👥 My students (12)]`, `[➕ Invite students]`, `[Open the app]`. **With 0 students** the invite button reads "I teach: invite students" / «Я преподаю: пригласить учеников» and goes last. It is a label, not a toggle.
- **Main teacher (S2, S3):** ⭐ shows only with two or more teachers. The screen separates a choice from the default: `links-main-chosen` vs `links-main-auto`.
- **Invite screen:** the link in plain text, `invite-hint`, `[📤 Share]` (URL button to `t.me/share/url`), `[🔳 QR code]` (sends a PNG to forward or print), `[🔄 New link…]`.
- **New link:** one confirm (`invite-new-ask`), then the old link and QR die. Existing links stay. Rotating and not sharing **is** the revoke, so there is no separate one.
- **Teacher card:** `[⭐ Make main]` (two or more teachers, not the current main), `[Remove…]`. **Removing the main teacher names who takes over** (`link-next-main`). **Student list:** 10 per page, card `[Remove…]`. One confirm step each.

**Mini App.** A `👥 Teachers and students` row in Settings opens a lazy screen with the same three parts and the same ⭐ and takeover rules. Remove via native `showConfirm`; QR as `<img src="data:…">` on white (CSP already allows `data:`); Copy; Share through a new `openTelegramLink` wrapper. Writes are not optimistic; 409 refetches. No Home row until ST-06 gives teachers a reason (Q12).

**Copy** (owner-accepted wording unless marked ⚑; ⚑ = drafted here, ux-writer pass before release; «ты»; RU gender-neutral; **names stay nominative**).

Consent screen = `invite-ask` + `invite-consent` + `invite-know-them` + `invite-not-told`:

EN:
```
🤝 { $name } sent you an invite. Add them to your teachers?

If you confirm:
• { $name } sees your name ({ $me }), nothing more for now.
• Later, when teachers get their own screen, they'll also see what you log from today on: practice or rest and your practice length. They'll see your last asana as marked in your log too. All rest looks the same, whatever the reason.
• Any teacher on your list will then also be able to mark a new asana for you. You can undo it.
• Check-ins, diary notes and the reason for a rest stay private unless you choose to share them.
• You can remove { $name } from your list any time in /teachers. No one gets a message.

Anyone can choose any name here, so confirm only if you know this person. If you tap Not now, { $name } isn't told.
```
RU:
```
🤝 { $name } отправляет тебе приглашение. Добавить в список твоих учителей?

Если подтвердить:
• { $name } увидит твоё имя ({ $me }), пока больше ничего.
• Позже, когда у учителей появится свой экран, будет видно и то, что ты отмечаешь с сегодняшнего дня: практика или отдых и объём практики. Ещё будет видна последняя асана по отметкам в журнале. Любой отдых выглядит одинаково, какой бы ни была причина.
• Тогда же любой учитель из твоего списка сможет отметить тебе новую асану. Это можно отменить.
• Самочувствие, заметки и причина отдыха остаются личными, если ты не решишь ими делиться.
• Убрать из списка можно в любой момент в /teachers. Сообщений никто не получит.

Имя здесь может выбрать любой, поэтому подтверждай, только если знаешь этого человека. Если нажать «Не сейчас», { $name } об этом не узнает.
```
**Size check:** about 760 characters EN and 830 RU before names; with `$name` (×4 EN, ×3 RU) and `$me` at the 64-character maximum, about 1,080 and 1,090. Well under Telegram's 4096, in one message. Estimated by hand; a test pins the worst case. "From today on" is what makes "No practice" and unlogged days both blank to a teacher (B1).

| Key | EN | RU |
|---|---|---|
| `invite-accept` / `invite-decline` | ✅ Confirm / Not now | ✅ Подтвердить / Не сейчас |
| `invite-linked` ⚑ | ✅ { $name } is on your list of teachers now. | ✅ { $name } теперь в списке твоих учителей. |
| `invite-already` ⚑ | { $name } is already on your list of teachers. | { $name } уже в списке твоих учителей. |
| `invite-own` ⚑ | This is your own invite link: share it with your students. | Это твоя ссылка-приглашение: поделись ею с учениками. |
| `invite-invalid` | This invite link no longer works. The person who shared it can send a new one. | Эта ссылка больше не работает. Новую может прислать тот, кто ею поделился. |
| `invite-full` ⚑ | This link can't add a teacher right now. | Сейчас по этой ссылке не получится добавить учителя. |
| `link-student-joined` ⚑ | 👥 { $name } is on your list of students now. | 👥 { $name } теперь в списке твоих учеников. |
| `invite-hint` | Share this link or QR code. Each student confirms for themselves. ⚑ | Поделись ссылкой или QR-кодом. Каждый ученик подтверждает сам. |
| `invite-share-text` | My link to add me as your teacher in Tristhana. The bot shows what I'd see before you confirm. | Моя ссылка, чтобы добавить меня как учителя в Tristhana. Перед подтверждением бот покажет, что мне будет видно. |
| `invite-new-ask` ⚑ | Get a new link? The old link and QR stop working. People already on your list stay. | Сделать новую ссылку? Старая ссылка и QR перестанут работать. Те, кто уже в списке, останутся. |
| `invite-qr-caption` ⚑ | Scan to add me as your teacher in Tristhana. | Отсканируй, чтобы добавить меня как учителя в Tristhana. |
| `link-unlink-ask` | Remove { $name } from your teachers? They won't get a message, but you'll no longer be on their list. | Убрать из списка учителей: { $name }? Сообщений никто не получит, просто в списке учеников тебя больше не будет. |
| `link-next-main` ⚑ | { $name } becomes your main teacher. | Основным учителем станет: { $name }. |
| `link-remove-ask` | Remove { $name } from your students? They won't get a message. | Убрать из списка учеников: { $name }? Сообщений никто не получит. |
| `links-empty` | No teachers on your list. Your log works the same either way. | Учителей в списке нет. Журнал практики работает и так. |
| `links-no-students` ⚑ | No students on your list. | Учеников в списке нет. |
| `links-primary-hint` | ⭐ marks your main teacher. You can change it any time. | ⭐ — твой основной учитель. Поменять можно в любой момент. |
| `links-main-chosen` ⚑ | ⭐ Main teacher: { $name } | ⭐ Основной учитель: { $name } |
| `links-main-auto` ⚑ | ⭐ Main teacher: { $name } (first on your list) | ⭐ Основной учитель: { $name } (в начале списка) |
| `links-title`, `command-teachers` ⚑ | 👥 Teachers and students; My teachers and students | 👥 Учителя и ученики; Мои учителя и ученики |
| `link-no-name` ⚑ | (no name) | (без имени) |
| `export-readme-links` ⚑ | teacher_links in data.json: your teachers and students, without names, so this list holds no one else's details. | teacher_links в data.json: твои учителя и ученики без имён, поэтому чужих данных в этом списке нет. |

**Buttons** (⚑ except the first three): `links-make-main` ⭐ Make main / ⭐ Сделать основным · `links-remove` Remove… / Убрать… · `links-invite-first` I teach: invite students / Я преподаю: пригласить учеников · `links-students` 👥 My students ({ $count }) / 👥 Мои ученики ({ $count }) · `links-invite` ➕ Invite students / ➕ Пригласить учеников · `links-remove-yes` Remove / Убрать · `invite-share` 📤 Share / 📤 Поделиться · `invite-qr` 🔳 QR code / 🔳 QR-код · `invite-new` 🔄 New link… / 🔄 Новая ссылка… · `invite-new-yes` 🔄 Yes, new link / 🔄 Да, новая ссылка · `invite-copy` Copy link / Скопировать ссылку · `invite-copied` Copied / Скопировано. Reused: `log-back`, `start-switch-language`, `start-open-app`, `page-prev`/`page-next`. `$name` falls back to `link-no-name` when `display_name` is null or has nothing visible (`shown_name`: Telegram refuses a button of blanks, code review). RU `$count` plurals go through Fluent where the count stands in a sentence.

**Existing strings**
| Key | Verdict |
|---|---|
| `settings-privacy-sharing` (app) | **Replace.** The old line contradicts the projection table. EN: "Your log is yours. A teacher on your list sees your name. When teachers get their own screen, they'll also see what you log: practice or rest, your practice length and your last asana. A teacher on your list will also be able to mark a new asana for you, and you can undo it. Check-ins, diary notes and the reason for a rest stay private unless you choose to share them. You can remove a teacher from your list any time." RU: «Твой журнал принадлежит тебе. Учитель из твоего списка видит твоё имя. Когда у учителей появится свой экран, будет видно и то, что ты отмечаешь: практика или отдых, объём практики и последняя асана. Учитель из твоего списка также сможет отметить тебе новую асану, а ты сможешь это отменить. Самочувствие, заметки и причина отдыха остаются личными, если ты не решишь ими делиться. Убрать учителя из списка можно в любой момент.» |
| `settings-name-hint` (app) | **Replace:** "How I greet you, and the name your teachers and students here see. Leave it empty to use your Telegram name." / «Так я к тебе обращаюсь, и это имя видят твои учителя и ученики. Оставь пустым, и я возьму имя из Telegram.» |
| `delete-explain` (bot, app) | **Extend** the list with "teacher and student lists" / «списки учителей и учеников». |
| `diary-empty` (bot, RU) | **Align (Q15):** «…что сказал учитель, новая асана или просто мысль.» Update `backend/tests/infrastructure/test_i18n.py:491-492` and `backend/tests/bots/test_diary_bot.py:571-572`. |
| `diary-private-hint` (app, RU) | **Align (Q15):** «Дневник личный: учителя его не видят.» Update `miniapp/src/i18n/bundles.test.ts:310`. EN unchanged. |
| `export-readme-ladies`, `settings-privacy-ladies`, `log-private-note` | True today and after this feature. **Keep**; re-check at ST-06. |

## 3. Domain, use cases, ports
`domain/teacher_links.py` (pure):
```python
MAX_TEACHERS = 20; MAX_STUDENTS = 500; CODE_LENGTH = 16
class InviteState(StrEnum): OPEN, OWN, ALREADY, FULL     # None = unknown code
@dataclass(frozen=True, slots=True)
class Linked: id: UUID; name: str | None; chosen_primary: bool; linked_at: datetime
def parse_invite(payload: str | None) -> str | None      # "t_" + 16 alphanumerics, else None
def invite_url(bot_username: str, code: str) -> str
def invite_state(me, teacher_id, linked, my_teachers, their_students) -> InviteState
def effective_primary(teachers: Sequence[Linked]) -> UUID | None
def next_primary(teachers, removing: UUID) -> UUID | None  # who takes over; None = no change
def teaches(student_count: int) -> bool                  # ID-03; SC-01 adds shala teaching
```
- **ID-03:** no role column and no "I teach" toggle (Q10). `teaches` is derived, and anyone may open the invite screen. Being a practitioner is unconditional.
- **Graph rules:** a self-link is refused (`OWN`, plus a DB CHECK). A duplicate is a no-op, with no second note. **Cycles are allowed** (A teaches B, B teaches A: peers do this), and nothing here walks the graph. Rights are **one hop, never transitive**: my teacher's teacher sees nothing of me. Caps: 20 teachers per student, 500 students per teacher, soft (a race can overshoot by a few).
- **Primary (Q7, S2):** the first teacher is main with no write. `effective_primary` = the explicitly chosen one, else the oldest link (`created_at`, then `teacher_id`). When the main teacher leaves, or their account is deleted, the next oldest takes over at read time. That needs no promotion write and no trigger, and it survives ST-09's one-statement cascade. **A teacher never learns whether they are main:** no field, note, export value or screen tells them.
- **Removal:** a hard delete by either side, silent on both (Q8). Keeping no record of ended links is the privacy default. A re-link is a new row with default privacy and a new `linked_on`, so future per-link opt-ins can't come back by accident. The invite still works afterwards, but only the student's tap uses it. **Access never ends by itself, for now:** a visiting teacher stays on the list until someone removes them.
- **Code:** one per teacher, reusable, no expiry, 16 alphanumerics ≈ 95 bits (Q4), payload 18 of 64 characters. Letters and digits only, because a trailing `-` or `_` may drop out of auto-linked text. Generated by a `CodeSource` port (`secrets`), so the domain stays pure.

Port `TeacherLinkRepository` (`application/ports/teacher_links.py`, on `Storage.teacher_links`):
- `preview(code, me) -> InvitePreview | None`: teacher id and name, already linked, both counts; 1 statement.
- `accept(code, me, caps, linked_on) -> Accepted | None`: one CTE; `INSERT … ON CONFLICT DO NOTHING` gated on the caps and `teacher <> me`; returns `created`, `already`, `full`, the student's teacher count, and the teacher's id, name, locale and Telegram id (join on `identity`). `already` can be False on a duplicate: the loser of a double tap doesn't see the winner's row, so the bot shows `invite-full` only when `full` is set (code review).
- `overview(me) -> Links`: teachers and students with names, ≤ 520 rows; 1 statement.
- `invite(me, new_code) -> str`: get or create (`ON CONFLICT (account_id) DO UPDATE` as a no-op, `RETURNING code`), so a race yields one code. `rotate(me, new_code) -> str`.
- `set_primary(me, teacher_id) -> bool`: **one transaction, two UPDATEs: clear, then set.** A single-`UPDATE` flip is unsafe: a non-deferrable partial unique index is checked per row, so it can fail on row order. 0 rows set = rollback, `NotLinked`. A concurrent 23505 on `teacher_link_one_primary` → `LinksChanged`, last tap retries.
- `unlink(student, teacher) -> bool`: 1 statement, idempotent.

Use cases (`application/teacher_links.py`, both adapters except where noted): `PreviewInvite`, `AcceptInvite` (bot only for now, Q12; computes `linked_on` from the clock and the caller's zone), `GetLinks`, `GetInvite`, `RotateInvite`, `SetPrimaryTeacher`, `RemoveTeacher`, `RemoveStudent`. Exceptions never carry the code. `AcceptInvite` sends the note only when `created`, through **`Notifier.tell_student_joined(recipient, name)`** (same shape as `send_export`, so the tick's `Notification` union doesn't change).

**Join note (Q11):** a direct one-off, always `disable_notification=True`, 3 s timeout. It skips the ledger and the cap. Silence covers quiet hours without zone maths, and a roomful of students scanning at once makes no noise. No retry: the list is the record. `BLOCKED`/`FAILED` are ignored and never reach the student; `mark_unreachable` isn't called (the tick owns that). `[👥 My students]` on the note. Removal and account deletion send nothing.

**Policies** (`application/policies.py`): `can_unlink(actor, student_id, teacher_id)` = either side; `can_choose_primary(actor, student_id)` = the student; `can_manage_invite(actor, owner)` = the owner. The three `can_view_*` are untouched and a test pins that.

`is_account_gone` matches only `*_account_id_fkey`, so it must also match `teacher_link_student_id_fkey`. A 23503 on `teacher_link_teacher_id_fkey` means the teacher was deleted mid-tap: `accept` returns None → `invite-invalid`.

**Export/delete (ST-09):**
- `teacher_link` goes in `EXPORTED_TABLES`: `data.json` gains `teacher_links: [{other_side: "teacher"|"student", primary: bool|null, linked_at}]` for both directions, in one extra statement selecting only `student_id = :me`, the effective primary and `created_at`. `primary` is null on rows where I am the teacher. **No name or id of the other person** (the `marked_by` rule, Q14). The schema stays `/1` (additive, as GM-01). No new CSV.
- `teacher_invite` goes in `EXCLUDED_TABLES`: "a live credential, not personal content; an export may be shared".
- Delete: both FKs cascade. The other side gets no message and the person vanishes from their list; their effective primary falls through. Existing `marked_by` still becomes `unknown`.

## 4. API (initData auth; `{code}` errors; `Cache-Control: no-store`; `gen:api`)
| Method, path | Request → Response | Policy |
|---|---|---|
| `GET /api/v1/me/links` | → `LinksOut {teachers: [{id, name, primary, primary_chosen, linked_at}], students: [{id, name, linked_at}]}` | own |
| `POST /api/v1/me/invite` | `{rotate?: bool}` → `InviteOut {url, qr}` (`qr` = PNG data URI); get-or-create when `rotate` is false | `can_manage_invite` |
| `PUT /api/v1/me/teachers/{id}/primary` | → `LinksOut`; 404 `not_linked`; 409 `links_changed` | `can_choose_primary` |
| `DELETE /api/v1/me/teachers/{id}` | → 204, idempotent | `can_unlink` |
| `DELETE /api/v1/me/students/{id}` | → 204, idempotent | `can_unlink` |

`ErrorCode` += `not_linked`, `links_changed`. `linked_at` is UTC and only sorts; the UI shows no dates. `students[]` has no primary field. **The code never appears in a URL or query string** (Cloud Run logs URLs), and the client never builds the link. A new **`TELEGRAM_BOT_USERNAME`** setting builds it, because no username is configured today; empty hides the invite in dev.

## 5. Bot (prefix **`t1:`**, free; distinct from the `t_` payload; ≤ 41 bytes; answer first, edit in place)
| Data | Meaning |
|---|---|
| `t1:y:<code>` · `t1:n` · `t1:l:<locale>:<code>` | confirm · not now · language on the consent screen |
| `t1:o` · `t1:s:<page>` | teachers screen · my students |
| `t1:c:<uuid>` · `t1:p:<uuid>` · `t1:u:<uuid>` · `t1:x:<uuid>` | teacher card · make main (then the teachers screen) · remove ask · remove |
| `t1:v:<uuid>` · `t1:r:<uuid>` · `t1:z:<uuid>` | student card · remove ask · remove |
| `t1:i` · `t1:q` · `t1:w` · `t1:wy` | invite screen · send QR · new link ask · new link |

- `on_start` takes `CommandObject`, calls `parse_invite(command.args)` and hands off to `LinkScreens`, with no logic of its own. `StartScreens.start` gains an optional lead line and lead row. Screens and parsing live in new `teacher_links.py` and `teacher_links_callbacks.py`, registered before the catch-all.
- A uuid in callback data is not a capability: every write is keyed on the caller's account, so a forged id matches no row and just re-renders the list.
- QR: `t1:q` awaits `answer_photo` directly (a file can't be a webhook reply, ADR-0012).
- `/teachers` joins `COMMANDS` in `set_webhook.py` and `/help`.

## 6. QR (Q13)
**Server-side, with `segno`** (pure Python, no dependencies, native PNG; 76.5 KB wheel for 1.6.6), behind a `QrCodes` port in `infrastructure/qr.py`, lazy-imported, with an import-linter rule like tzfpy's. One dependency serves both surfaces, gives bot-only teachers a QR, and yields a PNG that can be forwarded or printed for the shala wall, which a Mini App canvas can't do well. **Mini App bundle: 0 KB for QR.** Image: under 1 MB expected, but the notes' last figure (~245 MB) predates tzfpy, so check it against the 250 MB limit in `container-smoke.sh`.

## 7. Explicit Mysuru choice (`application/moon.py`)
**Bug:** `SetMoonLocation` stores `None` when the slug is the default, so choosing Mysuru looks like never choosing. MD-02 inherits only for people who never chose, so a deliberate Mysuru choice would be overridden by a teacher's city.
**Fix:** store what was chosen; `None` still means "back to the default". Drop the `stored` line and update the docstring. No migration: the CHECK already accepts `mysuru`.
**Every reader of `moon_location`, checked:**
| Reader | With `"mysuru"` |
|---|---|
| `application/days.py:107`, `stats.py:62`, `tick.py:98` (through `db/notifications.py:234`), `export.py:199`, `bots/telegram/settings.py:207`, `moon.py:225`, `api/v1/days.py:114` | Same city as NULL: `cities.get(None)` is the default. No change. |
| `application/moon.py:52-55`, `api/v1/moon.py:202-203`, `application/export.py:205` | `explicit` true, export `default: false`. This is the point of the fix. |
| **`bots/telegram/moon.py:182`** | **Must change.** `not zone_known and explicit` would now offer "Use Mysuru time?", which MD-03 forbids ("Picking Mysuru never sets a zone"). Add `and v.city is not cities.default`. |
| Mini App | Reads `location.slug` only; `explicit` appears in test mocks only, and `useSetMoonLocation` always sends a slug. No change. |

- **Existing test that changes:** `backend/tests/application/test_moon_tick.py:95` (`back.moon_location is None`) becomes `== "mysuru"`.
- **After this, no UI sets NULL:** the bot and Mini App always send a slug. `PUT /me/moon-location {slug: null}` stays, for MD-02's "Follow my teacher".
- **Past choices can't be recovered:** NULL rows mix "never chose" and "chose Mysuru before this fix". They stay as they are, and MD-02 must treat them as never chosen and announce any change (§11).

## 8. Migration `0019_teacher_links` (expand-only, down `0018`) and ops
- `teacher_link(student_id uuid, teacher_id uuid, is_primary boolean not null default false, linked_on date not null, created_at timestamptz not null default now())`: PK `(student_id, teacher_id)`; both FKs to `account` `ON DELETE CASCADE`, named `teacher_link_student_id_fkey` / `teacher_link_teacher_id_fkey`; CHECK `student_id <> teacher_id`; index `(teacher_id, student_id)`; **unique partial index `teacher_link_one_primary (student_id) WHERE is_primary`**.
- `teacher_invite(account_id uuid PK references account on delete cascade, code text not null unique, created_at timestamptz not null default now())`; CHECK `code ~ '^[A-Za-z0-9]{16}$'`. Rotation resets `created_at`.
- `op.f()` names (0004's double-naming lesson). No sequences; table grants come from the defaults (0001). No backfill. Downgrade drops both tables; `test_db_app_role.py`'s fixture re-runs it.

**☁️ Owner steps:** after deploy, run `tools/telegram/set_webhook.py` so `/teachers` shows in the menu. Add `TELEGRAM_BOT_USERNAME=tristhana_bot` to the `--set-env-vars` in `backend.yml` (repo change, no cloud step) and the dev bot's name to `.env`/`.env.example`. Optional beta-group line. Migration 0019 runs in CI.

## 9. Cross-cutting checks
- **Time zones:** no date or time is shown, so no zone label. `created_at` is UTC; the export uses UTC `Z`. **`linked_on` is the student's local date at confirm** (provisional zone if none, as PR-01), stored and never recomputed. The consent says "from today on", and `day_log.local_date` is a local date, so an instant alone couldn't give that boundary once zones differ or change.
- **Privacy:**
  - Only names cross accounts (Q2). The teacher view of a student is `{id, name, linked_at}`, nothing else.
  - **The invite is never logged, and the path is already clean.** `webhook.py` logs update id, type and outcome; errors log type and stack frames only; a malformed body logs no body; `serve.py` sets `access_log=False`; aiogram's `feed_update` logs update id and duration. Exception *messages* are logged only in dev polling, hence "exceptions never carry the code". A test pins this.
  - The code is stored plain (Q4): the teacher must re-show it, and a dump exposes nothing it doesn't already hold in stronger form.
  - The other person's name is rendered in my chat for the first time. The bot sends plain text (no `parse_mode`), so a name can't inject markup; if `parse_mode` ever arrives, names must be escaped.
  - **Names are self-chosen, so anyone can use any name.** `invite-know-them` stays for everyone, permanently. **ID-05 helps only people with a badge:** a badge is a separate positive fact with no negative counterpart, and no person is ever labelled "unverified".
- **i18n:** all copy in `.ftl`, en/ru parity. The note uses the **teacher's** locale, the consent screen the student's. RU plurals through Fluent; names never declined.
- **Responsiveness** (statements include the middleware's 1; a target until measured, §10):

| Tap | Statements | Outbound |
|---|---|---|
| `/start` without an invite | unchanged | none |
| `/start t_<code>` | 2 (+1 on first contact) | none |
| ✅ Confirm | 2 + `/start`'s own reads | 1 silent send (≤ 3 s; rare, once per link) |
| Not now | 1 + `/start`'s own reads | none |
| Consent language switch | 3 | none |
| `/teachers`, lists, cards, asks, invite screen | 2 | none |
| Remove (confirmed) | 3 | none |
| Make main | 4 (one short transaction) | none |
| New link | 2 | none |
| QR | 2 | 1 upload |
| Moon city pick | unchanged | none |

## 10. Test plan (108 cases)
- **Domain (19):** `parse_invite` accepts `t_` + 16 alphanumerics; rejects wrong prefix; wrong length; wrong alphabet; None and `t_` alone. `invite_state` open; own; already; cap. `effective_primary` none; oldest; chosen wins; chosen removed → oldest; tie on `teacher_id`. `next_primary` removing a non-main; removing the main with others left; removing the last. `teaches`. A cycle is valid.
- **Application, fakes (20):**
  - Accept creates and notifies once; a double tap notifies once; `BLOCKED`/`FAILED` still succeed with no mark; unknown code → None; own code refused; caps; **`linked_on` is the student's local date** (Kiritimati vs Honolulu on one instant, provisional zone); rotate kills the old code and keeps links; re-link is a fresh row with a new `linked_on`; `Accepted` flags a second link, not a first.
  - **Policies:** `can_unlink` both sides, not a third; `can_choose_primary` student only; `can_manage_invite` owner only; **a linked teacher gets False from `can_view_check_ins`, `can_view_diary`, `can_view_progression`.**
  - **Moon:** choosing Mysuru stores `"mysuru"` (changes `test_moon_tick.py:95`); `None` stores NULL with `explicit` False; `GetMoonView.explicit` True for stored Mysuru; **`"mysuru"` and NULL give identical results** in auto-rest, stats, reminders and the settings line (parametrized); export `{slug: "mysuru", default: false}`; unknown slug raises.
- **DB, real Postgres (17):** each repository call's statement count as in §9; two concurrent accepts → one row, one `created`; two concurrent `set_primary` → at most one flagged, the loser raises `LinksChanged`; a flip works whichever row comes first; `set_primary` on a non-link rolls back and keeps the old main; deleting a teacher account cascades, leaves other links and moves the effective primary; deleting a student account likewise; 23503 mapping (student → `AccountGone`, teacher → None); CHECKs and the unique index; the SQL ordering matches `effective_primary`; 0019 up/down/up; `alembic check`. **App role** (`test_db_app_role.py`): accept, set primary, rotate, unlink and export as `tristhana_app`. **Export:** both directions present; **the other person's name and id, and the code, appear nowhere in `data.json`**; `primary` is null on the teacher's side; the coverage guard passes.
- **API (12):** 401; `GET /me/links` key set exact (no practice field); **`students[]` has no primary field**; POST invite idempotent; rotate changes the URL; primary 200/404/409; both DELETEs 204 twice; a foreign id deletes nothing; `no-store`; no route takes a code in its path or query; OpenAPI lists the codes and the TS client builds; `moon-location` with `mysuru` → `explicit: true`, with null → false.
- **Bot, through the webhook, fake use cases (22):**
  - `/start t_<code>` as a brand-new person → consent in the negotiated language, account exists; own name shown, and absent cleanly with no name; language tap keeps the invite; ✅ edits into the grid and the grid still logs; Not now stores nothing and messages no one.
  - Every `invite-*` state; a stale ✅ after rotation; a non-`t_` payload behaves as before.
  - **Log capture at DEBUG across all loggers on `/start t_<code>`, ✅, a handler error and a malformed body: the code appears nowhere.**
  - **Consent with 64-character names ≤ 4096 in both locales.**
  - `[⭐ Make main]` on a second link, never a first; ⭐ absent with one teacher, chosen vs automatic shown with two; removing the main teacher names who takes over; student paging; 0 students → the "I teach" label, last; remove confirm steps on both sides; forged uuid, malformed `t1:`, every value ≤ 64 bytes; `answered` before the work.
  - Note sent silently in the teacher's locale, with no word about main; `set_webhook.py` lists `teachers`.
  - **Moon:** explicit Mysuru with an unknown zone shows no "Use … time" button, Almaty still does; the picker marks ✓ Mysuru from the stored slug.
- **Mini App, Vitest (11):** Settings row opens the lazy screen; lists and empty states; ⭐ only with two or more; make main; remove confirm cancel/accept, naming who takes over; invite shows `qr`, Copy, Share; rotate confirm; 409 refetch; the 0-students label; RU at 320 px; `npm run build && npm run check:bundle`.
- **i18n/architecture (7):** ftl parity; **the old `settings-privacy-sharing` sentence is gone** ("When teachers join, you choose what they see." / «Когда появятся учителя, ты выберешь, что им показывать.»); RU new keys contain no «отвязать», «связь», and `invite-consent`/`settings-privacy-sharing` no «длина»; no new key says "unverified", guru, instructor or coach; RU gendered-ending and avoid-word greps; the three diary tests updated (§2); import-linter (aiogram only in `bots/telegram`, segno only in `infrastructure/qr`, domain pure).
- **Measured 2026-11-07** (local Postgres, through the real webhook, Telegram stubbed, 50 warm samples, server-side): `/start t_<code>` p50 7.9 ms (p95 14.1), ✅ 27.4 ms (p95 44.5, with the stubbed note), `/teachers` 8.0 ms (p95 14.4); target < 300 ms. Owner on a phone: QR scan from a second device, new-person path, RU narrow width, the RU share button (a long percent-encoded URL).

## 11. What later features get from this
- **ST-06:**
  - Students by index, one hop. Extends `can_view_*` with a link argument. Per-link opt-ins become columns on `teacher_link`, so they die with the link.
  - **History:** day status and practice length only where `local_date >= linked_on`. Last asana is current state, visible from the start.
  - **Teacher projection, narrower than `public_status`:** practiced stays; rest, moon, 🌸, sick, travel and rest-period days all show as rest. **"No practice" and unlogged days are both blank and identical.** Auto-rest is not logged, so it is blank too.
  - **Stays hidden:** context (Mysore, Led, self-practice), duration, start time, milestones, check-ins, diary.
  - **Last asana** is labelled as the student's own mark, and the screen separates a mark from teacher-given. A position moving back is visible, even though PR-08 Q13 hides the events.
  - **Gentleness:** no "who hasn't practiced" list; a quiet "Haven't logged for a while" at most; counts only since `linked_on`; `last_seen_at` is never exposed. A teacher never sees whether they are main.
  - **Consent:** must stay within `invite-consent` or ask again. Links made before a change are identifiable by `created_at`, so no consent-version column.
- **PR-08 marks:** any linked teacher may mark a new asana (already in the consent, so no re-consent); `can_mark_progression` checks the link; events survive a removal, and `marked_by` keeps the teacher's UUID until that account is deleted. **"You can undo it" must hold:** today's undo works only on the latest event, so PR-08 Phase 3 must define undo for a teacher's mark that is no longer latest.
- **MD-02:**
  - **An explicit choice always wins.** Inheritance applies only to a null `moon_location`, which since §7 means "never chose, or chose Mysuru before the fix" (not separable).
  - Effective primary in one query for the tick: `DISTINCT ON (student_id) … ORDER BY student_id, is_primary DESC, created_at, teacher_id`. **Resolve one hop only**, or cycles loop.
  - **It must handle the first link, not only a primary change:** confirming would move a never-chosen student's moon days. Removal is silent, so a primary change does too. Both need a gentle line.
  - **Open rule:** `07 Moon Days` says teacher → own location and student → primary teacher's. Which applies to someone who is both?
  - **MD-02 reveals the teacher's moon city** to students, the first teacher data to cross a link, so it must tell teachers.
- **NT-03:** recipients by the `teacher_id` index; a per-link mute column; goes through the tick and ledger, unlike the join note.
- **SC-03:** my teachers from `overview`. **ID-05:** the badge joins on account id and is shown beside the name; `invite-know-them` stays. **SC-01:** no shala columns here; `teaches` gains a second source; a shala invite takes its own prefix in `parse_invite`.
- **Notes (notes-keeper, not this spec):** the privacy table in `05 Domain Model.md` needs updating for the above.

## 12. Decisions (owner, 2026-11-07; all as recommended, with these refinements)
1. **Who invites:** teachers only (anyone can act as one), and the student always confirms.
2. **Names:** linked people see each other's display name now, the only new exposure, stated on the consent screen.
3. **Consent promise:** "what you log from today on: practice or rest, length; the last asana as marked in the log, current state rather than from today; all rest looks the same; check-ins, notes and the reason for a rest private unless shared". Plus teacher marks, undoable, so no re-consent at PR-08.
4. **Invite code:** one reusable, non-expiring code per teacher, 16 alphanumerics, rotate for a leak, stored plain, no rate limit.
5. **Caps:** 20 teachers per student, 500 students per teacher.
6. **Cycles:** allowed; rights never transitive; MD-02 stops at one hop.
7. **Main teacher:** first teacher automatically, next oldest takes over, read-time default. `is_primary` stores only an explicit choice, under the partial unique index. S2 adds `[⭐ Make main]`, chosen vs automatic, and who takes over.
8. **Removal:** silent both ways, no neutral line, hard delete.
9. **Block list:** none now; `teacher_block` is additive if the beta shows a need.
10. **"I teach":** no toggle (a label at 0 students), and ST-06 doesn't require ID-05. `invite-know-them` stays for everyone.
11. **Join note:** one silent direct message per new student, outside the cap and ledger, no retry.
12. **Surfaces:** one `/teachers` command, a Settings row, no Home row, no accept endpoint yet.
13. **QR:** `segno` on the server.
14. **Export:** neither side's export names the other person.
15. **Words:** «учитель» for the relationship, "teacher" in EN, never guru/instructor/coach; «преподаватель» for formal titles and shala job roles; «преподаю» is fine. `diary-empty` and `diary-private-hint` aligned.
16. **Also decided:** teacher view history starts at the link (§11); explicit Mysuru stored as its slug (§7); access never ends by itself, for now; the student's real name is shown on the consent screen.
