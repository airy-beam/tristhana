# AC-01 / AC-02 (Phase 0 part): asana catalog seed files, loader and validator

- Status: draft, awaiting owner answers (§8) · Date: 2026-10-18
- Requirements: **AC-01** (asanas, variants, series and shared blocks as data, seeded from YAML, admin-editable later), **AC-02** (simple Latin display, IAST metadata, RU Cyrillic, meaning per locale). AC-04 (category, difficulty, image, tags) stays Phase 2.
- Related: ADR-0003 (layering), ADR-0007 (asana names are localized data, not `.ftl`), **ADR-0010** (seed format and natural keys, new), notes `08 Asana Catalog (draft)` (content source of truth), `05 Domain Model`

## 1. Goal and scope
**In this task (Phase 0):** `data/seed/asanas.yaml` + `data/seed/sequences.yaml` with the confirmed content, pure domain types and invariants, a strict YAML loader at the infrastructure edge, integrity tests, and a review-table renderer for the owner.
**Phase 1:** DB tables, the idempotent upsert, a `tristhana-seed` CLI, the read API, and the picker. **Phase 2:** AC-04 fields. **Phase 4:** custom sequences (AC-03).
**Out of scope:** Advanced C content (owner rule: **not seeded** until the owner provides it; the provisional chart list is not used), Advanced D content, vinyasa counts, images, admin editing.

## 2. User flows and copy
No user-facing surface in this task. Display rules for Phase 1, fixed now so the data fits them:
- EN (and any non-RU locale) shows `names.latin`; RU shows `names.ru`, falling back to Latin. IAST is shown only as secondary metadata (detail view).
- A variant is displayed as the name + uppercase code: "Marichyasana C", «Маричиасана C» (the letter stays Latin in RU).
- Picker groups are **derived**, not authored: consecutive items of the same asana form one group, labelled "Janu Sirsasana A–C".
- Series titles come from the data (`names` + `traditional_name`). Only generic UI words go into `.ftl`; reserved keys: `catalog-series-pending` ("This series will be added soon"), `catalog-optional-item`.

## 3. Domain, YAML shape, modules
**Natural keys (ADR-0010).** Asana `slug` = ASCII kebab of the simple Latin name (`utthita-hasta-padangusthasana`). Variants are lowercase codes on the asana (`variants: [a, b, c, d]`), never separate asanas. The item key is `slug` or `slug-code` (`marichyasana-e`) and is unique within a sequence. Progression and practice segments (Phase 1) reference items by this key, never by position.

```yaml
# asanas.yaml
meta: {schema_version: 1, reviewed_by: null, reviewed_on: null}
asanas:
  - slug: marichyasana
    names: {latin: Marichyasana, iast: Marīcyāsana, ru: Маричиасана}
    meaning: {en: "Pose dedicated to the sage Marichi", ru: "Поза, посвящённая мудрецу Маричи"}
    variants: [a, b, c, d, e, f, g, h]       # E–H are used by Advanced B
# sequences.yaml
sequences:
  - slug: primary
    kind: series                              # series | block
    number: 1                                 # series only, 1–6
    status: confirmed                         # confirmed | pending | placeholder
    names: {en: Primary Series, ru: Первая серия}
    traditional_name: {latin: Yoga Chikitsa, iast: Yoga Cikitsā, ru: Йога Чикитса}
    items:                                    # order = position (1-based, derived)
      - {asana: dandasana}
      - {asana: paschimottanasana, variant: a}
      - {asana: paschimottanasana, variant: c, stop: true}
      - {asana: paschimottanasana, variant: d, optional: true}
```
- `stop` (default `false`) is authored explicitly. `optional` (default `false`) means "not part of the implied practice unless enabled": Paschimottanasana D (off by default, per shala/teacher later), drop-backs, standing up, Balasana, Vrksasana, Viparita Chakrasana.
- **Enabled optional items:** an enabled optional item that directly follows a stop, in the same asana group, is included in a practice that ends at that stop (e.g. "ends at Paschimottanasana C" includes D when D is enabled; Balasana follows Sirsasana).
- **Blocks are whole-or-skipped.** "Standing only" = opening + standing + finishing, with backbending skipped. A segment can end inside a block only at the `standing` stop (Parsvottanasana).
- Blocks: `opening`, `standing`, `backbending`, `finishing`. Only `standing` has a stop point (Parsvottanasana, "standing only"). Series 5 and 6 ship with `items: []` and status `pending` / `placeholder`.
- One asana, many items: Paschimottanasana (Primary A–D + backbending, no variant), Marichyasana (Primary A–D, Adv B E–H). Vrksasana and Viparita Chakrasana are optional items in `backbending` (after drop-backs, before Paschimottanasana) for Advanced A students, as confirmed in the catalog. Non-asana entries (drop-backs, Savasana as "rest") are catalog entries too; `iast` may be `null` for them.
- `milestone: true` (default `false`) marks optional items that are also progression milestones a teacher "gives" (drop-backs, standing up), for PR-08 (Phase 2). Rule: a milestone item must be optional.
- No `category`, `reps` or `group` fields now (see Q2, Q3, Q5). Unknown fields are rejected, so adding them later is an explicit schema bump.

**Modules.**
- `domain/catalog.py` (pure): frozen dataclasses `Asana`, `AsanaNames`, `Meaning`, `Sequence`, `SequenceItem`, `Catalog`; enums `SequenceKind`, `SequenceStatus`; `validate_catalog(catalog) -> list[CatalogIssue]` (all issues, not first-fail); `item_key()`, `groups(sequence)`.
- `infrastructure/seed/catalog_yaml.py`: `load_catalog(asanas_path, sequences_path) -> Catalog`. PyYAML `safe_load` with a loader subclass that **rejects duplicate keys** (PyYAML silently overwrites them), then pydantic v2 models with `strict=True, extra="forbid"` (so YAML 1.1 coercions like `no` → `False` fail), then mapping to domain types and `validate_catalog`. New deps: `pyyaml` (runtime, lazy-imported) and `types-pyyaml` (dev); `pydantic` becomes an explicit dependency.
- `tools/catalog/render_review.py <notes-dir>`: renders both files into `08b Asana Catalog Review (generated).md` (sequence, pos, display, IAST, RU, meaning EN/RU, stop, optional). It is overwritten on each run, never hand-edited.

**Validation rules (`validate_catalog`).**
1. Slugs unique, ASCII kebab `^[a-z]+(-[a-z]+)*$`; variant codes `^[a-z]$`, unique per asana; every `slug-code` is globally unique and never equals another asana's slug.
2. Every item references an existing asana; `variant`, if given, is in that asana's `variants`.
3. An item key appears at most once per sequence.
4. Every asana and every declared variant is used by at least one item (no orphans, so no unconfirmed Adv C entries slip in).
5. Series numbers are exactly 1–6, each once; blocks are exactly the four slugs.
6. `confirmed` series are non-empty; `pending`/`placeholder` series are empty.
7. Every confirmed series has ≥ 1 stop point, and its **last non-optional item is a stop point** (no series can end on a non-stop item).
8. Optional items are never stop points. `standing` ends with a stop point; other blocks have none.
9. `names.latin`: ASCII letters, spaces, hyphens. `names.ru`: Cyrillic letters (ё not used), spaces, hyphens only. `names.iast`: NFC-normalized, Latin letters plus `āīūṛṝḷḹṅñṭḍṇśṣṃḥ` (anusvāra is ṃ, never ṁ) (and capitals), spaces, hyphens. All strings trimmed, single-line, non-empty; `meaning.ru` contains Cyrillic.

## 4. API endpoints
None in this task. Phase 1 sketch: `GET /api/v1/catalog?locale=` returns asanas and sequences with derived groups (public read, ETag by content hash, cached in-process).

## 5. DB migration outline (Phase 1, not this task)
- `asana(id, slug unique, names jsonb, meaning jsonb, variants text[])`
- `sequence(id, slug unique, kind, number null unique, status, names jsonb, traditional_name jsonb)`
- `sequence_item(id, sequence_id, position, asana_id, variant null, is_stop_point, is_optional)`, unique `(sequence_id, asana_id, variant)` (nulls not distinct) and deferrable unique `(sequence_id, position)`.
- **Idempotent upsert** (one transaction): upsert asanas by `slug`, sequences by `slug`, items by `(sequence, asana, variant)` (row ids stay stable, so progression references survive), then rewrite positions. Removing an item that is referenced by progression/practice fails loudly instead of deleting. Running twice is a no-op. Once admin editing exists, the seed switches to insert-missing only (Q6).

## 6. Cross-cutting checks
- **Time zones:** not applicable; the catalog holds no times or dates.
- **Privacy:** no personal data. Meanings must be original wording, not copied from copyrighted sites or books.
- **i18n:** names and meanings are localized data (ADR-0007), so adding a locale means adding keys in the YAML; RU names are Cyrillic transliteration, never translation. Only generic UI words live in `.ftl` (§2).
- **Responsiveness:** YAML is parsed only by the seed CLI and tests, never on a request path; `yaml` is lazy-imported. In Phase 1 the catalog (~200 asanas, ~250 items) is loaded once per instance and cached, so the picker needs no catalog query per tap.
- **Layering (import-linter):** `domain.catalog` stays pure. New forbidden contract: `yaml` is allowed only in `tristhana.infrastructure`; add `pydantic` to the forbidden list for `tristhana.domain`.

## 7. Test plan
- **Domain unit (`validate_catalog`):** one minimal in-code catalog per rule 1–9, each asserting the specific issue, plus a valid one; `groups()` labels ("Janu Sirsasana A–C", single asana, mixed runs).
- **Loader:** duplicate key, unknown field, `variant: no` (bool coercion), a missing file, and a bad charset each raise with file + path in the message.
- **Integrity on the real files:** loads with zero issues; golden facts: Primary ends at `setu-bandhasana` (stop), half primary stop at `navasana`, `utthita-trikonasana-b` is not a stop, `paschimottanasana-d` is optional and not a stop, `standing` ends at `parsvottanasana`, Intermediate ends at `baddha-hasta-sirsasana-d`, Advanced B ends at `omkarasana` and contains both `samanasana` and `sama-konasana`, series 5/6 are empty with the right status, `meta.reviewed_on` is reported (warning in Phase 0, required by a Phase 1 release check).
- **Use case, API contract, bot handler tests:** not applicable (Phase 1: upsert idempotency against Postgres, catalog endpoint contract).
- **Gates:** pyright strict, ruff, `lint-imports` with the new contract.

**Content workflow:** the `ashtanga-expert` agent drafts all IAST, RU names and meanings (~200 entries); the owner reviews the generated table; corrections go into the YAML and `03 Open Questions & Decisions`; the owner then sets `meta.reviewed_by/reviewed_on`. **IAST and meanings must be owner-reviewed before any Phase 1 user sees them.**

## 8. Open questions for the owner
1. Meanings: draft them now with the names (one review pass), or ship names first and add meanings later in Phase 1? Recommendation: now.
2. Repetitions (Surya Namaskara A ×5, B ×3–5, Urdhva Dhanurasana ×3): keep them out of the data for now (nothing in Phase 1 uses them), or add an optional `reps`? Recommendation: out.
3. Parenthesised groups, "Kapotasana (A, B)" and "Sirsasana (A, B)": model as two variant items with only B as the stop point (like Virabhadrasana A, B)? Or can a student stop at Kapotasana A?
4. Optional items (Paschimottanasana D, drop-backs, Balasana): seed them with `optional: true` (recommended), or leave them out until the shala setting exists? And Vrksasana and Viparita Chakrasana after backbends for Advanced A students: optional items in the shared `backbending` block, (confirmed in the catalog; recommended: optional items in `backbending`).
5. `category` now as an optional field, or with the rest of AC-04 in Phase 2? Recommendation: Phase 2, because the taxonomy is not confirmed yet (is Marichyasana C a twist or a forward bend?) and it doubles the review work.
6. Advanced B "every asana/variant group is a stop point": in a group like Marichyasana E–H or Nahusasana A–C, is only the last variant a stop (as with Virabhadrasana), or every variant (as with Marichyasana A–D in Primary)?
7. After admin editing ships, should the seed file stay authoritative (overwrites admin edits) or become insert-missing only? Recommendation: insert-missing only.

### Answers (owner, 2026-10-18)
- Q1 meanings drafted now · Q2 no repetitions in data · Q4 optional items seeded with `optional: true` (Paschimottanasana D, drop-backs, standing up, Balasana, Vrksasana, Viparita Chakrasana) · Q5 `category` in Phase 2 · Q7 once admin editing exists, the seed inserts missing items only.
- Q3: Kapotasana A, B: one stop, after B (like Virabhadrasana). Sirsasana A, B are plain finishing items.
- Q6: **Advanced B: every variant is a stop point** (Nahusasana A, B, C, Marichyasana E…H, etc.), as is every single asana.
- Drop-backs and standing up are optional backbending items **and** progression milestones (`milestone: true`).
- RU convention: transliterate from IAST (ś/ṣ → ш, kṣ → кш, ṛ → ри, c → ч, j → дж, consonant + h → х; no long-vowel or retroflex marks; y → ь/й/я; ё not used). Variant letters stay Latin. Surya Namaskara in RU is **«Сурья Намаскар»** (community spelling).
- Slugs are permanent: the owner confirms the slug list once in the review table before `reviewed_on` is set.
- **Seed path (Phase 1):** `data/seed/` lives outside the backend package. The Phase 1 seed command takes the directory as an argument/setting (`SEED_DIR`, default: repo `data/seed`), and the container image copies `data/seed/` next to the app. `load_catalog` validates and raises on any issue; `read_catalog` (no validation) is for review tooling only.
- **Picker rule:** a practice that ends at a stop includes enabled optional items directly after it in the same group (Paschimottanasana D after C).
