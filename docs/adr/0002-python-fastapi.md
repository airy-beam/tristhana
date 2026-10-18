# ADR-0002: Python 3.13 + FastAPI backend, React + TS Mini App
- Status: accepted · Date: 2026-10-18
## Context
The moon-day reference algorithm uses pyswisseph (Python), and the prior bots are Python. We need an API for several clients.
## Decision
FastAPI + Pydantic v2 + SQLAlchemy 2 (async, asyncpg) + Alembic, managed with `uv`. Mini App in React + TypeScript + Vite, with the client generated from OpenAPI.
## Alternatives
TypeScript end-to-end (grammY): shared types, but the swisseph port would need re-verification.
