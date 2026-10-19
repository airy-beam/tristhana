# ADR-0020: Practice stats computed server-side in the domain; heatmap drawn as plain SVG (no ECharts)
- Status: accepted
- Date: 2026-10-19
## Context
ST-01..03 add a year heatmap, a month summary and consistency/run metrics to the Mini App. The rules are domain rules: rest-like days are transparent, "No practice" ends a run quietly, unlogged days never count against anyone (Q18), and ladies' holiday must be projected to "rest" for anyone but the owner. The same numbers will later appear in the bot, in teacher views (ST-06), on share cards (ST-07) and in milestones (GM-01). `04 Architecture` planned Apache ECharts (lazy-loaded) for the heatmap. The Mini App's initial JS is 110.6 of 150 KB gzip, and NF-09 asks for a fast first load on 4G, including Russian networks.
## Decision
- Stats are computed by a **pure `domain/stats.py`** (cells, period summaries, runs) called by one use case, `GetYearStats`, and served by one endpoint, `GET /api/v1/me/stats?year=`. One request returns the whole year (cells, 12 month summaries, year total, runs, moon markers), about 8 KB, from 2 indexed statements. The client only draws.
- Every reader other than the owner (teacher, shala, share card) gets its stats from days passed through `public_status` (and a policy check) **before** they reach `domain/stats.py`. The owner's response may contain `ladies`; hiding it on the owner's own screen is presentational.
- The heatmap and month calendar are **hand-written SVG/CSS grids** in a lazily loaded Stats chunk. ECharts is dropped from the plan. Revisit it only when a chart needs real interaction (ST-05 trends).
## Consequences
- The rules are tested once, in Python, with fixed examples. The bot, ST-06 and ST-07 reuse them without a second (TypeScript) implementation drifting apart.
- Each logged change makes the client refetch the year (cache invalidation after mutations). That's a cheap PK range read, with no server cache or ETag to keep consistent.
- The Mini App can't show stats offline or recompute locally after an optimistic edit: the heatmap updates when the refetch lands (~tens of ms warm).
- No new dependency. The stats chunk is a few KB instead of ECharts' several hundred KB, and the initial bundle stays at ~111 KB.
## Alternatives considered
- **Compute in the Mini App from `/me/days`** (max 371 days per request): no new endpoint, but a 2-year window for runs needs 2 requests and ~30–60 KB of day JSON. The rules would also live in TypeScript, duplicated again for the bot and the teacher view, with privacy projection left to each client.
- **ECharts calendar heatmap (lazy chunk):** tooltips and zoom for free, but a heavy download for one static grid, theming that would have to fight the Telegram theme variables, and accessibility that is harder to control than with plain `<rect>` + `aria-label`.
- **Materialised stats table** updated on each log: faster reads at scale, but a cache to keep in sync with edits, backfill and deletions. Not needed at hobby scale (≤ 731 rows per request).
