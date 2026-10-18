# ADR-0001: Monorepo
- Status: accepted · Date: 2026-10-18
## Context
Backend, bot, Mini App and seed data evolve together, and API types are shared via OpenAPI codegen. One maintainer.
## Decision
One repository: `backend/`, `miniapp/`, `data/seed/`, `docs/`, `infra/`, `tools/`.
## Consequences
Atomic changes across API and client. CI uses path filters to build only what changed.
