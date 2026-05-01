# Dashboard UI screenshots

Captured during the SelfFork dashboard build-out. Three iterations land
in this folder; each subdirectory is a snapshot of the UI at a specific
moment so we can review the design progression without relying on git
diffs.

All screenshots are taken against **real on-disk artifacts** — every
session, paused record, audit event, project, and kanban card visible in
these images came from actual files under `~/.selffork/`. Per
`project_ui_stack.md`, the dashboard never renders mock data.

## ui-v1-initial/

First pass after the FastAPI backend went live. Single-column layout,
basic shadcn/ui primitives, no design system yet. Captured 2026-05-01.

| File | What it shows |
|---|---|
| `dashboard.png` | Paused sessions card + recent sessions list (flat layout, no KPI strip) |
| `session-detail.png` | Plan + workspace + raw audit stream, no filters |
| `run-page.png` | Bare PRD-path / config-path form |

## ui-v2-polished/

Conventional SaaS shell: sidebar + topbar + KPI strip + sortable
sessions table + audit-stream filter pills + autoscroll. Status colours
unified through a shared `StatusBadge` token. Sidebar gained a
collapsible mode (icon-only / full) with localStorage persistence.

| File | What it shows |
|---|---|
| `dashboard.png` | KPI strip (Paused / Sessions / Completed / Last event) + paused card + sortable recent-sessions table |
| `session-detail.png` | Plan + workspace + filter-pill audit stream with live status badge |
| `run-page.png` | Form with iconlu fields, hint copy, footer warning + Start button |
| `sidebar-expanded.png` | Full sidebar with primary nav (Dashboard / Paused / Sessions / New run / Audit log) |
| `sidebar-collapsed.png` | Same dashboard with the sidebar collapsed to icon-only mode |
| `sidebar-expanded-after-toggle.png` | Re-expanded sidebar after toggling — proves the localStorage persistence works |

## ui-v3-projects/

Full-vision UI: Project as first-class concept, kanban board per project,
provider-usage strip, dynamic projects list in the sidebar. Backed by
new endpoints under `/api/projects/*` and `/api/usage/providers`.

| File | What it shows |
|---|---|
| `projects-list.png` | `/projects/` index — one card per project, kanban counts, "+ New project" button |
| `project-detail-initial.png` | `/project/?slug=calc` — header, provider-usage strip, 4-column kanban with two cards in Backlog |
| `project-detail-after-card-moved-to-done.png` | Same project after a `kanban_card_move` (the same operation Jr's `<selffork-tool-call>` block triggers) — one card in Backlog, one in Done |

## How these were captured

`selffork ui --no-open` boots the FastAPI backend serving the static
Next.js bundle from `apps/web/out/`. A Playwright session navigates to
each route and screenshots the viewport (or the full page when the
content overflows). The runtime screenshots written by Playwright land
in `.playwright-mcp/` (gitignored); only the curated images here get
committed.
