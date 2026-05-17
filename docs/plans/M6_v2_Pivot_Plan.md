# M6 — SelfFork v3 Pivot Implementation Plan

> **Status:** Active.
> **Reference ADR:** [`docs/decisions/ADR-006_v2_Pivot.md`](../decisions/ADR-006_v2_Pivot.md).
> **Started:** 2026-05-17.

This document is the executable counterpart to ADR-006 §9. It tracks
sub-phases, what landed in each, and the smoke-test gates that flip a
phase from "in flight" to "shipped".

## Phase map

| Phase | Scope | Status |
|---|---|---|
| **M6.0 Foundation** | DESIGN.md v3, Stitch v3 export, ADR-006 cross-reference banners | ✅ Done |
| **M6.1 Server deploy iskelesi** | `infra/deploy/{Dockerfile,docker-compose,README}` | ✅ Done |
| **M6.2 Speaker-only refactor** | Reflex Watcher reference cleanup (no code existed; doc-only) | ✅ Done (no-op) |
| **M6.3 Destructive whitelist + soft-confirm** | Body sandbox YAML + matcher + PendingConfirmationStore + pending_router + UI banner wire | ✅ Done |
| **M6.4 UI v3** | apps/web 5 sayfa (Dashboard / Workspace 4-tab / Talk / Connections / Settings) + sidebar/topbar v3 + 12 new components | ✅ Done |
| **M6.5 Live Run Theater backend** | theater_router scaffold + WS protocol + Dashboard wire + Workspace wire. **Event producer (snappers + Body vision + Speaker reasoning) → sub-task** | 🟡 MV done, producer pending |
| **M6.6 Fine-tune UI + Telegram surface** | reflex_router stub + telegram_router status/setup + Connections wire | ✅ MV done |
| **M6.7 Smoke + close-out** | `M6_Smoke_Checklist.md`, memory entries, ADR-007 prep | 🟢 In flight |

## Deferred (M6.5+ sub-tasks)

These wires complete the v3 picture but aren't blocking for the M6
close-out. They land as discrete commits with their own smoke gates:

- **Theater event producer** — snappers → CLI output envelope; Body
  vision → screenshot envelope; Speaker `<thought_summary>` parser →
  thought envelope. Without this the Live Run tab is permanently in
  idle state.
- **Active loop endpoint producer** — derive `/api/loop/active` from
  the tmux session registry + most-recent audit ts. Currently always
  returns `None`.
- **Warden integration** — hook `DestructiveWhitelist.match` into the
  CLI subprocess action interception path. Without this, destructive
  actions still execute; the whitelist + store are dormant.
- **Telegram outbound** — instantiate `PtbTelegramBridge` on startup
  when `TELEGRAM_BOT_TOKEN` is set, and call `bridge.notify()` from
  the warden hook when a pending confirmation is created. Without
  this, the Telegram message in the soft-confirm flow never sends.
- **Telegram inbound** — Sr → Jr messages from the `TelegramInbox`
  table need a worker that routes them to the active workspace's
  Talk channel and/or pending-confirmation approve callback.
- **Adapter manifest reader** — `/api/reflex/adapter` currently
  returns hardcoded placeholder. Read from
  `~/.selffork/reflex/adapters/<current>/manifest.json` once the M7
  Reflex worker starts writing those.

## Test posture

Every sub-task lands with at least:
- 1 happy-path test (the thing works).
- 1 failure-path test (404 / unknown id / disabled flag).
- A line in `M6_Smoke_Checklist.md` if the failure surface reaches
  the operator UI.

Python tests live in `packages/{orchestrator,body}/tests/`; UI
typecheck enforces frontend correctness (`pnpm exec tsc --noEmit`).
End-to-end smoke is the checklist below.
