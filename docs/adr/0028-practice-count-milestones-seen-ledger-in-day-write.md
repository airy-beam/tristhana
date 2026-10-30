# ADR-0028: Practice-count milestones: a "seen" ledger written inside the day-status statement
- Status: accepted (2026-10-30, owner)
- Date: 2026-10-30
## Context
GM-01 part 2 celebrates 100 / 365 / 1000 practised days. ADR-0026 derives asana celebrations from the progression history, but practice counts are **not monotonic**: a day can be cleared, changed from 🧘 to rest, or backfilled, so "the count is now 100" can happen more than once. The trigger is the day-status write (bot `/log` and `/start`, reminder ✅/🧘, Mini App Today card and calendar backfill), the hottest path, which is one statement per tap today (`SqlDayLogRepository.upsert` / `insert_if_absent`, < 300 ms p50 target). Existing accounts may already be past a threshold at deploy, and thresholds should be data so more can be added later. Spec: `docs/specs/GM-01-practice-counts.md`.
## Decision
- **Ledger:** `practice_milestone(account_id, threshold, celebrated, reached_at)`, PK `(account_id, threshold)`, cascades with the account. A row means "seen"; it is never deleted except by account delete.
- **Rule:** only when a write makes a day Practiced that wasn't, `after` = practised days including it; every threshold ≤ `after` is inserted `ON CONFLICT DO NOTHING`; the inserted row equal to `after` is the celebration (`celebrated = true`), others are silent seeds. Clearing or changing a day away never touches the ledger, so a later rise is quiet.
- **Same statement:** two CTEs (`count(*)` over the account's practised rows, excluding the written date, + 1; the ledger insert `RETURNING`) are added to the existing day upsert / reminder insert, gated by the statement's existing "was not practiced" / "was empty" snapshot predicates. Non-🧘 writes run unchanged SQL.
- **Thresholds** come from `data/seed/milestones.yaml` (in memory, ADR-0017 pattern) and are passed to the repository as an `int[]` parameter. The pure rule lives in `domain/milestones.py`; the SQL mirrors it, checked by a parity test.
- **Delivery:** only in the reply to the person's own tap (no push), so no NT-01 toggle yet.
## Consequences
- Zero extra round trips; one small per-account aggregate on 🧘 writes only (≈ 365 rows after a year, ≈ 9 000 worst case). If a timing test shows > 5 ms on 9 000 rows, add a partial index `day_log (account_id) WHERE status = 'practiced'`.
- Existing users and thresholds added later are seeded silently and lazily on the next 🧘 write; no data migration. Edge: someone past 100 at deploy whose first write is clearing down to 99 and logging again sees 100 once (never seen before, so harmless).
- A mis-tap that crosses a threshold spends it, even if it is cleared at once.
- Concurrent 🧘 writes at the same count produce one ledger row (PK), so at most one 🎉.
- A lost HTTP reply loses the card; the ledger row stays (accepted, as in PR-08).
- The repository port takes the thresholds, and `Upserted` / `Inserted` carry `reached`; the ledger is exported (ST-09) and cascades on delete.
- GM-02 badges (e.g. 108) can reuse the ledger *pattern* under their own kind/key. Adding a number to `practice_counts` means a 🎉 count line, not a badge.
## Alternatives considered
- **Derive at write time without a ledger** (celebrate when `after` equals a threshold): re-celebrates after clear-and-relog and on every 🧘 ↔ rest toggle at 100.
- **A counter column on `account`:** O(1) reads, but a second hot row per write, drift from races, the old revision during deploys and backfills, and repair jobs.
- **A separate check after the write** (second statement, or only "when the count could cross"): an extra round trip on the hottest path, or needs the count anyway.
- **An asynchronous job or push** that detects crossings: needs the NT-01 toggle, delivery state and quiet hours, and celebrates away from the moment of the tap.
- **Seeding the ledger in the migration:** removes the edge above, but hard-codes today's thresholds in a migration and doesn't cover thresholds added later; the lazy seed covers both.
