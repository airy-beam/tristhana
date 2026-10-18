# ADR-0007: Fluent for i18n
- Status: accepted · Date: 2026-10-18
## Decision
Project Fluent `.ftl` files per locale (en, ru at launch), used by both the backend/bot (`fluent.runtime`) and the Mini App (`@fluent/react`). Asana names/meanings are localized data in the DB, not `.ftl`.
## Why
Proper Russian plural/gender handling. One format across clients. Adding a language = adding files.
