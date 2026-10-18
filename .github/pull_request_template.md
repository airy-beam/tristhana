## What & why
<!-- Requirement ID(s), e.g. PR-03. One or two sentences. -->

## How to verify
<!-- Commands, screenshots, bot flow to tap through. -->

## Checklist
- [ ] Tests pass (`uv run pytest` / `npm test`)
- [ ] `ruff check`, `ruff format`, `pyright`, `lint-imports` clean
- [ ] User-facing strings in `.ftl` for both `en` and `ru`
- [ ] No layering violations (`aiogram` only in `bots/telegram/`, auth in `application/` policies)
- [ ] Times: UTC instants / date + IANA zone; displayed times carry a zone label
- [ ] Privacy: diary, notes, ladies' holiday reason encrypted; teacher views projected
- [ ] Domain-sensitive change reviewed by `ashtanga-expert` (if applicable)
- [ ] ADR added for significant decisions; roadmap/decision notes updated
- [ ] No secrets committed
