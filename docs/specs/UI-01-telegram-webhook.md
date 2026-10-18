# UI-01 (Phase 0 slice): Telegram webhook end-to-end, `/start` → "Namaste 🙏"

- Status: confirmed by the owner (answers at the end), awaiting owner answers (§8) · Date: 2026-10-18
- Requirements: **UI-01** (greeting; language from `language_code`), **NF-01** (Fluent, en + ru), **NF-03** (secrets in Secret Manager), **NF-04** (aiogram only in `bots/telegram`), **NF-06** (idempotent webhook). Budget: < 300 ms p50 warm, < 1.5 s cold (`04 Architecture`).
- Related: ADR-0003, ADR-0007, ADR-0008, ADR-0011, `NF-02-cloud-run-deploy.md`. New: **ADR-0012** (webhook in-process, webhook-reply by default).

## 1. Scope
**In:** webhook route, secret check, aiogram Dispatcher with one `/start` handler, `StartUseCase`, Fluent loader + `en`/`ru` files, locale negotiation, in-memory dedupe, settings for the two secrets, deploy `--set-secrets`, a one-off `set_webhook` tool, dev long polling (if Q6 = yes).
**Phase 1 (not here):** **ID-01** account auto-creation (needs the DB; then the user upsert + `update_id` dedupe become one round trip), the "Log today's practice?" prompt (rest of UI-01), stored language preference, callback queries.
**Out:** `/help` and replies to other text (unless Q5), group chats (ignored), deep-link payloads (`/start <payload>` treated as `/start`).

## 2. Flows and copy
Private chat, user sends `/start` → bot replies with one plain-text message (no parse mode, no keyboard) in the negotiated locale. Anything else → no reply (200, empty body).
Keys in `backend/src/tristhana/infrastructure/i18n/locales/{en,ru}/bot.ftl` (package data; ux-writer polishes, RU uses informal «ты», warm and never pushy):
```
# en
start-greeting = Namaste 🙏
    I'm Tristhana, your practice companion. Soon you'll be able to log your practice here.
# ru
start-greeting = Намасте 🙏
    Я Тристхана, твой спутник в практике. Скоро здесь можно будет отмечать практику.
```

## 3. Design
**Layers.**
- `domain/locale.py` (pure): `Locale = Literal["en","ru"]`; `negotiate_locale(language_code: str | None) -> Locale`: take the primary subtag (`ru-RU` → `ru`), map via a table (Q3), fallback `en`. Reused later by the API.
- `application/start.py`: `StartUseCase.execute(StartCommand(telegram_user_id, language_code)) -> StartResult(locale, reply=Greeting())`. Phase 0 it only negotiates the locale; Phase 1 adds the `UserRepository` upsert behind the same signature. No I/O now.
- `application/ports/i18n.py`: `Translator` protocol `t(locale, key, **args) -> str`. Implementation `infrastructure/i18n/fluent.py` (`fluent.runtime`; bundles parsed lazily on first use, cached per process). `bots` cannot import `infrastructure` (independent siblings in the layers contract), so `main.py` injects the translator.
- `bots/telegram/`: `router.py` (aiogram `Router`, `CommandStart()` + private-chat filter → use case → `t(locale, "start-greeting")` → returns `SendMessage`), `runtime.py` (lazy `Bot` + `Dispatcher` builder), `webhook.py` (FastAPI `APIRouter`, imports only FastAPI/stdlib at module level), `polling.py` (dev).

**Request path.** `POST /telegram/webhook`, root level, `include_in_schema=False` (not part of the versioned public API, so it never enters the generated TS client). Mounted by `main.py` only when both secrets are configured; otherwise a startup warning and 404.
1. Compare `X-Telegram-Bot-Api-Secret-Token` with `hmac.compare_digest` → missing/wrong: **401**, empty body, no retry value for an attacker.
2. Read the raw body, `Update.model_validate_json(...)`. Malformed (authenticated, so it is Telegram schema drift): log a warning, **200** (a retry can't fix it).
3. Dedupe: `update_id` seen → 200 empty. Else `dp.feed_webhook_update(bot, update)` awaited to completion (CPU is throttled after the response, ADR-0011; no background tasks).
4. Result is a `TelegramMethod` → **webhook reply**: 200, `application/json` `{"method": "sendMessage", "chat_id": …, "text": …}`, serialized with aiogram's own request-preparation so defaults resolve. Otherwise 200 empty. Mark `update_id` seen after success.
5. Handler exception: log (update_id, error type, no payload) and **200** (a code bug is not fixed by Telegram retrying; Phase 1 may return 503 for transient DB errors so Telegram retries).

**Webhook reply vs direct Bot API call (decision: webhook reply).** Reply-in-response saves one outbound HTTPS request from europe-west3 to `api.telegram.org` (~20–40 ms warm, plus TLS + aiohttp session setup on a cold instance, often 100+ ms) and keeps the cold path free of outbound calls. Limits: one method per update, no result (no `message_id`, no error if the user blocked the bot), no file uploads. Fine for `/start`. When a flow needs the result or more than one call (Phase 1 edits), the handler calls the Bot API directly before returning; aiogram's `AiohttpSession` is created lazily on the first such call and closed in the FastAPI lifespan shutdown. In polling mode aiogram executes the returned method itself, so handlers are identical in both modes.

**Cold start.** `import tristhana.main` must not import aiogram (keeps `/health` and future Mini App cold starts unchanged). `runtime.get_bot_runtime()` imports aiogram and builds `Bot(token)` + `Dispatcher` on the first webhook request (no network: `Bot()` only validates the token format). Measure: `python -X importtime -c "import aiogram, aiogram.types"` and first-webhook latency in the container; if aiogram import exceeds ~300 ms, revisit (pre-import in lifespan under startup CPU boost).

**Idempotency (Phase 0).** Per-instance bounded set (last 1 024 `update_id`s, `OrderedDict`). With `max-instances=2` a retry can land on the other instance; acceptable because `/start` is naturally idempotent. Phase 1 moves dedupe into the DB in the same statement batch as the user upsert.

**Settings.** `telegram_bot_token: SecretStr | None`, `telegram_webhook_secret: SecretStr | None` (stripped; secret must match `[A-Za-z0-9_-]{1,256}` per Bot API), `telegram_mode: Literal["webhook","polling"] = "webhook"`; `polling` is rejected when `app_env == "prod"`.

**Dev.** `tristhana-dev` with `TELEGRAM_MODE=polling` starts aiogram long polling for @tristhana_dev_bot in the app lifespan (same Dispatcher/router), calling `deleteWebhook` once first. Dev and prod are separate bots, so polling and webhook never conflict.

**Logging.** One line per update: `update_id`, update type, handler (or `unhandled`/`duplicate`/`malformed`), outcome, `latency_ms` (server-side, monotonic). Never the body, headers, user id, names or message text.

## 4. Ops (☁️ owner only, in order)
1. Owner adds values (stdin, never CI, never pasted to the agent): `printf %s "$TOKEN" | gcloud secrets versions add telegram-bot-token --data-file=-`; `python3 -c 'import secrets,sys;sys.stdout.write(secrets.token_urlsafe(48))' | gcloud secrets versions add telegram-webhook-secret --data-file=-`.
2. Merge: deploy job adds `--set-secrets TELEGRAM_BOT_TOKEN=telegram-bot-token:latest,TELEGRAM_WEBHOOK_SECRET=telegram-webhook-secret:latest` (only after step 1, or the deploy fails).
3. Run `tools/telegram/set_webhook.py` (stdlib only): reads the token and secret via `gcloud secrets versions access`, URL from `gcloud run services describe tristhana-api`, calls `setWebhook` with `url=<service>/telegram/webhook`, `secret_token`, `allowed_updates=["message","callback_query"]`, `drop_pending_updates=true`, `max_connections=10`; `--info` prints `getWebhookInfo` (url, pending count, last error). Never prints the token; the URL never contains it. Rotation: add version → redeploy → rerun the tool.

## 5. Migration
None (no DB). Dependencies: `aiogram` 3.x, `fluent.runtime` (pulls Babel, ~30 MB installed: check against the 250 MB image budget, currently 189 MB).

## 6. Cross-cutting checks
- **Time zones:** none; latency uses a monotonic clock; no displayed times.
- **Privacy/security:** constant-time secret compare; secrets as `SecretStr`, never logged; no payload logging; token not in URL; only private chats answered; `/docs` stays off in prod.
- **i18n:** both locales have identical key sets (CI check); fallback `en`; no hard-coded text in handlers. `.ftl` files ship as package data (container test).
- **Responsiveness:** one inbound request, zero outbound calls and zero DB round trips for `/start`; lazy aiogram and Fluent; target server time < 20 ms warm. Measure: per-update `latency_ms` log + Cloud Run request latency (p50 of 20 warm `/start`s); end-to-end checked manually (10 taps from a phone, warm and after ≥ 20 min idle); record numbers in `04 Architecture`.

## 7. Test plan
- **Domain:** `negotiate_locale` table (`ru`, `ru-RU`, `en-GB`, `None`, `""`, `de` → `en`, plus Q3 codes).
- **Use case:** `StartUseCase` returns the negotiated locale and `Greeting`.
- **i18n:** every `.ftl` parses without junk; en and ru key sets equal; `start-greeting` renders in both via the infrastructure `Translator`.
- **API contract (TestClient):** no/wrong secret → 401; correct secret + `/start` (ru, en, missing code) → 200 JSON `sendMessage` with the right `chat_id` and text; malformed JSON → 200; non-command text → 200 empty; group `/start` → 200 empty; same `update_id` twice → second is 200 empty and the handler ran once; handler raising → 200; route absent (404) without secrets; webhook not in OpenAPI.
- **Bot handler:** `/start` handler with a fake translator and use case returns `SendMessage` (aiogram objects only, no network; a `Bot` with a dummy token).
- **Architecture:** import-linter green; `allow_indirect_imports = true` on the aiogram/yaml/swisseph "only in X" contracts (main wires adapters; direct imports stay forbidden); new contract "fluent only in infrastructure"; test that `import tristhana.main` leaves `aiogram` out of `sys.modules`.
- **Settings:** `polling` in prod rejected; secrets are `SecretStr`. **Tool:** `set_webhook.py` builds the right payload (mocked HTTP), never echoes the token.
- **Container:** existing smoke stays green; `.ftl` files present; image ≤ 250 MB; `-X importtime` budget ≤ 400 ms still holds.

## 8. Open questions for the owner
1. Route path `POST /telegram/webhook` at the root (outside `/api/v1`, hidden from OpenAPI): OK, or prefer something else (e.g. `/api/telegram/webhook`)?
2. Reply via the webhook response body (webhook reply; no outbound call, no result) as the default, with direct Bot API calls only when a result is needed: OK?
3. Which `language_code`s map to Russian: `ru` only, or also `be`, `kk`, `ky` (and `uk`?) — everything else gets English?
4. Greeting text: "Namaste 🙏" plus the one "coming soon" line above, or only "Namaste 🙏"? In Russian, «Намасте» (Cyrillic) or "Namaste" (Latin)?
5. Add `/help` (and a gentle reply to other messages) now, or leave it for Phase 1?
6. Is dev long polling (`tristhana-dev` + @tristhana_dev_bot) part of this task, or a follow-up?
7. If Babel (via `fluent.runtime`) pushes the image past 250 MB, raise the budget or look for a lighter Fluent setup?

### Answers (owner, 2026-10-18)
1. Route `POST /telegram/webhook` at the root, hidden from OpenAPI: **yes**.
2. Reply via the webhook response body by default; direct Bot API calls only when a result is needed: **yes** (ADR-0012).
3. Russian for `language_code` **ru, be, kk, ky**; everything else gets English.
4. Greeting: **two lines**, RU in Cyrillic «Намасте 🙏»; ux-writer polishes.
5. **`/help` now**, plus a **gentle fallback** reply to other messages.
6. **Dev long polling is part of this task** (`tristhana-dev` + @tristhana_dev_bot).
7. If Babel pushes the image past 250 MB: first trim Babel locale data, otherwise raise the budget to 300 MB.

### Implementation notes (2026-10-18)
- **aiogram import ≈ 3.4 s** (container; 2.9 s on the host): `aiogram/types/__init__.py` rebuilds every Telegram type's pydantic schema on import. Owner chose **preload + keep-warm**: when the webhook is configured, the app builds the bot runtime **during startup** (lifespan, under Cloud Run's startup CPU boost) instead of in the background, because Cloud Run throttles CPU after a response and a background import could stall on an instance kept alive only by pings. A Cloud Scheduler job (`tristhana-keepwarm`, `infra/gcp/bootstrap.sh`) GETs `/api/v1/health` every 10 min so an instance usually stays warm.
- Measured locally (Podman): ready after ~4.0 s cold (incl. preload); `/start` webhook reply 60 ms on the first update (Fluent bundle load), ~14 ms after (incl. curl). Image 242 MB (fluent.runtime + Babel ≈ +53 MB; budget 250 MB).
- `pydantic` constraint relaxed to `>=2.11,<3`: aiogram 3.x caps pydantic below 2.14.
- Greeting copy polished by ux-writer and kept by the owner: the "logging soon" promise lives in `/help`.
