# NF-02 / NF-03 / NF-07: GCP project, container image, Cloud Run deploy via GitHub Actions (WIF)

- Status: confirmed by the owner (answers in §8) · Date: 2026-10-18
- Requirements: **NF-02** (≤ ~$5/mo, scale-to-zero), **NF-03** (secrets in a secret manager; least privilege), **NF-07** (structured logs). Latency budget from `04 Architecture`: < 1.5 s cold, < 300 ms p50 warm.
- Related: ADR-0004 (Cloud Run europe-west3, Secret Manager, GitHub Actions + WIF), ADR-0009 (pyswisseph sdist → compiler in the builder only; AGPL), AC-01 spec (`SEED_DIR`, image copies `data/seed/`). Next item: Telegram webhook (`/start` → "Namaste 🙏").

> **Legend.** ☁️ = creates/changes cloud or GitHub resources, or can cost money. ☁️ steps run **only after the owner approves**, in the order of §5. Everything else is local files + CI.

## 1. Scope
**In (this task):** `backend/Dockerfile`, root `.dockerignore`, a tiny serve entry point, settings changes, `infra/gcp/bootstrap.sh` (idempotent, with `--dry-run`), a CI `image` job (build + container smoke test on every PR), a `deploy` job (main only), a post-deploy smoke check, an image-size/startup budget, local Podman verification.
**Later:** Cloud Scheduler + `POST /internal/tick` (with jobs, Phase 1), Telegram webhook route + `setWebhook` (next item), Firebase Hosting (with the Mini App), **Supabase (defer to Phase 1, Q4)**, custom domain, error alerts to an admin Telegram chat (NF-07 part 2, needs the bot), Cloud Logging trace correlation.
**Out:** Terraform (a reviewed shell script is enough for ~10 resources), a cloud dev environment (dev = local polling with @tristhana_dev_bot).

## 2. Flows and copy
No user-facing surface, no `.ftl` keys. Operator flows: (a) PR → `checks` + `image` jobs; (b) merge to main → `checks` → `image` (push by digest) → `deploy` → smoke; (c) `workflow_dispatch` redeploys a given commit.

## 3. Design (no domain changes, no use cases, no ports)
**Image (`backend/Dockerfile`, build context = repo root).**
- Builder: `ghcr.io/astral-sh/uv:python3.13-bookworm` (has gcc for pyswisseph). `UV_COMPILE_BYTECODE=1` (precompiled `.pyc` cuts cold-start import time), `UV_LINK_MODE=copy`, `UV_PYTHON_DOWNLOADS=never`. Two layers: `uv sync --locked --no-dev --no-install-project` (deps, cached), then `uv sync --locked --no-dev --no-editable` (project as a wheel, so `moon/ephe/*.se1` must ship as package data: test asserts it).
- Runtime: `python:3.13-slim-bookworm`, same Python minor as the builder; copy only `/app/.venv` and `data/seed/` → `/app/data/seed`; no compiler, no uv, no dev deps. Non-root user (uid 10001), `WORKDIR /app`, `ENV PATH=/app/.venv/bin:$PATH SEED_DIR=/app/data/seed PYTHONUNBUFFERED=1`, `ARG/ENV GIT_SHA`. No `TZ` (container stays UTC; `tzdata` from PyPI provides zones).
- Entry: `CMD ["tristhana-serve"]`, a new script `tristhana.serve:main` that calls `uvicorn.run("tristhana.main:app", host="0.0.0.0", port=settings.port, workers=1, proxy_headers=True, forwarded_allow_ips="*", access_log=False, log_config=None, timeout_graceful_shutdown=8)`. Rationale: exec-form CMD can't expand `$PORT`; `log_config=None` keeps our JSON logging; Cloud Run already writes a request log, so uvicorn's access log is noise; `"*"` is safe because only Google's front end reaches the container.
- `.dockerignore`: allowlist (`*`, then `!backend/pyproject.toml !backend/uv.lock !backend/README.md !backend/src !data/seed`), excluding `**/__pycache__`, `.venv`, tests.

**Settings (`tristhana/settings.py`).** Add `port: int = 8080` (env `PORT`, set by Cloud Run), `seed_dir: Path` (default: repo `data/seed` resolved for dev; image sets `/app/data/seed`), `git_sha: str = "dev"`. Prod gets `APP_ENV=prod` via `--set-env-vars`; `LOG_FORMAT` then defaults to json. Secrets are plain env vars injected by `--set-secrets` and typed `SecretStr` when they arrive (next item adds `telegram_bot_token`, `telegram_webhook_secret`). The app never calls the Secret Manager API (no client lib, no startup latency).

**Cloud Run service** `tristhana-api` (Q5), europe-west3, `--min-instances=0 --max-instances=2` (cost + abuse cap, Q6), `--cpu=1 --memory=512Mi --concurrency=80 --timeout=60s --cpu-boost --cpu-throttling` (request-based billing → free tier), `--ingress=all`, public invoker (Telegram must reach the webhook; it is authenticated by the secret header, `/internal/*` later by OIDC). Service account = runtime SA. Execution environment: measure gen1 vs gen2 cold start once, keep the faster (record result).
- **Consequence for the webhook (next item):** with CPU throttling, work after the HTTP response is starved. Handlers must finish (or use webhook-reply) **before** returning 200; no fire-and-forget tasks. `setWebhook` is a one-off command after deploy, never at startup (no outbound calls on the cold path).

**GCP resources (`infra/gcp/bootstrap.sh`, idempotent: describe-before-create, `set -euo pipefail`, no `set -x`, `--dry-run` prints commands).** All ☁️.
1. Enable APIs: run, artifactregistry, secretmanager, iamcredentials, sts, billingbudgets (cloudscheduler later).
2. Artifact Registry Docker repo `tristhana` in europe-west3 + cleanup policy (keep 5 newest tagged, delete untagged > 7 d) to stay under the 0.5 GB free storage.
3. Runtime SA `tristhana-run@`: **no project roles** (stdout logs are collected by the platform); `roles/secretmanager.secretAccessor` granted **per secret**.
4. Deployer SA `tristhana-deploy@`: `roles/run.developer` (project; the only service), `roles/iam.serviceAccountUser` **on the runtime SA only**, `roles/artifactregistry.writer` **on the repo only**. Not `run.admin`: the public-invoker binding is set once by bootstrap, so CI never needs `setIamPolicy`.
5. WIF pool `github` / OIDC provider `github-actions` (issuer `token.actions.githubusercontent.com`), mapping `google.subject=assertion.sub`, `attribute.repository_id`, `attribute.ref`; **attribute condition** `assertion.repository_id == '<id of airy-beam/tristhana>' && assertion.ref == 'refs/heads/main'` (numeric id survives renames and blocks repo-name squatting). `roles/iam.workloadIdentityUser` on the deployer SA for `principalSet://…/attribute.repository_id/<id>`. No JSON keys anywhere.
6. Secret containers (no values): `telegram-bot-token`, `telegram-webhook-secret`; later `database-url`, `field-encryption-key`, `jwt-signing-key`. Values are added by the owner with `gcloud secrets versions add NAME --data-file=-` (stdin, not shell history). The deploy references a secret only once it has a version (`:latest` with no version fails the deploy), so this task deploys with no secrets.
7. First deploy of a placeholder (`us-docker.pkg.dev/cloudrun/container/hello`) with the settings above, then `allUsers` → `roles/run.invoker`. CI from then on only updates the image.
8. Budget $5/month on billing account `01CBF7-6E2154-3A850B`, scoped to the project, thresholds 50/90/100 % actual + 100 % forecast, emails to billing admins (Q2). Budgets alert; they **do not cap** spend (max-instances does).
9. ☁️ GitHub: repo **variables** (not secrets; nothing here is sensitive) `GCP_PROJECT_ID`, `GCP_REGION`, `GCP_WIF_PROVIDER`, `GCP_DEPLOY_SA` via `gh variable set`.

**CI (`.github/workflows/backend.yml`).**
- `image` job (PRs and main, `needs: checks`): hadolint; shellcheck `infra/**/*.sh`; `docker buildx build` with GHA cache, `--build-arg GIT_SHA`; container smoke test (§7). On main only: WIF auth (`google-github-actions/auth`, `permissions: id-token: write, contents: read`), push `…/tristhana/backend:<sha>`, output the digest.
- `deploy` job (main push + `workflow_dispatch`, `needs: image`, `concurrency: {group: deploy-prod, cancel-in-progress: false}`): `gcloud run deploy tristhana-api --image …@sha256:<digest> --set-env-vars APP_ENV=prod,GIT_SHA=<sha>` (plus `--set-secrets` from the next item). Third-party actions pinned by commit SHA. Then smoke: `GET /api/v1/health` must return 200 with `commit == <sha>` within 60 s of retries; log time of the first request and p50 of 10 warm requests (from a US runner, so network RTT dominates: report, fail only if first > 5 s).
- Note the existing `paths:` filter: infra-only changes won't deploy; use `workflow_dispatch`.

**Budgets.** Runtime image ≤ 250 MB uncompressed (CI fails above); `python -X importtime -c "import tristhana.main"` ≤ 400 ms locally; container start → first 200 on `/health` ≤ 1.0 s locally; cloud cold first request ≤ 1.5 s (measured manually after ≥ 20 min idle, server latency read from the Cloud Run request log); warm p50 server latency < 50 ms for `/health`, leaving headroom for the 300 ms bot budget.

**Cost (NF-02).** Cloud Run request-based free tier, Secret Manager (6 active versions, 10k accesses free), AR 0.5 GB free, WIF/budgets/IAM free. Expected $0. Verify that the free tier applies in europe-west3 (a Tier 2 price region) on the pricing page before the first deploy.

## 4. API
`GET /api/v1/health` (public, no I/O) gains `commit: str` (from `GIT_SHA`) so the smoke check proves the new revision serves. Additive OpenAPI change; regenerate the Mini App client when it exists.

## 5. Migration and rollout order
No DB. Order: (1) Dockerfile, serve, settings, CI `image` job, bootstrap script with `--dry-run`, merged after review; (2) local Podman verification (below); (3) ☁️ owner reviews `bootstrap.sh --dry-run` output, then runs it; (4) ☁️ set GitHub variables; (5) ☁️ merge/dispatch → first real deploy → smoke; (6) record measured cold/warm numbers in `04 Architecture`.
**Local verification (Podman):** `podman build -f backend/Dockerfile -t tristhana:local .` · `podman image inspect --format '{{.Size}}'` · `podman run --rm -p 8080:8080 -e APP_ENV=prod tristhana:local` and time from start to first 200 · `podman run --rm --entrypoint id tristhana:local -u` (≠ 0).

## 6. Cross-cutting checks
- **Time zones:** container runs UTC, no `TZ`; zone data from the `tzdata` wheel (test `ZoneInfo("Asia/Almaty")` in the image). Budget alerts are monthly per billing account; nothing user-facing.
- **Privacy/security:** no user data yet. No secrets in the repo, workflow, logs or image layers; secret values never pass through CI. The future webhook URL must not contain the bot token (secret header instead). Uvicorn access log is off, and we never log headers or bodies (the Telegram secret header and initData stay out of logs). `/docs` already disabled in prod.
- **i18n:** none now. Future `.ftl` files must ship as package data; the image test will check they exist once added.
- **Responsiveness:** precompiled bytecode, slim image, single uvicorn worker with uvloop/httptools, no outbound calls or secret fetches at startup, startup CPU boost, lazy heavy imports (swisseph only in `tristhana.moon`). Warm keeping comes from the scheduler tick later (Phase 1), not min-instances (cost).

## 7. Test plan
- **Unit:** `Settings` reads `PORT`, `SEED_DIR`, `GIT_SHA`; `serve.main` passes `proxy_headers`, `workers=1`, `access_log=False`, `log_config=None` (patch `uvicorn.run`). JSON log line has `severity` + `message` (exists).
- **API contract:** `/api/v1/health` returns `{status, version, commit}`; OpenAPI snapshot includes `commit`.
- **Container (CI `image` job, every PR):** build succeeds; hadolint clean; uid ≠ 0; `gcc` and `pytest` absent; `python -c "import swisseph"` works and the `.se1` files are present in the installed package; one known moon date computes from the installed (non-editable) package (e.g. a 2025 Mysuru Purnima from the golden set); `SEED_DIR` exists with both YAML files (and `load_catalog` passes once AC-01 is merged); `ZoneInfo` loads; container start → `/api/v1/health` 200 within 5 s in CI; size ≤ 250 MB.
- **Scripts:** shellcheck on `infra/gcp/*.sh`; `bootstrap.sh --dry-run` runs in CI without credentials (prints, creates nothing).
- **Post-deploy:** smoke as in §3. **Bot handler / use case tests:** not applicable.

## 8. Open questions for the owner
1. Reuse the existing project `braided-trees-444417-u6` ("tristhana-bot", billing linked; the ID can't be renamed but only shows in Artifact Registry paths, since `run.app` URLs use the project number), or create a fresh `tristhana-prod`? And a separate dev project, or none (dev = local polling)? Recommendation: reuse, no dev project.
2. Budget alert: $5/month to the billing-account admin email (default), or another address / extra thresholds?
3. Region: keep europe-west3 (ADR-0004, near Supabase eu-central-1) even if it is a Tier 2 price region, or switch to a Tier 1 EU region if the free tier differs?
4. Supabase: create the project now, or defer to Phase 1 when the DB lands? Recommendation: defer (an unused free project pauses after 7 days idle, and the free plan allows only 2 projects).
5. Service name `tristhana-api` (it serves API + bot webhook), or another name?
6. `max-instances=2` OK as the cost/abuse cap?
7. Deploy on every push to main (recommended for a solo project, with manual dispatch for redeploys), or only on tags / manual dispatch?
8. AGPL (ADR-0009): once deployed with a public invoker, the `*.run.app` URL is reachable by anyone, though it serves only `/health` until the webhook lands. Make the repo public now, or at the point real users can use the bot (private beta)? Flag only, not legal advice.
9. OK to add `commit` to the health response and a `tristhana-serve` entry point?

### Answers (owner, 2026-10-18)
1. **Reuse** `braided-trees-444417-u6` ("tristhana-bot"); no dev project (dev = local polling).
2. Budget **$5/month** to the billing-account admin email, thresholds 50/90/100 % actual + 100 % forecast.
3. **Keep europe-west3** (next to Supabase eu-central-1); watch spend via the budget alert. The free-tier treatment of Tier 2 regions is unconfirmed.
4. Supabase **deferred to Phase 1**.
5. Service name **`tristhana-api`**. 6. **max-instances 2**. 7. Deploy on **every push to main** + manual `workflow_dispatch`.
8. **Make the repo public now** under **AGPL-3.0** (add `LICENSE`), after a secret scan of the full git history. Branch protection becomes available on the free plan once public.
9. Add `commit` to `/api/v1/health` and the `tristhana-serve` entry point: **yes**.
