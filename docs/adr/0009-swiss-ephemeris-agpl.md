# ADR-0009: Accept AGPL-3.0 for Swiss Ephemeris (pyswisseph)
- Status: accepted · Date: 2026-10-18
## Context
ADR-0006 ports the verified moon-day generator 1:1, and that generator uses Swiss Ephemeris via `pyswisseph`. Both are dual-licensed: AGPL-3.0 or a paid Swiss Ephemeris professional licence. For a network service, AGPL generally requires offering the corresponding source to its users. (Not legal advice.)
## Decision
Use `pyswisseph` under **AGPL-3.0** in the backend and publish the backend source under AGPL-3.0 (before or at the public launch). `swisseph` is imported only in `tristhana.moon` (enforced by import-linter), so the dependency stays isolated if this decision changes.
## Consequences
1:1 parity with the verified generator, and moon days can be computed for any user location at runtime. The repository (at least `backend/`) must carry an AGPL-3.0 licence and be publicly reachable once the service is offered to users.
pyswisseph 2.10.3.2 ships only a source distribution, so `uv sync` compiles C code: CI and the container build need a C compiler (build in a builder stage and copy the venv into a slim runtime image).
## Alternatives considered
- Offline generator in `tools/` shipping only generated data: licence-free backend, but a fixed city list.
- Professional licence: clean, costs money.
- Skyfield + JPL ephemeris (MIT): sunrise/delta-T definitions differ, so dates near boundaries may flip vs the verified generator; contradicts ADR-0006.
