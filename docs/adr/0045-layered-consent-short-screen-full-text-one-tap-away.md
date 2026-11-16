# ADR-0045: Layered consent: a short screen, with the full text one tap away as the consent record
- Status: accepted (owner, 2026-11-16; Q311 and Q312 in `docs/specs/UI-06-simple-journey.md` answered as recommended)
- Builds on ADR-0030 (teacher invite), ADR-0031 (`quiet_note_agreed`), ADR-0033 (shala join and staff link). Changes none of their promises.
- Date: 2026-11-16
## Context
The three consent screens (`invite-consent`, `shala-join-consent`, `shala-staff-consent`) are lists of five to eight bullets, shown at the moment a person first meets the product through someone else's link. The UI-06 audit found them too long to be read, which defeats their purpose. The owner approved three lines (what the other side sees, what they never see, you can leave any time) plus a "Details" button showing the full current text, on the condition that the full text stays reachable and accurate.

Two accepted rules constrain this. ADR-0030: the consent screen tells everyone, permanently, to confirm only if they know the person. ADR-0031: a value derived for a teacher (the quiet note) must be named in the text the student confirmed, and `teacher_link.quiet_note_agreed` is set only by the confirm of such a text (`t1:a:<code>`); a change of promises needs a new column and a new confirm callback.
## Decision
- **Two layers, one consent.** The short screen carries the ask line, the directory fact when there is one (ID-05), three summary lines, the know-this-person line, and `[Confirm] [Not now] [Details] [other language]`. "Details" shows the full text exactly as it is today, from the same Fluent keys, with the same `[Confirm] [Not now]` and a way back.
- **The full text is the consent record.** Confirm on either layer agrees to it. Nothing is promised on the short screen that the full text does not say.
- **Rule for the short "sees" line:** it names every data item the full text lists as visible to the other side. For a teacher invite: the name, practice or rest with its length from today on, the last asana, and the note shown when nothing is logged for a while. Things the other side can do (mark a new asana, send announcements) and the mechanics (no one is told on decline) live in Details.
- **The know-this-person line stays on the short screen**, as a fourth line. It is a safety warning, not one of the consent items.
- **No new column and no new confirm callback.** The promises do not change, only their presentation, so `t1:a` keeps setting `quiet_note_agreed`, and `h1:a` / `h1:b` are unchanged. A full-text screen sent before the release stays valid: its text is the Details text.
- **New stateless callbacks only for the layer switch** (`t1:d:<code>`, `h1:d:<code>`, `h1:ds:<code>` and back). Each render re-reads the invite, so a rotated or used code shows the "no longer works" line on either layer.
- **A later change of promises still follows ADR-0031**, and must change both layers in the same pull request.
- **Tests pin both layers:** the full texts byte for byte (existing tests), the short texts byte for byte, a table of data items each short line must name in `en` and `ru`, "Details" present on every short screen, and a confirm from Details creating the same link with the same flag.
## Consequences
- A person can confirm without opening Details. That was already possible without reading; now the summary they do read is short enough to be read.
- The short "sees" line is constrained and may run long in Russian; it must still fit a phone screen with the longest names (the existing longest-name test extends to it).
- Two texts per consent must be kept in step. The item table makes a drift fail a test.
- The public guide keeps describing the full list ("What your teacher sees").
- If the owner rules that the quiet note may not ride on a summary (Q312), the fallback is a second confirm letter that leaves `quiet_note_agreed` false when confirmed from the short screen, which creates two classes of new links.
## Alternatives considered
- **Keep the long screens:** nothing to maintain, and the audit's finding stands.
- **Confirm only from Details:** the strongest reading of "informed", but it puts the long text back in everyone's path.
- **Set `quiet_note_agreed` only when confirmed from Details:** literal ADR-0031, but teachers would see the note for some new students and not others with no visible reason.
- **Telegram's expandable quote for the full text in the same message:** one message, no extra tap, but it needs `parse_mode` on screens that carry people's self-chosen names and are plain text today.
