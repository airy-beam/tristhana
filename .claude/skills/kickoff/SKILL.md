---
name: kickoff
description: Start a work session on Tristhana. Loads the current phase, open questions and last session outcome, then proposes the next concrete task. Use at the beginning of every session.
disable-model-invocation: true
---
# Session kickoff
1. Read `/home/pumpkin_vibe/Documents/pumpkin_notes/02_projects/tristhana_bot/09 Roadmap.md` (current_phase, statuses, last Session log row) and `/home/pumpkin_vibe/Documents/pumpkin_notes/02_projects/tristhana_bot/03 Open Questions & Decisions.md`.
2. If git exists: run `git status` and `git log --oneline -10` to see uncommitted or recent work.
3. Summarise for the user in ≤ 10 lines:
   - Current phase and its goal
   - What was done last session
   - Open questions blocking this phase (if any), and ask them now
   - **Top 3 candidate next tasks** (with requirement IDs and a rough size: S/M/L), with your recommendation
4. Wait for the user to pick. Then run small tasks directly, or suggest `/feature <ID>` for feature-sized work.
$ARGUMENTS
