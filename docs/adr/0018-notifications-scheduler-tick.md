# ADR-0018: Notifications on a scheduler tick, computed per run, with a delivery ledger
- Status: accepted
- Date: 2026-10-19
## Context
MD-03 (moon reminders) is the first proactive message; PR-10 (practice reminder), class reminders and recaps follow. Reminders fire at a wall-clock hour in the recipient's IANA zone with quiet hours and a daily cap (NT-02, ADR-0005). Cloud Run throttles CPU outside requests (ADR-0011), so nothing may run in the background. Cloud Scheduler's free tier is 3 jobs per billing account; keep-warm (every 10 min) and the weekly backup use 2. The image is at ~245 of 250 MB. `application` must stay free of aiogram (ADR-0003). Spec: `docs/specs/MD-03-moon-reminders.md`.
## Decision
- **Trigger:** one Cloud Scheduler job `tristhana-tick`, every 10 min, `POST /internal/tick` on the existing service. It also pings the DB, so it **replaces** `tristhana-keepwarm`. All periodic work (reminders, moon calendar top-up, ledger pruning) runs inside that request with a 40 s deadline; leftovers go to the next tick.
- **Auth:** header `X-Tristhana-Tick-Token` compared in constant time with a value from Secret Manager (`internal-tick-token`); a mismatch returns 404. The route is hidden from OpenAPI and mounted only when the token is configured.
- **No materialised outbox:** each tick computes what is due from current settings, zone and calendars with a pure domain function (`send_at ≤ now < send_at + 3 h`, not in quiet hours, under the cap). Settings or zone changes therefore need no rescheduling.
- **Ledger:** `notification_delivery(account_id, dedupe_key)` is claimed with `INSERT … ON CONFLICT DO NOTHING` **before** sending (at most once across instances and scheduler retries), then finished as `sent | failed | blocked`. Transient failures retry on later ticks (≤ 3 attempts, within the grace window). A blocked bot pauses the account until it is seen again.
- **Ports:** `application` emits semantic notifications (`MoonReminder`, later `PracticeReminder`) to a `Notifier` port. The Telegram adapter in `bots/telegram` renders text and buttons (Translator, callback codec) and maps Bot API errors to a `DeliveryResult`. Sends are paced (≤ 8 concurrent, ≤ 25 msg/s); a 429 stops the batch.
## Consequences
- No new infrastructure or dependency; scheduler use stays at 2 of 3 free jobs; latency is ≤ 10 min after the chosen minute.
- If the tick breaks, keep-warm breaks too; the first tick log after each deploy is the check.
- The header secret sits in the Scheduler job config, readable by project viewers (only the owner today). Rotation = new secret version + re-run bootstrap.
- At-most-once means a crash between claim and send loses that one reminder. Acceptable for reminders; revisit for anything transactional.
- The per-tick candidate query scans every account with reminders on (~2 rows each); fine to ~10k accounts, then filter by send hour in SQL.
## Alternatives considered
- **Scheduler OIDC token verified in the app:** standard and secret-free, but needs `google-auth` (~2–3 MB) and an outbound Google cert fetch on cold ticks. Revisit if the image budget grows or a second internal caller appears.
- **A separate IAM-protected Cloud Run service or a Cloud Run Job per tick:** Google verifies the caller, but a second deployable (or a container cold start with the 8.8 s aiogram import every run) and no keep-warm effect.
- **A third scheduler job next to keep-warm:** lower blast radius, but uses the last free slot for the same cadence.
- **Materialised outbox rows (`due_at`):** must be rewritten on every settings, zone or calendar change; computing per tick is simpler at this scale.
- **Background tasks or an in-process scheduler:** starved by CPU throttling, and lost on scale-to-zero.

## Operations (added with the implementation, 2026-10-19)
- **Deploy order:** (1) `bootstrap.sh` creates the `internal-tick-token` secret container and grants the runtime SA access; (2) the owner adds a value via stdin; (3) merge: the deploy maps `INTERNAL_TICK_TOKEN=internal-tick-token:latest` (a secret without a version would fail `gcloud run deploy`) and the migrate job applies 0004 first; (4) `bootstrap.sh` again creates the `tristhana-tick` job; (5) after a tick returns 200 in the logs, delete `tristhana-keepwarm`.
- **The token on the command line:** creating the scheduler job passes `--headers X-Tristhana-Tick-Token=…` to gcloud, so the value is briefly visible in the local process list and may land in gcloud's local logs (`~/.config/gcloud/logs`). Accepted for a single-owner machine; rotate the secret (add a version, re-run bootstrap) if those logs are ever shared. OIDC with audience verification stays the upgrade path if more people get project access.
- **Robustness:** sends have a 10 s Telegram timeout and the deadline is checked before every claim; a claim left behind by a cut-off run is taken over after 5 minutes (still within the 3 h grace, so at most once per reminder).
