# ADR-0030: Teacher links: the student always consents, one reusable invite code per teacher, primary resolved at read time
- Status: accepted (owner, 2026-11-07)
- Amended by ADR-0031 (2026-11-07): `created_at` can't identify which consent text was confirmed, so `teacher_link.quiet_note_agreed` records the quiet-note consent.
- Date: 2026-11-07
## Context
ID-04 is the first time one account relates to another. A student has 0..n teachers with one primary, a teacher has teachers too, linking goes through `t.me/bot?start=t_<code>`, and either side can unlink. ST-06, MD-02, NT-03, SC-03 and PR-08 teacher marks all build on it. Being a teacher is a capability derived from relationships (ID-03, no role column). Teachers need to show one QR to a whole room, or print it for a shala wall. Account delete is one cascading statement (ADR-0027). Bot interactions are stateless (ADR-0008). Spec: `docs/specs/ID-04-teacher-links.md`.

The key asymmetry: what a link exposes is mainly the **student's** data, so consent has to come from the student, and an invite code is not a credential to anyone's data. The one exception on the horizon is MD-02, which will reveal a teacher's moon city to their students.
## Decision
- **Consent:** a link exists only after the student taps ✅ on a screen naming the inviter, showing the student's own name, and stating what the teacher will see, now and later. Only teachers create invites. The code rides in the callback data, so there is no pending row and a new person can't lose the invite. A decline stores nothing and tells no one.
- **What the consent promises:** now, the student's name. Later, what they log from the link date on (practice or rest, length) and their last asana as marked; all rest looks the same; any teacher on the list may mark a new asana, which the student can undo; check-ins, notes and the reason for a rest stay private unless shared.
- **Capability:** no role column and no "I teach" toggle. Anyone can open their invite; `teaches` = has at least one student. SC-01 adds a second source later.
- **Exposure:** linking shows display names to the two people, and nothing else. The owner-only `can_view_*` policies are unchanged. Rights are one hop, never transitive. Cycles are allowed.
- **Names:** self-chosen, so the consent screen tells everyone, permanently, to confirm only if they know the person. A future badge is a separate positive fact with no negative counterpart: no person is ever labelled unverified, and ID-05 replaces nothing here.
- **Invite code:** one per teacher in `teacher_invite`, reusable, no expiry, 16 alphanumerics (about 95 bits), stored **plain** so it can be re-shown. Rotation is the only revoke. No rate limit: guessing is infeasible and a code yields only a name. Never logged, never in a URL we serve, never exported.
- **Links:** `teacher_link(student_id, teacher_id, is_primary, linked_on, created_at)`, PK on the pair. `linked_on` is the student's local date at confirm, the boundary for "from today on". Removal is a **hard delete** from either side and is silent. A re-link is a new row with default privacy. Access never ends by itself, for now. There is no block list: a teacher can't link anyone without that person's tap.
- **Primary:** `is_primary` stores only an explicit choice; a partial unique index keeps it to at most one per student. The **effective primary** is that row, else the oldest link, resolved at read time. So a first teacher needs no write and a departing primary needs no promotion, which keeps account delete a single cascade. Changing it is one transaction of clear then set, because a non-deferrable unique index is checked per row and a one-statement flip can fail on row order. A concurrent loser gets `links_changed`. The UI says "Main teacher", separates a choice from the default, and names who takes over when the student removes their main teacher. A teacher never learns whether they are main.
- **Explicit Mysuru:** `SetMoonLocation` stores the chosen slug, including the default city, so "chose Mysuru" differs from "never chose". NULL now means only never chosen, or chosen before this fix.
- **Join note:** a direct, always-silent (`disable_notification`) message through the `Notifier` port, with no ledger, cap or retry. The list is the record.
- **QR:** generated on the server with `segno`, used by both the bot (a PNG to forward or print) and the Mini App (a data URI).
- **Export:** both directions appear as `{other_side, primary, linked_at}`, with no name or id of the other person and `primary` null on the teacher's side; the invite table is excluded.
## Consequences
- A leaked link is a nuisance, not a data leak: at worst unwanted rows on a teacher's list, limited by the 500 cap and ended by rotating.
- Rotating breaks printed QRs, so removing a persistent unwanted student has a real cost. A `teacher_block` table would be additive.
- A stranger can use any name and invite someone. The protection is consent, the know-this-person line, instant removal and nothing being visible yet. A badge helps only people who have one.
- The consent copy commits ST-06 to a teacher projection narrower than `public_status`: practiced, or rest for every rest kind and moon days; "No practice" and unlogged days blank and identical; context, duration, start time and milestones hidden. Anything beyond the copy needs new consent. Links made before a change are identifiable by `created_at`, so no consent-version column is kept.
- The consent also commits PR-08's teacher marks, so that needs no re-consent. "You can undo it" must then hold beyond today's latest-event undo.
- Every read of the primary must use the same ordering, including MD-02's batch query for the tick.
- **MD-02:** an explicit choice always wins, and inheritance applies only to a null `moon_location`. Past explicit Mysuru choices can't be recovered, because they were stored as NULL, so those people look like never chosen. It must resolve one hop, handle the first link as well as a primary change, settle the rule for someone who is both teacher and student, and tell teachers that their moon city becomes visible to students.
- Ended links leave no row of their own, but not no trace: with PR-08 marks, a student's progression events keep the teacher's UUID in `marked_by` until that account is deleted.
- A plain code sits in backups; rotation handles an incident. Silent notes can pile up after a busy class.
- `is_account_gone` must learn `teacher_link_student_id_fkey`; a 23503 on the teacher FK means the invite is gone.
- A small new runtime dependency (`segno`), lazy-imported; the bundle is unaffected.
## Alternatives considered
- **Link on tap, with no confirm:** fewest taps, but anyone with a link would gain future access to a student's data.
- **Student-created invites (`s_` codes):** a second code type and flow for a rare case; additive later.
- **Single-use or expiring codes:** safer against leaks, but a code here unlocks no data, and they break the one QR for a room or wall.
- **Hashed codes:** every viewing of the link would have to rotate it. Hash plus sealed copy adds two columns to protect a name.
- **Materialising exactly one primary** (promotion on unlink): needs a trigger or an extra step in the one-statement delete, for no read benefit.
- **`primary_since` timestamp** (latest wins): a one-row write with no race, but the invariant is invisible in the schema, where a partial unique index states and enforces it.
- **Deferrable exclusion constraint:** allows a one-statement flip, but is less familiar and still fails on a true concurrent race.
- **Soft delete with `ended_at`:** a record of past relationships could be useful, but hard delete is the privacy default, and keeping it risks reviving old opt-ins.
- **`linked_at` as the history boundary:** one column fewer, but an instant can't give the student's local "today" once zones differ or change.
- **Block list now:** not needed for students; speculative for teachers.
- **Join note via the tick and ledger:** honours quiet hours and batches, but arrives up to 10 minutes late and needs new candidate logic; a silent message covers the same concern.
- **Client-side QR in a lazy chunk:** no backend dependency, but no QR for bot-only teachers and no printable file.
