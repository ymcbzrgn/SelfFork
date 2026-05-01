# selffork-body

**Status:** Skeleton — implementation lands in **M5 (Body Daemon)** per `docs/ROADMAP.md`.

This package exists from day 1 to lock the SelfFork monorepo shape (per [ADR-001 §4 and §14.9](../../docs/decisions/ADR-001_MVP_v0.md)).

## Sub-packages (planned)

| Sub-package | Purpose | Reference repo |
|---|---|---|
| `vision/` | Gemma 4 vision: screenshot → decision → action | — |
| `drivers/android/` | docker-android + ADB wrapper | prior art in the agentic-CLI orchestration space |
| `drivers/ios/` | appium-mcp + mobile-mcp wrapper | prior art in the agentic-CLI orchestration space, prior art in the agentic-CLI orchestration space |
| `drivers/web/` | browser-use / skyvern / stagehand wrapper | prior art in the agentic-CLI orchestration space, prior art in the agentic-CLI orchestration space, prior art in the agentic-CLI orchestration space |
| `drivers/desktop/` | Electron + llama.cpp shell (clippy ref) | prior art in the agentic-CLI orchestration space |
| `sandbox/` | Action-level permission warden, audit, kill-switch | — |

> **NB:** This package's `sandbox/` is **action-level** (per-tool-call permission gating). The orchestrator-level sandbox (env isolation) lives in `packages/orchestrator/sandbox/`. Different concerns; no shared interface.
