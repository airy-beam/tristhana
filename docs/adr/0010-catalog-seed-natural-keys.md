# ADR-0010: Asana catalog seed as strict YAML with natural keys
- Status: accepted
- Date: 2026-10-18
## Context
AC-01 requires asanas, variants, series and shared blocks as data, seeded from YAML and later editable by admins. Phase 1 progression ("last asana per sequence") and practice segments ("sequence ended at item X") will reference catalog items for years, so item identity must survive reseeds, reordering and admin edits. PyYAML silently accepts duplicate keys and YAML 1.1 coerces `no`/`yes` to booleans.
## Decision
- Two files: `data/seed/asanas.yaml` (catalog) and `data/seed/sequences.yaml` (six series + four blocks), with `meta.schema_version`.
- Natural keys: asana `slug` (ASCII kebab of the simple Latin name); variants are lowercase letter codes on the asana; a sequence item is identified by `(sequence slug, asana slug, variant)`, unique per sequence. Positions are derived from list order and are never used as references.
- Picker groups are derived from consecutive items of the same asana, not stored.
- Parsing happens only in `tristhana.infrastructure.seed`: PyYAML `safe_load` with duplicate-key rejection, then pydantic strict models (`extra="forbid"`), then pure domain types validated by `domain.catalog.validate_catalog`.
- The DB upsert (Phase 1) matches on natural keys and never deletes referenced items.
## Consequences
- Reseeding is idempotent and keeps row ids stable, so user history is safe.
- Renaming a slug is a migration, not a YAML edit.
- New fields (AC-04 `category`, etc.) need an explicit schema bump.
- New runtime dependency `pyyaml` (lazy-imported, infrastructure only).
## Alternatives considered
- TOML via stdlib `tomllib`: no new dependency, but deeply nested item lists are hard to read and review.
- Surrogate ids or position-based references: break when an admin inserts an asana.
- One flat `asana-variant` entity per variant: duplicates names and meanings across A–H.
- Explicit `group` labels in YAML: redundant with the asana run and can drift.
