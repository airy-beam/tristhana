# ADR-0004: GCP Cloud Run + Supabase Postgres + Firebase Hosting
- Status: accepted · Date: 2026-10-18
## Context
Hobby budget (≤ $5/mo). Must be **responsive**: the old sashas-bot on Yandex Functions was slow (cold starts with heavy imports, many DB round trips, blocking SDK).
## Decision
Cloud Run (europe-west3, scale-to-zero, startup CPU boost), Cloud Scheduler tick every 5 min (also keeps it warm), Supabase Postgres in eu-central-1 (always-on free tier, used as plain Postgres), Firebase Hosting for the Mini App, Secret Manager, GitHub Actions with WIF.
## Alternatives
Neon (free tier suspends after 5 min → stacked cold starts), Cloud SQL (≈ $10+/mo), Firestore (poor relational fit), AWS Lambda (more setup), Yandex Cloud (fallback for RU reachability).
## Risks
Reachability of Google domains from Russia; test in Phase 1.
