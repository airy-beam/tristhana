---
name: wrapup
description: End a Tristhana work session. Updates the roadmap, session log and decision log so the next session can continue seamlessly.
disable-model-invocation: true
---
# Session wrap-up
1. Collect what happened this session: the conversation, plus `git status` / `git log` / `git diff --stat` if available.
2. Ask the **notes-keeper** agent to update `/home/pumpkin_vibe/Documents/pumpkin_notes/02_projects/tristhana_bot/09 Roadmap.md` (statuses, Session log row) and `03 Open Questions & Decisions.md` (new decisions and questions).
3. If this session changed what a person sees, or touched `site/`, run `/guide-check` and name any problems or pages that may be behind in the summary. Don't fix them here; suggest `/guide-update <ID>` as a next task.
4. If CLAUDE.md is now inaccurate (new commands, new conventions), propose a minimal edit and apply it after the user agrees.
5. If you learned something durable about how the user likes to work, save it to memory.
6. Tell the user in ≤ 8 lines: what was done, what is uncommitted, and the recommended first task for next session.
