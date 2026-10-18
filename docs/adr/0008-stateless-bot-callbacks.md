# ADR-0008: Stateless bot interactions
- Status: accepted · Date: 2026-10-18
## Decision
Encode dialog state in `callback_data` (≤ 64 bytes, compact codes like `pl:p:full1:20261018`). Avoid FSM storage. For the rare multi-step text input, keep one `bot_dialog` row (read and written once). Answer callback queries immediately and edit messages in place. Updates are idempotent by `update_id`.
## Why
FSM-in-DB round trips were a major latency source in sashas-bot.
