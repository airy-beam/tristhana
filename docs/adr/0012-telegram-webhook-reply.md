# ADR-0012: Telegram webhook served in-process, replies via the webhook response
- Status: accepted
- Date: 2026-10-18
## Context
The bot must answer in < 300 ms p50 warm and < 1.5 s cold on Cloud Run with CPU throttled outside requests (ADR-0011). Every outbound HTTPS call to `api.telegram.org` adds latency, and on a cold instance it also adds TLS and session setup. Spec: `docs/specs/UI-01-telegram-webhook.md`.
## Decision
- The webhook is a FastAPI route (`POST /telegram/webhook`, outside `/api/v1`, hidden from OpenAPI) owned by `bots/telegram` and mounted by the composition root. It is authenticated by `X-Telegram-Bot-Api-Secret-Token` (constant-time compare) and handles each update to completion before responding.
- Handlers return a single Bot API method, which is sent back as the webhook response body ("webhook reply"). Direct Bot API calls are used only when the result is needed or more than one call is required.
- aiogram costs ~3.4 s to import (it rebuilds every Telegram type's schema). When the webhook is enabled, the runtime is **preloaded during startup** (under Cloud Run's startup CPU boost), and a Cloud Scheduler job pings `/api/v1/health` every 10 min so an instance usually stays warm. No network calls at startup; `setWebhook` is a one-off operator tool.
- `update_id` dedupe is per instance in memory in Phase 0, and moves to the DB in Phase 1.
## Consequences
Zero outbound calls for simple replies (~14–60 ms server time). A cold instance is ready after ~4 s, so the rare cold reply misses the 1.5 s cold target; min-instances=1 (~$3–5/month) is the fallback if that hurts. The bot gets no result from a webhook reply (no `message_id`, no delivery errors), and no file uploads that way. Handlers work unchanged in dev long polling, where aiogram executes the returned method itself.
## Alternatives considered
Always calling the Bot API directly (simpler mental model, about one extra RTT per reply); aiogram's aiohttp webhook server as a separate app (a second server stack next to FastAPI); handling updates in background tasks after a fast 200 (starved by CPU throttling on Cloud Run).
