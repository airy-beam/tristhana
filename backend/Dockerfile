# syntax=docker/dockerfile:1
# Build context: the repository root (needs data/seed). See docs/specs/NF-02-cloud-run-deploy.md.

# --- builder: has a C compiler (pyswisseph ships only an sdist, ADR-0009) ---
FROM python:3.13-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /src/backend
# Dependencies first: this layer is cached until uv.lock changes.
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY backend/src ./src
# Babel (via fluent.runtime) ships CLDR data for ~1,000 locales (~32 MB); keep root and our UI
# locales only. Adding a language? Add it here; the container smoke test checks every LOCALES entry.
RUN uv sync --locked --no-dev --no-editable \
    && find /app/.venv/lib/python3.13/site-packages/babel/locale-data -name '*.dat' \
      ! -name root.dat ! -name 'en.dat' ! -name 'en_*.dat' ! -name 'ru.dat' ! -name 'ru_*.dat' \
      -delete

# --- runtime: slim, no compiler, no uv, non-root ---
FROM python:3.13-slim-bookworm
# The slim image ships the stdlib without .pyc files and the app user can't write them,
# so precompile it here; otherwise every cold start recompiles it (~0.5 s).
# Skip what the app never imports (pip, IDLE, Tk, ensurepip, docs data): ~10 MB of .pyc.
RUN python -m compileall -q -j 0 \
      -x '/(site-packages/pip|idlelib|tkinter|turtledemo|ensurepip|pydoc_data)/' \
      /usr/local/lib/python3.13 \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY data/seed /app/data/seed
# Supabase's CA for TLS verify-full (DATABASE_CA_FILE, ADR-0014); public, not a secret.
COPY infra/supabase/certs /app/certs
# Declared late: an ARG invalidates the cache of every RUN after it.
ARG GIT_SHA=dev
# PYTHONTZPATH empty: zoneinfo uses the pinned `tzdata` package, not the base image's files,
# so the moon calendars' ALGO_VERSION (which names the tzdata version) matches the data used.
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONTZPATH="" \
    PYTHONUNBUFFERED=1 \
    APP_ENV=prod \
    SEED_DIR=/app/data/seed \
    GIT_SHA=$GIT_SHA
USER 10001
EXPOSE 8080
CMD ["tristhana-serve"]
