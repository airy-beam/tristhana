# SC-01: shalas (profile, staff with roles, students join, the shala moon step)

- Status: **accepted** (owner, 2026-11-07: all as recommended, plus Q104 "Front desk", Q107–Q109; ashtanga-expert copy fixes applied; ux-writer pass before release) · Size M, Phase 3
- Requirements: **SC-01** (name, location: city, lat/lon, zone; online flag; staff with roles). **ID-03** (shala roles; "teaches at a shala" as a second teacher source). **MD-02** (the "shala → own location" step, "teacher → follow shala"). Prepares SC-02 (classes in the shala zone, moon auto-cancel policy), SC-03 (my shalas' schedules), SC-05, ST-08.
- Related: ADR-0008, 0019, 0025, 0027, 0029, 0030, 0031, 0032. New: **ADR-0033** (accepted).

## 1. Scope (decided slice, Q96)
SC-01 alone (a shala row with staff) gives a student nothing. The smallest useful slice:
**In:** create a shala (name, listed city, online flag); a shala card for members; staff invited by a single-use role link and confirmed by the invitee; students join by the shala's reusable link with a consent screen; leave and remove, silent, from either side; the shala's moon city as a new step in the MD-02 rule plus "🏛 Follow my shala"; export and delete coverage.
**Deferred (marked for later):** classes and schedules (SC-02/03); a public shala directory or search; custom coordinates or addresses (Q97); ownership transfer (Q102); a "add this shala's teachers as my teachers" shortcut (needs ADR-0030 consent per teacher; SC-03); any practice data through a shala (ST-08, new consent); a verification badge (ID-05); a main-shala choice for people in several shalas; a "practises here" flag for staff (Q107, with SC-02/ST-08 attendance); inheriting the shala's weekly day off (Q109, SC-02).
**Unchanged:** `teacher_link`, the teacher view and its policies. **A shala membership never grants access to anyone's log.** Joining a shala creates no teacher link.

## 2. Flows and copy
**Create and edit (Mini App only, Q103).** Settings → 👥 Teachers and students gains a **🏛 Shalas** part: my shalas as rows, then `[🏛 Create a shala]`. Form: name (1–64, normalised like `display_name`), city (`<select>` of the 34 cities, preselected with `home_city`), "🌐 Online classes only" toggle. The creator becomes the owner, with roles they tick (teacher by default). The bot's invite screen (`t1:i`) and an empty shala list show `[🏛 Create a shala]` as a `web_app` button.

**Shala card (both surfaces, any member):**
```
🏛 Ashtanga Almaty
📍 Almaty · shala time: Almaty (UTC+5)        (online: 🌐 Online · shala time: Almaty (UTC+5))
🌙 Moon days: 📍 Almaty
Teachers and staff: Anna (owner, teacher) · Boris (teacher) · Dana (assistant)
[👥 Students (34)]   (staff only)   [➕ Invite students] [➕ Invite staff]   (per policy)
[Leave…]             (not for the owner)
```
The zone label uses the existing city label helper (offset at "now", never stored). Students never see other students.

**Student joins (bot, `/start h_<code>`).** Preview shows only the shala name and city, never staff names (staff consented to members, not to link holders). Consent, stateless (code in `h1:a:<code>`), `[✅ Join] [Not now] [🗣 Русский]`, edits into the shala card after ✅. States: invalid, already a member, already staff, full.

**Staff joins (bot, `/start hs_<code>`).** An owner or admin taps `[➕ Invite staff]`, picks a role, and gets a link that **works once, for 7 days**. The invitee sees the staff consent and taps ✅ (`h1:b:<code>`). A student of the shala who accepts becomes staff (the student row goes in the same statement). The inviter gets one silent note (`shala-staff-joined`, `disable_notification`, as ID-04's join note). Student joins send no note (Q105).

**Roles, removal (Mini App: all; bot: remove and leave only).** Roles are edited on the staff list in the Mini App. Remove and Leave are one confirm each, silent both ways, hard delete. The owner can't leave; deleting the shala is Mini App only, with a native confirm.

**Moon.** The `/moon` picker gets `[🏛 Follow my shala (Ashtanga Almaty)]` (`m1:h`), shown only with a shala, after "Follow my teacher". The card, `/moon` and Settings show `moon-source-shala`. Owners and admins see `shala-moon-shared` on the card.

**Copy** (⚑ all drafted here; «ты»; RU gender-neutral verbs; shala and people names nominative only; role nouns per Q104):

| Key | EN | RU |
|---|---|---|
| `shala-join-ask` | 🏛 Join { $shala } (📍 { $city })? | 🏛 Присоединиться к шале { $shala } (📍 { $city })? |
| `shala-join-consent` | If you join:<br>• The shala's teachers and staff see your name ({ $me }). Nothing from your log.<br>• Your moon days follow the shala's calendar, unless you've chosen a city, or your teacher has. If your teacher teaches here, the shala's calendar comes first.<br>• You can leave any time in /teachers. No one gets a message. | Если присоединиться:<br>• Преподаватели и сотрудники шалы увидят твоё имя ({ $me }). Ничего из журнала.<br>• Лунные дни будут считаться по календарю шалы, если город не выбран ни тобой, ни твоим учителем. Если учитель преподаёт в этой шале, календарь шалы важнее.<br>• Выйти можно в любой момент в /teachers. Сообщений никто не получит. |
| `shala-know-them` | Join only a shala you know: anyone can create one with any name. | Присоединяйся только к знакомой шале: создать шалу с любым названием может кто угодно. |
| `shala-staff-ask` | 🏛 { $name } invites you to { $shala } as { $role }. | 🏛 { $name } приглашает тебя в шалу { $shala }. Роль: { $role }. |
| `shala-staff-consent` | If you confirm:<br>• Everyone in the shala, students included, sees your name ({ $me }) and role.<br>• You'll see the names of its students and staff, not their logs.<br>• You can leave any time in /teachers. | Если подтвердить:<br>• Все в шале, включая учеников, увидят твоё имя ({ $me }) и роль.<br>• Тебе будут видны имена учеников и сотрудников, но не их журналы.<br>• Выйти можно в любой момент в /teachers. |
| `shala-staff-joined` | 🏛 { $name } joined { $shala } as { $role }. | 🏛 { $name } теперь в шале { $shala }. Роль: { $role }. |
| `shala-staff-link-hint` | This link adds one person as { $role }. It works once, for 7 days. | Эта ссылка добавит одного человека. Роль: { $role }. Работает один раз, 7 дней. |
| `shala-role` | `{ $role -> [owner] Owner [admin] Manager [teacher] Teacher [assistant] Assistant *[office] Front desk }` | `… Владелец / Управляющий / Преподаватель / Ассистент / Администратор` (Q104) |
| `moon-source-shala` | 🏛 Same as your shala, { $shala }. You can choose another city. | 🏛 Как в шале: { $shala }. Можно выбрать другой город. |
| `moon-follow-shala` | 🏛 Follow my shala ({ $shala }) | 🏛 Как в шале ({ $shala }) |
| `shala-moon-shared` | 🌙 Staff, and members whose teacher works here, follow this calendar unless they chose a city. Other members follow it unless they or their teacher chose one. (Q110) | 🌙 Сотрудники и участники, чей учитель преподаёт здесь, следуют этому календарю, если сами не выбрали город. Остальные — если город не выбран ни ими, ни их учителем. |
| `settings-moon-line-shala` | 🌙 Moon days: 📍 { $city } (as { $shala }) | 🌙 Лунные дни: 📍 { $city } (как в шале: { $shala }) |

Plus states and buttons: `shala-invalid`, `shala-already`, `shala-already-staff`, `shala-full`, `shala-joined`, `shala-leave` / `-ask` / `-yes`, `shala-remove-ask`, `shala-students` (Fluent plural), `shala-staff-title`, `shala-invite-students`, `shala-invite-staff`, `shala-create`, `shala-online`, `shala-time`, `shala-delete-ask`, `shala-name-invalid`, `shala-caps`, `export-readme-shalas`; `delete-explain` extended ("shalas you own are deleted for everyone"). Reused: `invite-share`, `invite-qr`, `invite-new*`, `link-no-name`, `log-back`, `page-prev/next`.

**Copy rules (owner + ashtanga-expert, 2026-11-07):**
- **Glossary, split on purpose:** «Преподаватель» is the shala staff role; «учитель» is the personal teacher of ID-04 («Как у учителя»). Never swap them.
- A Mysuru moon city is labelled **calculated** (the existing `moon-calc-note` wording: lunar day at sunrise), never "SYC", until MD-05 imports the official calendar.
- The "Teacher" role on a shala card is a role in that shala, nothing more. No copy may imply SYC authorisation or certification; ID-05 stays the only badge.

## 3. Domain, use cases, ports
`domain/shalas.py` (pure):
```python
class ShalaRole(StrEnum): ADMIN = "admin"; TEACHER = "teacher"; ASSISTANT = "assistant"; OFFICE = "office"
# owner is not a role value: it is `shala.owner_id` (exactly one, by construction)
MAX_OWNED = 3; MAX_STAFF = 30; MAX_STUDENTS = 1000; MAX_STAFF_OF = 10; MAX_STUDENT_OF = 5
MAX_PENDING_STAFF_INVITES = 10; STAFF_INVITE_TTL = timedelta(days=7); NAME_MAX = 64
@dataclass(frozen=True, slots=True)
class Membership: shala_id: UUID; owner: bool; roles: frozenset[ShalaRole]; student: bool
def parse_shala_invite(payload) -> ShalaInvite | None   # h_<16> student, hs_<16> staff
def normalize_shala_name(raw) -> str | None              # same cleaning as display_name
def join_state(...) -> JoinState                        # OPEN, ALREADY, STAFF, FULL
def grantable(actor: Membership) -> frozenset[ShalaRole] # owner: all; admin: all but ADMIN
def teaches_at_shala(m: Membership) -> bool              # TEACHER or ASSISTANT (ID-03)
```
Staff and student are **exclusive** per shala (a domain rule, kept by the accept statement). The owner always has a staff row (roles may be empty).

**Moon rule (`domain/moon.py`, Q99 + Q108).** `FOLLOW_SHALA = "-shala"`; `MoonSource.SHALA`; `ShalaMoon(id, name, moon_city, staff: bool, teacher_on_staff: bool)` where `moon_city` is the shala's moon city, else its city (always listed), and `teacher_on_staff` = the person's main teacher is on this shala's staff. `moon_follow(own, teaches, teacher, shala, cities)`:
```
1. own is a listed city                                              → CHOSEN
2. own = "-shala"                                                    → shala city, else DEFAULT
3. own = "-teacher"                                                  → teacher's own explicit city, else DEFAULT  (as today)
4. never chose:  staff at a shala                                    → SHALA
                 student of a shala where the main teacher is staff  → SHALA   (Q108: beats the teacher's city)
                 no students and the teacher has an explicit city    → TEACHER (as today)
                 student of a shala                                  → SHALA
                 otherwise                                           → DEFAULT
```
Still one hop (Q98): a teacher's SHALA value never passes to students who aren't members. Q108 needs no hop either: it reads only the student's own membership and whether their main teacher staffs that shala. **Main shala** = staff memberships first, then student memberships where the main teacher is staff, then the oldest: `ORDER BY staff DESC, teacher_on_staff DESC, created_at, shala_id LIMIT 1`. `Account` += `shala: ShalaMoon | None`; `moon_follow_of` passes it, so every MD-02 reader picks it up unchanged.

**SQL sketch (no extra round trip).** In the account columns (`_COLUMNS`, so `find_by_identity` and every `RETURNING`) one more jsonb scalar subquery, next to `_MAIN_TEACHER`:
```sql
(SELECT jsonb_build_object('id', s.id, 'name', s.name, 'moon', coalesce(s.moon_city, s.city),
                           'staff', m.staff, 'teacher_on_staff', m.teacher_on_staff)
   FROM (SELECT shala_id, true AS staff, false AS teacher_on_staff, created_at
           FROM shala_staff WHERE account_id = account.id
         UNION ALL
         SELECT st.shala_id, false, EXISTS (SELECT 1 FROM shala_staff t
                  WHERE t.shala_id = st.shala_id AND t.account_id = (<main teacher id>)), st.created_at
           FROM shala_student st WHERE st.account_id = account.id) m
   JOIN shala s ON s.id = m.shala_id
  ORDER BY m.staff DESC, m.teacher_on_staff DESC, m.created_at, s.id LIMIT 1)
```
`<main teacher id>` is `_main_teacher_of(_TEACHER.c.id)`, the same correlated subquery and ordering as `effective_primary`. Index reads only: `shala_staff (account_id)`, `shala_student (account_id)`, the `shala_staff` PK and `teacher_link`'s PK prefix (≤ 10 + 5 membership rows). Tick candidates add the same expression as `shala_location`, `shala_staff`, `shala_teacher_on_staff` columns; still 3 statements.

**Policies (`application/policies.py`), on the caller's `Membership` from the same statement:** `can_view_shala` any member · `can_view_shala_students` staff · `can_edit_shala` owner, admin · `can_show_join_link` staff · `can_rotate_join_link` owner, admin · `can_invite_staff(actor, role)` / `can_set_roles(actor, target, roles)` role ∈ `grantable(actor)`, never on the owner, admins only by the owner · `can_remove_staff(actor, target)` owner any other; admin non-admins; anyone themselves except the owner · `can_remove_student` owner, admin, office · `can_delete_shala` owner. Non-members get `NotFound`, never `NotAllowed`, so ids can't be probed. `can_view_activity` and the other teacher policies are untouched; a test pins False for shala co-members.

**Use cases (`application/shalas.py`, both adapters unless noted):** `CreateShala`, `GetMyShalas`, `GetShala`, `UpdateShala`, `DeleteShala`, `GetShalaStudents`, `GetJoinLink`, `RotateJoinLink`, `CreateStaffInvite`, `SetStaffRoles`, `RemoveStaff` (also leave), `RemoveShalaStudent` (also leave); bot only: `PreviewShalaInvite`, `JoinShala`, `AcceptStaffInvite` (joined_on = caller's local date, as `linked_on`). `SetMoonLocation.execute(principal, slug | None, follow="teacher" | "shala")`. `_moved` and `_keep_offer` (MD-02) pass the shala input.

**Port `ShalaRepository` (`Storage.shalas`), one statement each:** `create` (CTE: cap check, shala + owner staff row), `mine`, `card(shala, me)` (shala + my membership + staff names ≤ 30 + student count; None = not a member), `update`, `delete`, `students(shala, me, offset, limit)`, `preview(code, me)`, `join(code, me, caps, joined_on)`, `invite_staff(shala, me, role, code, expires_at)` (pending cap), `accept_staff(code, me, joined_on)` (`DELETE … RETURNING` the invite, unexpired, so single use holds under a double tap; deletes a student row; returns the inviter's Telegram id and locale), `set_roles`, `remove_staff`, `remove_student`, `rotate_join(shala, me, code)`. `CodeSource` and `QrCodes` reused.

## 4. API (initData; `{code}` errors; `no-store`; `gen:api`)
| Method, path | Request → Response | Policy |
|---|---|---|
| `GET /api/v1/me/shalas` | → `[{id, name, city, online, side: "staff"\|"student", owner, roles}]` | own |
| `POST /api/v1/shalas` | `{name, city, online, roles}` → 201 `ShalaOut`; 409 `shala_caps` | anyone, caps |
| `GET /api/v1/shalas/{id}` | → `ShalaOut {id, name, city: {slug, name}, zone, online, moon_city, staff: [{id, name, owner, roles}], students_total: int\|null, me: {owner, roles, student}}` | member; 404 |
| `PATCH /api/v1/shalas/{id}` | `{name?, city?, online?, moon_city?}` (null = same as city) → `ShalaOut` | `can_edit_shala` |
| `DELETE /api/v1/shalas/{id}` | → 204 | `can_delete_shala` |
| `GET /api/v1/shalas/{id}/students` | `?offset&limit≤50` → `{students: [{id, name}], total}` | `can_view_shala_students` |
| `POST /api/v1/shalas/{id}/join-link` | `{rotate?}` → `{url, qr}` | show / rotate policies |
| `POST /api/v1/shalas/{id}/staff-invites` | `{role}` → `{url, qr, expires_at}`; 409 `shala_caps` | `can_invite_staff` |
| `PUT /api/v1/shalas/{id}/staff/{account_id}` | `{roles}` → `ShalaOut` | `can_set_roles` |
| `DELETE /api/v1/shalas/{id}/staff/{account_id}` · `/students/{account_id}` | → 204, idempotent (self = leave) | remove policies |
| `PUT /api/v1/me/moon-location` | `{slug: null, follow?: "teacher"\|"shala"}` (default teacher) | own |
| `GET /api/v1/me/moon-days` | `Location.source` += `"shala"`, `shala: {id, name} \| null` | own |

`zone` is the IANA name; the client builds the label. `ErrorCode` += `shala_caps`, `invalid_shala_name`, `not_allowed` (403: the first API route where a caller may see a resource but not change it); `unknown_location` reused for the city. No accept route (joins land in the bot, as ID-04 Q12). Codes never in a URL or query.

## 5. Bot (prefix **`h1:`**, free; ids as 22-char base64url uuids so two fit in 64 bytes; answer first, edit in place)
| Data | Meaning |
|---|---|
| `h1:a:<code>` · `h1:n` · `h1:l:<locale>:<code>` · `h1:b:<code>` | student join ✅ · not now · language · staff accept ✅ |
| `h1:c:<shala>` · `h1:m:<shala>:<page>` · `h1:v:<shala>:<acct>` | card · students page · student card |
| `h1:i:<shala>` · `h1:q:<shala>` · `h1:w:<shala>` · `h1:wy:<shala>` | join link · QR · rotate ask · rotate |
| `h1:e:<shala>` · `h1:e:<shala>:<t\|a\|o\|m>` | staff invite: pick role · create (teacher, assistant, office, manager = `admin`; `m` only for the owner) |
| `h1:u:<shala>:<acct>` · `h1:x:<shala>:<acct>` · `h1:k:<shala>` · `h1:ky:<shala>` | remove ask · remove · leave ask · leave |
| `m1:h` | moon: follow my shala |

Longest: `h1:x:` + 22 + `:` + 22 = 50 bytes. `/teachers` lists my shalas as `🏛 Name` rows above `[Open the app]`. `on_start` dispatches `t_`, `h_`, `hs_` through the parsers, no logic. Staff accept on a never-chose person with students adds the existing MD-02 Keep button for the shala city (`m1:k:<slug>`), so their students can get it too (Q98).

## 6. Migration `0021_shalas` (expand-only, down `0020`)
- `shala(id uuid PK default gen_random_uuid(), name text NOT NULL CHECK 1–64, city text NOT NULL, moon_city text NULL, online boolean NOT NULL DEFAULT false, owner_id uuid NOT NULL → account ON DELETE CASCADE, join_code text NOT NULL UNIQUE CHECK '^[A-Za-z0-9]{16}$', created_at, updated_at)`; slug CHECKs `'^[a-z][a-z-]{0,23}$'` (no sentinels); index `(owner_id)`. Slugs have no FK, as ADR-0019.
- `shala_staff(shala_id → shala CASCADE, account_id → account CASCADE, roles text[] NOT NULL DEFAULT '{}' CHECK roles <@ '{admin,teacher,assistant,office}', joined_on date NOT NULL, created_at)`, PK `(shala_id, account_id)`, index `(account_id, created_at)`.
- `shala_student(shala_id, account_id, joined_on, created_at)`, same keys and index.
- `shala_staff_invite(code text PK CHECK 16 alnum, shala_id → shala CASCADE, role text CHECK in roles, created_by → account CASCADE, expires_at timestamptz NOT NULL)`, index `(shala_id)`. Expired rows are deleted by the tick's pruning step.
- FK names via `op.f()`; `is_account_gone` learns the new `*_account_id_fkey` names. No backfill. Downgrade drops all four. Account load and tick candidates gain one correlated subquery each (UNION ALL of the two membership indexes, `LIMIT 1`).

## 7. Cross-cutting checks
- **Time zones.** The shala zone is `city.tz` (IANA), never stored as an offset; labels `Almaty (UTC+5)` are computed at render. SC-02 expands classes in this zone. Moon dates are the shala city's local dates; each person's day stays in their own zone (as MD-02). `joined_on` is the member's local date at confirm (provisional zone if none), the boundary for later shala features. Expiry is a UTC instant; no time of day is shown.
- **Privacy.** Only names and roles cross accounts: staff see staff and students; students see staff; **co-students never**. Previews show no people. No practice data through a shala; tests pin `can_view_activity` False for co-members. Removal and leaving are silent hard deletes; ending a shala membership never touches teacher links. Shala names are self-chosen: plain text, no `parse_mode`, `shala-know-them` on every join screen. Codes are never logged (the ID-04 log-capture test is extended to `h_`/`hs_`). **Export:** `shalas: [{name, city, moon_city, online, side, owner, roles, joined_on}]` for my own memberships, no other person's name or id; invites and join codes in `EXCLUDED_TABLES` (credentials). **Delete:** cascades my rows; deleting an owner deletes their shalas for everyone (Q102, `delete-explain`).
- **Abuse.** Anyone can create, capped (Q101). A leaked student link → staff remove and rotate. A staff link works once, expires in 7 days, and its use notifies the inviter. Caps are soft like ID-04's.
- **i18n.** All keys in `bot.ftl` / `app.ftl`, en + ru parity; Fluent plurals for counts; role labels through one select key; names never declined.
- **Responsiveness.**

| Tap | Statements | Note |
|---|---|---|
| Any tap (account load) | unchanged (1) | + one ≤ 15-row index subquery |
| `/start h_` / `hs_` | 2 | preview |
| ✅ join / staff accept | 2 | + 1 silent send for staff |
| Shala card, students page, invite screens | 2 | ≤ 30 staff rows, ≤ 10 students |
| Remove, leave, rotate, staff invite | 2 | |
| `/moon`, Today, stats, tick | unchanged | rule is pure CPU |

Measure with a 1000-student shala before calling it done. Mini App: shala screens in one lazy chunk; initial JS unchanged but for the Links section; RU at 320 px (names and role lists wrap).

## 8. Test plan
- **Domain:** `moon_follow` table extended (every MD-02 row × no shala / staff / student; `-shala` with and without a shala; staff with students never chose → SHALA; a teacher on SHALA gives their student nothing; a removed moon slug; **Q108:** a never-chose student whose main teacher (with a chosen city) staffs the student's shala → SHALA, the same teacher not on that shala's staff → TEACHER, the teacher staffs a different shala → TEACHER, student in two shalas with the teacher on staff of the newer one → that one, a chosen city or `-teacher` still wins, a teacher with no city on staff → SHALA; a student with students (Q76) in that shala → SHALA); main-shala ordering; `parse_shala_invite` (`h_`, `hs_`, wrong lengths, `t_` untouched); `grantable` and every policy as a role × action matrix, including owner-can't-leave and admin-can't-touch-admin; name normalisation; caps; invite expiry boundary.
- **Use case, fakes:** create sets owner + staff row; caps raise; join stores the student's local `joined_on` (Kiritimati vs Honolulu); staff accept consumes once, converts a student, notes the inviter silently in their locale; non-member → `NotFound`; `SetMoonLocation(None, "shala")` stores `-shala`; MD-02 `_moved` / Keep offer with a shala; no use case reads `day_log`, `practice` or `progression`.
- **DB (real Postgres):** CHECKs; cascades (shala delete, owner account delete, member delete); two concurrent staff accepts → one row; staff/student exclusivity under a race; account load fills `shala` identically in `find_by_identity` and every `RETURNING`, including `teacher_on_staff` and the Q108 ordering (teacher made main, teacher removed from staff, teacher unlinked: the next read changes, no write); tick candidates match the domain for a seeded Q108 mix; statement count unchanged by the new subquery; statement counts per §7; `EXPLAIN` on 1000 students; app role; 0021 up/down/up; `alembic check`; export has no other person's name or id and no code.
- **API:** 401; exact key sets; non-member 404 equals unknown id 404; students list hidden from students (`students_total: null`); role grants per matrix (a member without the right gets 403 `not_allowed`, a non-member 404); `follow: "shala"`; `source: "shala"`; OpenAPI → TS client builds.
- **Bot, through the webhook:** both consents in both locales, ≤ 4096 with 64-character names; preview shows no person; every state line; ✅ edits into the card; a used or expired staff link → `shala-invalid`; card per role (buttons present/absent); remove, leave confirm steps; forged ids re-render; every callback ≤ 64 bytes; `answered` first; `m1:h` and the picker row only with a shala; code never in logs.
- **Mini App (Vitest, also `TZ=UTC`):** create form validation; card per role; staff role editor; delete confirm; zone label; moon select option; cache invalidation; RU at 320 px; `check:bundle`.
- **i18n/architecture:** ftl parity; RU gendered-ending and avoid-word greps; import-linter (domain pure, aiogram only in `bots/telegram`, `application.shalas` imports no day/practice/progression port).
- **Owner on a phone:** create a shala, invite a teacher from a second account, a student joins by QR, the moon label on both surfaces.

## 9. What SC-02 will need (not built here)
- The shala's **weekly day off** (Sat or Sun), and whether never-chose students inherit it (Q109).
- A **moon-day policy** per shala: closed, or pranayama / led only; classes on moon days auto-cancel per that policy.
- **Swap days** (a Sunday-off shala practising on the Saturday, 07 Moon Days), **closures** and a **substitute teacher** per occurrence.
- The **led-class day** (often Friday or Sunday) as a class rule, not a shala field.
- Attendance views (SC-05) show 🌸 as **rest**, the same projection as ST-06; a "practises here" flag for staff (Q107).

## 10. Decisions (owner, 2026-11-07; all as recommended, with Q104 changed and Q107–Q109 added)
- **Q96 Scope.** Recommend the slice in §1 (profile, staff, students join, moon step). SC-01 alone (profile + staff) would ship nothing a student sees; adding classes makes it L.
- **Q97 Location.** Recommend a **listed city only** (lat/lon/zone from `cities.yaml`); a missing city is added to the YAML on request (one deploy, computed by the next tick). An online-only shala still picks a city (its zone and moon days). Custom coordinates deferred (ADR-0033).
- **Q98 Moon through a shala teacher.** Recommend keeping Q77's one hop: a teacher's shala city doesn't pass to their non-member students. Mitigation: the Keep button on staff accept, and `moon-teacher-shared` gets a `[shala]` variant.
- **Q99 Default order.** Recommend: never-chose **staff** follow their shala before their own teacher; never-chose **students** follow their teacher's explicit city first, then their shala, then Mysuru. Refined by Q108.
- **Q100 Staff confirmation.** Recommend a single-use, 7-day, role-bound link that the invitee confirms, plus a silent note to the inviter. Alternative: promote from members with a push confirm (needs pending state).
- **Q101 Creation and caps.** Recommend anyone can create; 3 owned shalas, 30 staff, 1000 students per shala, 10 staff and 5 student memberships per person, 10 pending staff links per shala.
- **Q102 Owner leaves.** Recommend: the owner can't leave; deleting the owner's account deletes their shalas (stated in `delete-explain`). Transfer of ownership comes later.
- **Q103 Surfaces.** Recommend create, edit, roles and delete in the Mini App only (forms); the bot does joins, the card, invite links, remove and leave.
- **Q104 Words (changed).** EN Owner, Manager (admin), Teacher, Assistant, **Front desk** (office); RU «Владелец», «Управляющий», «Преподаватель», «Ассистент», «Администратор»; «шала» in RU. «Преподаватель» (shala role) vs «учитель» (personal teacher) is on purpose (§2 copy rules).
- **Q105 Join notes.** Recommend a silent note to the inviter on a staff join only; none for student joins (a room scanning a QR would flood the owner).
- **Q106 Visibility.** Recommend: students see the staff list; all staff see student names and the count; co-students never; no public directory.
- **Q107 Staff who practise.** Staff and student stay exclusive within one shala in SC-01. A "practises here" flag for staff is deferred to SC-02/ST-08 attendance.
- **Q108 Teacher on the shala's staff.** For a never-chose student whose main teacher is on the staff of a shala the student belongs to, that shala's calendar wins over the teacher's chosen city. Otherwise Q99's order applies (§3 rule).
- **Q109 Weekly day off.** Whether a never-chose student inherits the shala's day off is deferred to SC-02.

- **Q110–Q113 (owner, after the build review, 2026-11-07, all as recommended).** Q110 `shala-moon-shared` states the real rule (only members, Q98). Q111 a removed moon city falls back to the shala's own city. Q112 keep "up to 64 characters" and the «команда» / «сотрудники» split. Q113 the Mini App delete explanation names shalas too.

All questions above are accepted as written ("Recommend" = the decision), except Q104 as changed.
