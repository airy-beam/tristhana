# ADR-0051: A tap on an old Today asks which day; Today's buttons get their own callback letter
- Status: accepted (2026-11-18, with the UI-06 stage 6 spec; owner Q368: fix all of the launch clarity audit, with `docs/specs/UI-06-stage-6-launch-clarity.md`, item B6)
- Builds on ADR-0008 (stateless callback data, absolute dates) and the UI-06 stale-button rule (CLAUDE.md; `tests/bots/test_stale_buttons_bot.py`).
- Date: 2026-11-18
## Context
Today's three choices carry the day they were drawn for: `d1:s:<date>:<code>`, the same data the day editor uses (`days.py`, `callbacks.py`). Absolute dates are deliberate (ADR-0008): a keyboard tapped later still acts on the day it shows. But Today is the screen people leave at the bottom of the chat. Tapped the next morning, yesterday's unanswered Today saves 🧘 on yesterday, and the person does not notice (launch audit B6, S1). The editor's buttons are different: the person opened that date on purpose.

The two kinds of tap cannot be told apart today, and `d1:s` may not change meaning: buttons already in chat history must keep saving the date they carry.
## Decision
- **A new letter for taps from Today:** `d1:n:<date>:<code>` ("set, from Today"). Today's 🧘 and 😌, and the reasons screen opened from Today (`d1:r:<date>:t`), draw their status buttons with it. The editor keeps `d1:s`.
- **On `d1:n`:** the date is the person's today (by `GetDays.today`) → saved exactly as `d1:s`. The date is earlier → nothing is saved; the message is edited into one question, "which day?", with one full-width row per date, today first and then the carried date, both as `d1:s` with explicit dates (so the answer never asks again), and a last row "‹ Back" (`log-back`) to Today (`w1:n`). A date later than today (a zone change) → the existing `DateInFuture` path.
- **With the zone unknown** (no device zone and no city yet, so "today" comes from the provisional zone of the language: UTC for English, Moscow for Russian), the question is asked only when the carried date is earlier than the earliest local date on Earth (UTC-12, `domain.days.earliest_today`); a date that is still today somewhere is saved as `d1:s` would save it. Otherwise an English speaker in Los Angeles who taps that evening's Today after 00:00 UTC would be asked "which day?" about their own today. (Review fix, 2026-11-18.)
- **`d1:s` is unchanged.** Old Today messages already in chat (sent before this release) still save their date; they age out.
- The rule lives in the bot adapter (`bots/telegram/days.py`): it is about how a chat message ages, which the Mini App (always drawn live) does not have. The use cases are unchanged.
## Consequences
- With the zone unknown, a stale Today keeps saving its own date until that date has ended everywhere on Earth, so for some people a few hours longer than with a known zone: the guess cannot tell a late log from a stale message, and asking someone "which day?" about their own today is the worse mistake. The city question (B7) removes the guess.
- One more tap only in the case that was wrong before; a tap on today's Today costs nothing extra (no read added: `today` is computed from the loaded account).
- The callback docstring and the frozen stale-button list gain `d1:n`; the stale test covers both outcomes (today, and an older date).
- The practice reminder keeps its own `r1:` data and its insert-if-absent rule (Q26): it names its date in the text and a new one comes each day. Not changed here.
## Alternatives considered
- **A relative "today" letter (as `w1:n`):** after midnight the person may well mean yesterday (a late log); silently saving today is the same mistake the other way round.
- **Always ask when the date is not today, also in the editor:** the editor's date was chosen on purpose; asking there is noise.
- **Edit or delete yesterday's Today at midnight:** needs a job per person and a stored message id; a bot cannot know which message is the last one the person sees.
- **Change what `d1:s` means:** forbidden by the stale-button rule; old messages would change behaviour silently.
