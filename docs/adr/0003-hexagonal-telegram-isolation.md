# ADR-0003: Hexagonal architecture; Telegram library isolated
- Status: accepted · Date: 2026-10-18
## Decision
`domain` (pure) ← `application` (use cases, ports) ← adapters (`api`, `bots/telegram`, `jobs`, `infrastructure`). `aiogram` is imported only in `bots/telegram/`. Bot and REST API call the same use cases. Enforced with import-linter in CI.
## Consequences
The bot library can be swapped, and web/mobile reuse all logic. A little more boilerplate (ports, DTOs).
