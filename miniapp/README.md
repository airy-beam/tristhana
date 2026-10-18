# Tristhana Mini App

React + TypeScript + Vite Telegram Mini App. Spec: `docs/specs/UI-03-miniapp-skeleton.md`, ADR-0013.

```bash
npm ci
npm run dev            # http://localhost:5173 with a mocked Telegram (?lang=ru, ?theme=dark)
npm test               # Vitest
npm run lint && npm run typecheck
npm run build && npm run check:bundle   # initial JS <= 150 KB gzip (NF-09)
npm run gen:api        # regenerate src/api/schema.d.ts from src/api/openapi.json
```

- `/api` is proxied to the local backend in dev: `cd backend && uv run tristhana-dev`.
- The API contract comes from the backend: `cd backend && uv run tristhana-openapi` writes
  `src/api/openapi.json`; then `npm run gen:api`. CI fails if either is stale.
- All UI text lives in `src/locales/{en,ru}/app.ftl` (no literals in JSX: ESLint enforces it).
- Only `src/telegram/` talks to the Telegram SDK.
