# apps/

User-facing surfaces for SelfFork.

**Status:** Empty until **M4 (Cockpit Full Control)** per `docs/ROADMAP.md`.

The cockpit is the web/mobile/desktop UI. SelfFork is **backend-first** (per [`ADR-001 §1.2`](../docs/decisions/ADR-001_MVP_v0.md)): no UI ships until the orchestrator core and pillar contracts are stable.

## Planned (M4)

- `apps/web/` — web cockpit (TS/React)
- `apps/mobile/` — companion app
- `apps/desktop/` — desktop shell (`examples_crucial/clippy/` reference)
- `apps/server/` — rented GPU server runtime

## Today

All `selffork` interaction is via the CLI: `packages/orchestrator/src/selffork_orchestrator/cli.py`.
