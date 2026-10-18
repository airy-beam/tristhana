# ADR-0017: Asana catalog served from memory; practices reference it by natural key
- Status: accepted
- Date: 2026-10-18
## Context
AC-01 (ID-01 spec Q3) put off seeding the catalog into the DB until "the first feature that reads it". That feature is PR-03: the practice-length picker, its presets and stored practice end points. The catalog is small (143 entries, 177 sequence items), read-only today, already shipped in the image (`/app/data/seed`, validated by the container smoke test) and loaded by a strict loader into pure domain types (ADR-0010). Admin editing (AC-01, "editable by platform admins") has no requirement date yet. Every bot tap must stay under 300 ms p50, and the image is at ~245 MB of a 250 MB budget.
## Decision
- Load `data/seed/*.yaml` once per process, in the FastAPI lifespan (startup CPU boost), into the domain `Catalog`. An invalid catalog stops startup. `Catalog.version` = the first 12 hex digits of the SHA-256 of both files.
- Use cases receive the `Catalog` as an immutable value from the composition root (no port, no I/O). Picker screens, presets and length validation read no DB.
- Stored practice data references the catalog by **natural keys as text** (series slug, item key such as `kapotasana-b`), checked by the domain on write (stop points of confirmed series only). No FKs to catalog tables, since there are none.
- `GET /api/v1/catalog` serves the picker projection with `ETag: "<version>"` and a public cache header.
- When admin editing arrives: add catalog tables keyed by the same natural keys (text PKs), seed them with "insert missing" (ADR-0010), then add FKs from practice columns `NOT VALID` and `VALIDATE` them. Stored data needs no rewrite.
## Consequences
- No migration, no DB round trip and no new dependency for catalog reads. Startup pays one YAML parse (expected well under 100 ms; measured in the implementation).
- The DB can't stop a bad key. Mitigations: domain validation on every write; renaming a slug stays a migration (ADR-0010), now also rewriting `practice` rows; readers tolerate unknown keys (show the raw key, log a warning, never fail).
- A catalog change ships with a deploy (as today). All instances run the same image, so they agree on the version.
## Alternatives considered
- Seed catalog tables now (`asana`, `sequence`, `sequence_item`) with FKs from practices: real integrity, but it needs a seed job in the deploy pipeline and either a DB read per picker screen or an in-memory cache anyway. It also builds admin-editing infrastructure before anyone needs it.
- Keep the YAML parse per request: needlessly slow.
- Compile the YAML to JSON or Python at build time: a faster startup, but one more build step to keep in sync; worth revisiting only if the measured parse cost hurts.
