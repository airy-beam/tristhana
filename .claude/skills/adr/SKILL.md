---
name: adr
description: Record an Architecture Decision Record in docs/adr/ for a significant technical decision.
argument-hint: <decision title>
disable-model-invocation: true
---
# New ADR: $ARGUMENTS
1. Find the next number in `docs/adr/` (4 digits).
2. Copy the structure of `docs/adr/0000-template.md`: Status, Date (today), Context, Decision, Consequences, Alternatives considered.
3. Fill it in from the conversation. Keep it under 40 lines. If the context is unclear, ask the user 1–2 questions first.
4. If it supersedes an older ADR, update the old one's status line.
5. Add a one-line entry to the decision log in `03 Open Questions & Decisions.md` (notes) linking the ADR file name.
