# ADR-0033: Shalas: a listed city as the location, the owner on the row, single-use staff invites, a shala step in the moon rule
- Status: accepted (owner, 2026-11-07)
- Date: 2026-11-07

## Context
SC-01 asks for a shala with a name, a location (city, lat/lon, zone), an online flag and staff with roles (ID-03: owner, admin, teacher, assistant, staff-admin). MD-02 says "shala → own location; teacher → own or follow the shala". SC-02 will expand classes in the shala's zone and cancel them on the shala's moon days. Today there is no location table: moon calendars exist only for the 34 cities in `data/seed/cities.yaml`, pre-computed by the tick (ADR-0019). Links between people need the consent of the person whose data is exposed (ADR-0030). The moon city is resolved at read time, one hop (ADR-0032). Account delete is one cascading statement (ADR-0027). Spec: `docs/specs/SC-01-shala.md`.

## Decision
- **Location = a listed city slug** (`shala.city`, required, also for online-only shalas). Lat/lon and the IANA zone come from the city, never stored per shala and never as an offset. `shala.moon_city` (nullable = the city) lets a shala follow another listed city, such as Mysuru. A missing city is added to `cities.yaml`.
- **Ownership is a column:** `shala.owner_id → account ON DELETE CASCADE`, so there is always exactly one owner and deleting the owner's account deletes the shala. Staff roles are a set in `shala_staff.roles` ⊆ {admin, teacher, assistant, office}. The owner always has a staff row, which can hold teaching roles.
- **Staff and students are separate tables** (`shala_staff`, `shala_student`), exclusive per shala, both with `joined_on` (the member's local date at confirm).
- **Joining always needs the joiner's tap.** Students use the shala's reusable `h_<code>` link (code on the shala row, rotatable). Staff use a **single-use, 7-day, role-bound** `hs_<code>` link (`shala_staff_invite`), consumed by `DELETE … RETURNING` in the accept statement, and the inviter gets a silent note.
- **A membership exposes names and roles only.** No log data flows through a shala; teacher views stay on `teacher_link`. Co-students never see each other. Previews show no people.
- **Moon:** `MoonSource.SHALA` and the sentinel `-shala` ("Follow my shala"). Never-chose staff follow their shala first. A never-chose student follows their shala when their main teacher is on its staff (Q108); otherwise their teacher's explicit city first, then their shala, then Mysuru. Still one hop: a teacher's shala city doesn't pass to students who aren't members. The main shala (staff memberships first, then student memberships where the main teacher is staff, then the oldest) loads with the account and the tick candidates in the existing statements, as one more correlated subquery.
- **Words:** «Преподаватель» is the shala role, «учитель» the personal teacher. A shala "Teacher" role never implies SYC authorisation (ID-05 stays the only badge). Staff and student stay exclusive per shala; a "practises here" flag waits for SC-02/ST-08 (Q107).
- **Authorization** lives in `application/policies.py` on the caller's membership, read in the same statement as the resource. Non-members get 404.

## Consequences
- No new moon computation, and no geocoding, coordinates or location table. Shalas outside the list wait for a YAML change.
- SC-02 gets a zone and a moon calendar for every shala with no further schema, and SC-03 gets "my shalas" from the membership indexes.
- An owner deleting their account removes the shala for everyone. Ownership transfer is an additive update of `owner_id` later.
- Staff links can't be shared to a room. Each needs a new link, which is the point.
- A student's moon city can change when their main teacher joins or leaves the staff of the student's shala, on the next read, with no write (as for other MD-02 changes made by others: silent, shown in labels).
- Students of a shala teacher who aren't members don't inherit the shala city. The staff accept screen offers the MD-02 Keep button to make it the teacher's explicit city.
- One more correlated subquery in the account load and the tick candidates. Callback data encodes uuids as base64url to fit two ids in 64 bytes.

## Alternatives considered
- **Free coordinates per shala** (map pin or typed lat/lon, zone via tzfpy): exact, but needs a location table, on-demand moon calendars per shala, polar checks, and stores a precise address-like point.
- **A `shala_member` table with a role enum, `student` included:** one table, but an owner who also teaches needs two roles, and student rows (link consent) mix with staff rows (privileged).
- **Owner as a role with a partial unique index:** symmetric, but an owner's account delete would leave an ownerless shala, or need a trigger.
- **Promote existing members to staff with a push confirm:** no second link type, but needs pending state and a notification flow.
- **Reusable staff links:** one QR for a team, but a leaked link makes strangers staff with access to student names.
- **Deriving a shala's students from its teachers' links:** no join step, but a teacher at two shalas would mix them, and a student couldn't follow a shala's schedule without a personal teacher.
- **Shala city passed through teachers (two hops):** a better default for students of shala teachers, but reverses Q77.
