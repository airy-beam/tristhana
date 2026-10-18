---
name: feature
description: End-to-end workflow for implementing one roadmap feature or requirement ID (e.g. /feature PR-03). Spec → owner confirmation → test-first implementation → review → notes update.
argument-hint: <REQ-ID or short description>
disable-model-invocation: true
---
# Feature workflow for: $ARGUMENTS

Follow these steps in order. Keep the user informed with one line per step.

## 1. Understand
- Look up the requirement(s) in `/home/pumpkin_vibe/Documents/pumpkin_notes/02_projects/tristhana_bot/02 Requirements.md` and the related notes (domain, time zones, moon days, catalog).
- Read the relevant existing code.

## 2. Spec (design before code)
- Use the **architect** agent to write `docs/specs/<ID>-<slug>.md`.
- If the feature touches the Ashtanga domain (sequences, presets, rest/moon days, progression, wording), have the **ashtanga-expert** agent review the spec.
- Show the user a short summary of the spec, plus its open questions. **Stop and wait for confirmation.** Record the answers in `03 Open Questions & Decisions.md`.

## 3. Implement test-first
- Use the **test-engineer** agent (or write the tests yourself) to create failing tests from the spec's test plan.
- Implement in layer order: domain → application (use case + ports) → infrastructure (repo, migration) → API → bot / Mini App.
- New user-facing text goes into `.ftl` (en + ru). Ask the **ux-writer** agent to polish the copy.
- Run the tests, ruff and pyright (and the Mini App tests/build if touched) until green.

## 4. Review
- Run the **code-reviewer** agent on the diff, and **ashtanga-expert** again if domain logic changed.
- Fix blockers and should-fix items. Mention nits to the user.

## 5. Wrap up
- Summarise for the user: what changed, how to try it (commands / bot steps), and the test results (honestly, including failures or skipped steps).
- Suggest a commit message (`<ID>: <imperative summary>`). Commit only if the user asks.
- Use the **notes-keeper** agent to update the roadmap status and decision log.
