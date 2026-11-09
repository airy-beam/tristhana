# ADR-0038: Announcements are delivered by the tick from the live audience, silently in quiet hours, pinned in the app only, and can't be edited
- Status: accepted (owner, 2026-11-09)
- Date: 2026-11-09
## Context
NT-03 lets a teacher announce to their linked students (up to 500) and lets shala staff announce to the shala (up to 1000 students + 30 staff). The send has to fit the existing constraints:
- Cloud Run throttles the CPU after the response (ADR-0011), so nothing can fan out in the background. The tap target is < 300 ms p50.
- Telegram allows roughly 30 messages a second per bot and answers 429 beyond that.
- NT-02 promises quiet hours and a daily cap.
- ADR-0018 already provides the 10-minute tick, a claim-before-send ledger (`notification_delivery`) with retries and blocked-bot handling, and a `Notifier` port.

ID-04 §11 planned for NT-03 to go "through the tick and ledger, unlike the join note". The ashtanga-expert pointed out that Mysore rooms open 5:30–6:30, inside most people's quiet hours, so a same-morning closure note must not wait for quiet hours to end. Spec: `docs/specs/NT-03-announcements.md`.
## Decision
- **One row per announcement, no per-recipient outbox.** `announcement(author_id, shala_id NULL = the teacher's students, text, audience, pinned_until, created_at)`. The send request is one guarded statement: policy, rate limit, audience count, pin. It makes no outbound call.
  - **The rate limit** is 3 per source per rolling 24 h, counted over existing rows.
  - Delete is a hard delete, so deleted announcements don't count (owner: delete and resend fixes a typo).
- **The tick computes who is due, from the live audience.** Each run reads, in one statement, the announcements under 24 h old joined to their current audience, and keeps the people who:
  - joined before the announcement;
  - haven't muted the source;
  - have the global switch on;
  - are reachable;
  - have no final ledger row.

  The 24 h bound only protects against pushing stale items after a tick outage. Sending reuses `claim → deliver → finish` with category `announcement` and key `ann:<id>`. Leaving a shala or removing a link before delivery therefore stops the push, and a delete stops pending pushes, with no cleanup.
- **NT-02, quiet hours decide the sound, never the timing.**
  - A recipient inside their quiet hours (their IANA zone) gets the message at once with `disable_notification=True`; outside them, with sound.
  - With no known zone, it goes at once, silently.
  - Announcements ignore the daily cap, but their ledger rows count toward it, so reminders yield on a busy day.
- **Opt-out without telling the sender.** `announcements_muted` on `teacher_link`, `shala_student` and `shala_staff` (it dies with the link), and `notification_settings.announcements_on` (NT-01). Muting stops only the push. The sender sees only the audience size at send time, muted people included, with no delivered or read counts.
- **Pins live in the app.** `pinned_until` holds 7 or 30 days. One pin per source, kept by the write statement. Expiry is read-time. No Telegram `pinChatMessage`.
- **Plain text that can't be edited, and changes no data.**
  - 1–1000 characters, no `parse_mode`, link previews off.
  - An announcement never changes a day, auto-rest or a reminder: a closure announcement is not a rest day (revisit with SC-02 Q122).
  - Delete is a hard delete from the app; delivered Telegram messages stay, so no `message_id` is stored.
- **Not sealed.** Unlike ADR-0016's private fields, announcement text is broadcast by its author and copied into every recipient's chat. Encrypting it would protect nothing that isn't already in Telegram. It is pruned after 90 days.
## Consequences
- The send tap is one statement and never waits on Telegram. Delivery latency is ≤ 10 min for small audiences. A 1000-person shala at ~15–25 sequential sends/s spans 2–3 ticks (≤ ~30 min), sharing the 40 s budget after reminders. If measurement shows more, batch claims or ≤ 8 concurrent sends (already allowed by ADR-0018).
- An early-morning note reaches everyone before class, without waking anyone: it arrives silently in quiet hours. The cost is that someone who checks the phone only after quiet hours sees it among other unread messages, with no sound to mark it.
- Each recipient costs 2 statements (claim, finish), and the ledger grows by one row per recipient (pruned at 60 days). The tick's existing per-account delivery read grows with these rows. That is fine at this scale; filter by category if it starts to matter.
- The `notification_delivery` category CHECK changes (migration 0024, the 0005 drop-and-recreate pattern).
- The rate limit is soft under a race (at most one overshoot), like the other caps. Delete and resend makes the limit a guard against floods, not against an author's corrections.
- Editing a sent announcement, deleting delivered messages, or Telegram pins would each need `message_id` per ledger row and a second fan-out. That calls for a new ADR.
## Alternatives considered
- **Send in the request (like the join note and the teacher's mark):** instant, but 500–1000 sends can't fit in a tap or in Cloud Run's request after the response.
- **Cloud Tasks / Pub/Sub fan-out:** immediate and scalable, but new infrastructure, IAM and cost for a hobby project, and it duplicates the ledger.
- **Materialised recipient rows (`announcement_recipient`):** an exact snapshot and easy delivered counts, but 1000 inserts per send, and stale recipients after a leave or removal. Delivered counts are a privacy leak we don't want anyway.
- **Hold during quiet hours until they end (the first draft):** fits the reminders' rule, but a 05:30 "the shala is closed today" note would land after class has started. Rejected on the ashtanga-expert's advice.
- **Silent always (as the join note):** simplest, but daytime announcements are the one category people want to notice.
- **Respect the cap:** would drop or delay a teacher's message because of the app's own reminders. The wrong priority.
- **Count deleted announcements toward the limit (a soft delete):** stricter against delete-and-resend floods, but it punishes typo fixes, and 3 per 24 h plus the push's Mute button already bound the noise.
- **Telegram `pinChatMessage` in each private chat:** visible at the top of the chat, but a second rate-limited call per recipient, a stored message id, unpinning fan-out, and a teacher controlling the top of the student's own chat.
- **Encrypting the text (ADR-0016 format):** no real protection (the text is in every recipient's Telegram), and it costs the key on every feed read.
