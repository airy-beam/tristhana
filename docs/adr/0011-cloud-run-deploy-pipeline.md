# ADR-0011: Cloud Run deploy pipeline (reuse project, WIF, deploy on main)
- Status: accepted · Date: 2026-10-18
## Context
ADR-0004 chose Cloud Run in europe-west3 with GitHub Actions and Workload Identity Federation. We needed concrete choices for the project, the identities and when to deploy. Spec: `docs/specs/NF-02-cloud-run-deploy.md`.
## Decision
- Reuse the existing GCP project `braided-trees-444417-u6` ("tristhana-bot"). No cloud dev environment: dev is local polling with @tristhana_dev_bot.
- One service `tristhana-api` in europe-west3: scale to zero, `max-instances=2`, request-based CPU, startup CPU boost, public invoker (the webhook is authenticated by Telegram's secret header; `/internal/*` by OIDC later).
- Two service accounts: a runtime SA with no project roles (secret access granted per secret) and a deployer SA with `run.developer`, `iam.serviceAccountUser` on the runtime SA only, and `artifactregistry.writer` on the repo only. GitHub authenticates through WIF restricted to the numeric repository id and `refs/heads/main`. No JSON keys.
- Every push to `main` builds an image (pushed by digest) and deploys it, followed by a smoke check that `/api/v1/health` reports the new commit. `workflow_dispatch` redeploys.
- GCP resources are created by a reviewed, idempotent `infra/gcp/bootstrap.sh` (`--dry-run` first), not Terraform.
- The repository is public under AGPL-3.0 (ADR-0009).
## Consequences
Near-zero cost and no long-lived credentials. CPU is throttled outside requests, so handlers must finish their work before responding. A budget alert ($5) warns but does not cap spend; `max-instances` is the cap.
## Alternatives considered
A fresh project (cleaner ID, more setup); Terraform (overkill for ~10 resources); deploying on tags only (slower feedback for a solo project); `run.admin` for CI (broader than needed).
