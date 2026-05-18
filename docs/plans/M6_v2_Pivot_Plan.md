# M6 — SelfFork v3 Pivot Implementation Plan

> **Status:** Active.
> **Reference ADR:** [`docs/decisions/ADR-006_v2_Pivot.md`](../decisions/ADR-006_v2_Pivot.md).
> **Started:** 2026-05-17.

This document is the executable counterpart to ADR-006 §9. It tracks
sub-phases, what landed in each, and the smoke-test gates that flip a
phase from "in flight" to "shipped".

## Wave structure

M6 runs in **two waves**. Wave 1 (MV scaffold) is DONE. Wave 2 (wiring
completion) is sequenced by **[`ADR-007_v3_Wiring_Completion.md`](../decisions/ADR-007_v3_Wiring_Completion.md)**
into 6 backend-first sprints (S1–S6).

### Wave 1 — MV Scaffold (DONE, commit `8d509d5`)

| Phase | Scope | Status |
|---|---|---|
| **M6.0 Foundation** | DESIGN.md v3, Stitch v3 export, ADR-006 cross-reference banners | ✅ Done |
| **M6.1 Server deploy iskelesi** | `infra/deploy/{Dockerfile,docker-compose,README}` | ✅ Done |
| **M6.2 Speaker-only refactor** | Reflex Watcher reference cleanup (no code existed; doc-only) | ✅ Done (no-op) |
| **M6.3 Destructive whitelist + soft-confirm** | Body sandbox YAML + matcher + PendingConfirmationStore + pending_router + UI banner wire | ✅ Done (scaffold) |
| **M6.4 UI v3** | apps/web 5 sayfa + sidebar/topbar v3 + 12 new components | ✅ Done |
| **M6.5 Live Run Theater backend** | theater_router scaffold + WS protocol + frontend wire | ✅ Done (scaffold) |
| **M6.6 Fine-tune UI + Telegram surface** | reflex_router + telegram_router + Connections wire | ✅ Done (scaffold) |
| **M6.7 Smoke + close-out** | M6_Smoke_Checklist, memory entries, ADR-007 | ✅ Done |

> **Wave 1 verdict:** scaffold complete but a 2026-05-17 wiring audit
> (audit-god) found **30+ UI elements stub/dead/hardcoded**, 9 with
> endpoints-but-no-producer, only 13 truly live. Wave 1 is a vitrine,
> not a working product. Wave 2 fixes this.

### Wave 2 — Wiring Completion (S1–S8, ADR-007)

> 2026-05-18: plan 6→8 sprint'e genişletildi. Vizyon-izlenebilirlik
> denetimi 6-sprint taslağının 2 kilitli ADR-006 kararını (CLI router,
> Telegram inbound) sprint dışı bıraktığını buldu. Düzeltme: S6 = CLI
> Router (yeni), Telegram inbound S3'e katıldı, eski devasa S6 → S7+S8.

| Sprint | Scope | Status |
|---|---|---|
| **S1 Talk Loop** | `talk_router` + Self Jr session resolver + Talk page real wire | ⬜ Next |
| **S2 Live Run Theater** | theater event producer (snapper/vision/speaker) + `/api/loop/active` derive | ⬜ |
| **S3 Destructive Warden + Telegram** | warden hook → `whitelist.match` → `store.request()` + Telegram outbound **ve** inbound (Sr→Jr) | ⬜ |
| **S4 Settings Persistence** | settings endpoints GET/PUT + form wire + kill hardcoded mock data | ⬜ |
| **S5 Connections Actions** | provider sign-in flow + Telegram setup + button handlers | ⬜ |
| **S6 CLI Router** | `select_cli` (quota + RAG affinity + operator override) + auto-switch | ⬜ |
| **S7 Workspace Actions** | kanban add/drag/filter + Notes GET/PUT + header/theater buttons | ⬜ |
| **S8 Dashboard Activity + Final Cleanup** | `/api/activity` endpoint + topbar/sidebar + son dead-button taraması | ⬜ |

Each sprint is backend-first, ends end-to-end (not scaffold), passes its
own smoke gate. Full sprint detail (backend/frontend line items,
dependencies, gates) in **ADR-007 §4**. M6 closes only when all S1–S8
gates PASS — then M7 (Reflex LAST MILE) opens.

## Test posture

Every sub-task lands with at least:
- 1 happy-path test (the thing works).
- 1 failure-path test (404 / unknown id / disabled flag).
- A line in `M6_Smoke_Checklist.md` if the failure surface reaches
  the operator UI.

Python tests live in `packages/{orchestrator,body}/tests/`; UI
typecheck enforces frontend correctness (`pnpm exec tsc --noEmit`).
End-to-end smoke is the checklist below.
