# SelfFork — Roadmap

> **Codename:** Yamaç Jr. Nano
> **Hardware target (v1):** 16 GB Apple Silicon MacBook Pro (operator's existing machine)
> **Default AI:** Gemma 4 E2B-it Q4_0 — *no fine-tune until M7*
> **License:** Apache 2.0
> **Owner:** Yamaç Bezirgan (arketic.tools@gmail.com)
> **Date:** 2026-04-27
> **Companion docs:** [`PRD.md`](./PRD.md) · [`Yamac_Jr_Nano_Kararlar.md`](./Yamac_Jr_Nano_Kararlar.md) · [`decisions/`](./decisions/)

---

## 0. Roadmap at a Glance

```
NOW                                                                          NANO v1.0
 │                                                                              │
 │   ┌──────┐  ┌──────┐  ┌──────┐    ┌────────────┐  ┌──────┐  ┌──────┐  ┌─────────────┐
 │   │ M-1  │  │  M0  │  │  M1  │    │  M3 + M4   │  │  M5  │  │  M6  │  │ M7 (Reflex) │
 │   │ Prep │─>│ Found├─>│ Spkr ├─┬─>│   (par.)   │─>│ Body │─>│ Polsh├─>│ Last mile   │─> v1.0
 │   └──────┘  └──────┘  └──────┘ │  │ Surf  Cock │  └──────┘  └──────┘  └─────────────┘
 │                                │  │  M3    M4  │
 │                                │  └────────────┘
 │                                │
 │                                └────> M2 (Mind)  ────────────────> [used by all later]
 │
 │
 │   PASSIVE DATA COLLECTION ─────────────────────────────────────────────────────>
 │   (starts M0, runs every working day until M7 ingests it)
 │
 │
 NANO v1.0 ──> M8 (Autonomous, sub-PRD) ──> v2.0 (Full Vision) ──> v3.0+ (Community)
```

**Critical path:** M-1 → M0 → M1 → M2 → (M3 ∥ M4) → M5 → M6 → M7
**Calendar estimate:** 8–12 months single-developer pace, including the Reflex training cycle.
**Earliest M7 ship:** ~2027-01.

---

## 1. Guiding Philosophy

These principles override speed.

### 1.1 Fine-tune is the LAST mile.
Stock Gemma 4 E2B-it must carry the system through M0–M6. The operator commutes to work every day; data collection is passive and continuous; by M7 we have the volume and the system maturity to deserve a custom adapter. Training too early wastes good data and produces a half-shaped reflex.

### 1.2 Each milestone is a complete, demoable slice.
No half-implementations. No "we'll wire that up later." Exit criteria are concrete and testable. A milestone that fails its exit criteria does not advance — it iterates.

### 1.3 Surgical scope per milestone.
A milestone owns its scope. M3 work does not bleed into M2; M5 work does not start in M3. If a discovered need belongs to a future milestone, it goes into the backlog of *that* milestone, not the current one.

### 1.4 Parallelize where independence is real.
M3 (CLI Surfing) and M4 (Cockpit Full Control) are independent and run in parallel after M2. Forced parallelism elsewhere (e.g., M2 + M3) creates integration debt; sequential discipline pays off.

### 1.5 Quality before speed.
A milestone that ships at "70% of exit criteria" is not done. It iterates. Calendar slippage is acceptable; quality slippage is not.

### 1.6 Decision discipline.
Every locked decision lands in the SSOT (`docs/Yamac_Jr_Nano_Kararlar.md` or `docs/decisions/`) within 24 hours. This roadmap may not contradict the SSOT; if the roadmap and SSOT diverge, the SSOT wins and the roadmap is updated.

### 1.7 Korpus reflex per milestone.
Before a milestone's architectural work begins, the operator (or an agent on their behalf) consults at least one `examples_crucial/` rival in the relevant pillar. Findings are recorded in `docs/research/M{n}_korpus.md`.

---

## 2. Milestones

Each milestone section below contains:

- **Goal** — the one-sentence north star.
- **Scope** — concrete sub-tasks, by package.
- **Deliverables** — outputs (code, docs, demo videos).
- **Exit Criteria** — testable conditions that must hold before advancing.
- **Documentation Outputs** — docs that must land before the milestone is done.
- **Test Coverage Targets** — concrete coverage thresholds.
- **Performance Benchmarks** — SLOs that must be met.
- **Open Questions Resolved Here** — references back to PRD §27.
- **Risks & Mitigations** — threats to this milestone.
- **Dependencies** — prior milestones that must be complete.
- **Demo** — what success looks like to a viewer.
- **Bouncing Back Path** — what to do if this milestone slips.

---

### M-1 — Pre-Foundation Preparation (3–5 days)

**Goal:** Have the operator's existing tooling, accounts, and data sources ready *before* writing any product code.

**Scope:**
- Verify Tailscale ACLs across home macOS, work Windows, work Ubuntu.
- Confirm operator has active subscriptions: Claude Code, OpenCode (with Minimax/GLM/GPT-4o-mini), Gemini Pro.
- Confirm operator has Telegram account and create the dedicated bot (decision §27.7).
- Inventory operator's existing session data:
  ```bash
  ls -lah ~/.claude/projects/
  du -sh ~/.claude/projects/
  find ~/.claude/projects/ -name "*.jsonl" | wc -l
  ```
- Sketch the `~/yamac-jr-data/` directory tree and confirm there's space (~50 GB free recommended).
- Set up Akakçe price alerts for Mac Studio M2/M3 Ultra (per Donanım PDF).
- Create initial Apache 2.0 LICENSE file at repo root if not yet present.
- Resolve Open Question §27.4 (decision SSOT structure: one-file vs split). **Recommended: split into `docs/decisions/<topic>.md` going forward, with `Yamac_Jr_Nano_Kararlar.md` as historical document.**

**Deliverables:**
- Tailscale verified, ACLs documented.
- Telegram bot created, token saved in macOS Keychain.
- Session data inventory committed to `docs/research/M-1_data_inventory.md`.
- Decision SSOT structure decided and documented.

**Exit Criteria:**
- Operator can `ssh` between all three machines via Tailscale without password prompt.
- Telegram bot responds to a manual `curl` test.
- Session data inventory shows ≥ 100 sessions, ≥ 10K turns (existing baseline).
- LICENSE in place at `LICENSE`.

**Documentation Outputs:**
- `docs/research/M-1_data_inventory.md`
- `docs/decisions/2026-04-XX_decision_ssot_structure.md` (resolves §27.4)

**Risks:**
- Tailscale config drift on Windows. Mitigation: re-run installer.
- Operator's `~/.claude/projects/` may be in a non-standard location. Mitigation: locate via `find ~ -name "*.jsonl" 2>/dev/null` and document.

**Bouncing Back Path:**
M-1 should not slip more than 1 week. If Tailscale or Telegram blockers appear, document them as separate decision items and proceed without those two pieces (they can be wired in M0 instead).

---

### M0 — Foundation (1–2 weeks)

**Goal:** Repo skeleton, decision SSOT discipline live, passive data collection running, mock cockpit verified.

**Scope:**

- Create directory structure per PRD §6.1:
  ```
  packages/{reflex,body,mind,orchestrator,shared}/
  apps/{web,server,mobile,desktop}/    # only web populated initially
  infra/{docker,deploy,scripts}/
  tests/{reflex,body,mind,orchestrator,e2e}/
  benchmarks/yamac_session_holdouts/
  docs/{decisions,architecture,research,retros}/
  ```
- Monorepo workspace config:
  - `pyproject.toml` for Python packages (uv or poetry).
  - Root `package.json` for TS/JS workspaces.
- CI:
  - `.github/workflows/ci.yml` runs lint + type-check + minimal tests on every PR.
  - Branch protection: PRs require passing CI + 1 review (from operator).
- Decision SSOT migration:
  - Decision in M-1 (one-file vs split): execute the migration.
- **Passive data collection cron** on home Mac:
  ```bash
  # /etc/cron.d/selffork-data-snapshot
  0 3 * * 0 yamac /usr/local/bin/selffork-snapshot
  ```
  ```bash
  # /usr/local/bin/selffork-snapshot
  #!/usr/bin/env bash
  set -euo pipefail
  STAMP=$(date +%Y%m%d)
  cp -R "$HOME/.claude/projects" "$HOME/yamac-jr-data/raw/claude-code/projects-$STAMP"
  ```
  Document OpenCode / ChatGPT / Claude.ai manual export procedures.
- Verify the existing `apps/web` mock cockpit still runs (`npm run dev` in `apps/web/`).
- Establish `examples_crucial/` and `examples/` as **read-only reference**, NOT in workspace `package.json`.
- Initial `packages/shared/` skeleton with envelope types stubbed.
- Initial `.editorconfig`, `.prettierrc`, `ruff.toml`, type-check configs.
- Initial cross-pillar lint rules (`packages/shared/eslint-rules/no-cross-pillar.js`).
- Initial telemetry stub (events go to console; OTLP optional).

**Deliverables:**
- `packages/`, `apps/`, `infra/`, `tests/`, `benchmarks/`, `docs/` skeleton committed.
- `.github/workflows/ci.yml` running on PRs.
- `~/yamac-jr-data/raw/` populated with first weekly snapshot of Claude Code sessions.
- `docs/decisions/` reconciled with `Yamac_Jr_Nano_Kararlar.md`.
- `apps/web` confirmed runnable, no regressions.
- `docs/architecture/diagram.md` with the PRD §7.1 ASCII diagram and pillar boundary discipline.
- `docs/operations/install.md` outlining how to set up SelfFork from scratch.

**Exit Criteria:**
- CI passes on `main`.
- First weekly data snapshot exists and contains ≥ 10K turns.
- All decisions made during PRD drafting (Watcher cancellation, hybrid pillars, CLI Surfing v1, Cockpit full-control v1, M0–M7 with fine-tune last) are entries in the decision SSOT.
- A new contributor can clone, run `bin/setup`, and have `apps/web` running locally with passing CI in < 30 minutes.

**Documentation Outputs:**
- `docs/decisions/2026-04-XX_watcher_cancelled.md`
- `docs/decisions/2026-04-XX_hybrid_pillar_naming.md`
- `docs/decisions/2026-04-XX_cli_surfing_v1_core.md`
- `docs/decisions/2026-04-XX_cockpit_full_control_v1.md`
- `docs/decisions/2026-04-XX_capability_roadmap_finetune_last.md`
- `docs/decisions/2026-04-XX_passive_data_collection_at_m0.md`
- `docs/architecture/diagram.md`
- `docs/architecture/cross-pillar-boundaries.md`
- `docs/operations/install.md`
- `docs/operations/data-collection.md`

**Test Coverage Targets:**
- N/A (no product logic yet); CI proves lint + type-check pipelines work.

**Performance Benchmarks:**
- N/A.

**Open Questions Resolved:**
- §27.4 (Decision SSOT structure)
- §27.9 (Off-site backup strategy)
- §27.13 (Operator preference persistence)

**Risks:**
- Decision SSOT structure churn after migration. Mitigation: pick on day 1, accept, move on.
- CI tooling churn (Vite 8, TS 6 are bleeding edge). Mitigation: lock versions in lockfile.
- Cron not reliable on macOS (deprecated). Mitigation: use `launchd` plist instead; document both.

**Dependencies:** M-1 complete.

**Demo:**
- Operator pulls fresh from `main`, runs `bin/setup`, sees `apps/web` cockpit at `http://localhost:5173/` with mock data.
- `~/yamac-jr-data/raw/claude-code/projects-{today}/` exists with their session JSONLs.

**Bouncing Back Path:**
If M0 slips beyond 3 weeks, the decision SSOT migration likely got ambitious. Cut to: pick a structure, do not migrate historical content yet, just adopt the new structure for new entries. Resume M1.

---

### M1 — Speaker Stub (3–4 weeks)

**Goal:** Stock Gemma 4 E2B-it Q4_0 speaks back through one CLI bridge end-to-end.

**Scope:**

- `packages/reflex/speaker/`:
  - MLX runtime integration (`mlx-lm`).
  - YAML config loader (`config.yaml` per PRD §9.1).
  - Speaker server (FastAPI): exposes `/generate` endpoint with streaming.
  - **No adapter loaded; stock weights only.**
  - Health probe (`/health` returns RAM, KV pressure, model id).
  - Hot-swap stub (no-op for v1, but the API is in place for M7).
- `packages/orchestrator/cli-surfer/adapters/claude-code/`:
  - tmux pane spawn / send-keys / capture-output.
  - Translate Speaker output → Claude Code prompt format.
  - Parse Claude Code output → typed `CLIResponse` envelope.
  - Quota signal parser (placeholder; full logic in M3).
- `packages/orchestrator/tmux/`:
  - Session/pane lifecycle helpers.
  - State persistence to SQLite every 30 s.
  - Restart resume from last persisted state.
- `packages/shared/envelopes/`:
  - `ChatPrompt`, `Token`, `CLIPrompt`, `CLIResponse`, `WorkspaceState` types.
- Cockpit Chat tab wired to live Speaker:
  - WebSocket client → orchestrator → Speaker `/generate`.
  - Render streaming tokens.
- Cockpit Mission tab "+ Task" button → Speaker drafts task description → orchestrator inserts into Mission backlog.
- Cockpit Run tab terminal stream live-mirroring tmux pane.

**Deliverables:**
- `mlx-lm` loads `mlx-community/gemma-4-e2b-it-4bit` and responds to a `curl` request.
- Cockpit Chat tab sends operator message → Speaker generates → message renders in chat stream.
- Claude Code bridge spawns a tmux pane and forwards Speaker prompts.
- End-to-end: operator types "Build a hello world Express server" in Chat → Speaker drafts task → operator confirms in Mission → Speaker writes prompt → Claude Code lane executes → result shown in Run tab terminal.
- `docs/architecture/sequence-cockpit-to-speaker.md` capturing the M1 flow.
- `docs/operations/run-locally.md` end-to-end run guide.
- M1 demo video (3 minutes, recorded by operator).

**Exit Criteria:**
- Operator types "Ben kimim?" in cockpit Chat → Speaker responds with a Yamaç Jr. self-introduction (stock model, no adapter — quality will be weak; that's expected).
- Operator triggers "+ Task" on Mission tab → Speaker drafts a task description → it appears in the Backlog column.
- End-to-end Claude Code flow: Speaker drafts a prompt → Claude Code bridge sends it → Claude Code's response is captured and shown in Run tab terminal.
- Cockpit Chat reply latency: p95 < 3 s cold, < 1.5 s warm.
- No mock data in Chat or Mission tabs (Run + Context still mocked at M1).

**Documentation Outputs:**
- `docs/architecture/sequence-cockpit-to-speaker.md`
- `docs/architecture/cli-bridge-protocol.md`
- `docs/operations/run-locally.md`
- `docs/research/M1_korpus.md` (Letta + Hexis read for Reflex framing)

**Test Coverage Targets:**
- `reflex/speaker/`: 80% line coverage.
- `orchestrator/cli-surfer/adapters/claude-code/`: 70%.
- `orchestrator/tmux/`: 60%.
- `shared/envelopes/`: 100% (type-checked).
- Integration: 1 e2e Playwright test covering the demo vignette.

**Performance Benchmarks:**
- Cockpit chat reply (cold): p95 < 3 s.
- Cockpit chat reply (warm): p95 < 1.5 s.
- Speaker startup: < 60 s on operator's MBP.

**Open Questions Resolved:**
- None new at M1 (M0 resolved 27.4, 27.9, 27.13).

**Risks:**
- E2B-it stock quality may feel weak for complex prompts. Mitigation: this is expected; M7 fixes it. Document the gap. Operator's evaluation is "is the system structurally working?", not "is the response brilliant?".
- MLX model loading on 16 GB MBP under cockpit + Vite dev server load. Mitigation: profile RAM at M1 close; if tight, suspend Vite during heavy generation.
- Streaming WebSocket disconnects on long generation. Mitigation: heartbeat pings every 5 s; client reconnect with state resync.

**Dependencies:** M0 complete.

**Demo:**
- Operator opens cockpit. Chat tab. Types "Hello." Speaker streams response.
- Operator asks "What model are you?" Speaker says "Gemma 4 E2B-it (no Yamaç adapter yet)."
- Operator goes to Mission tab. Clicks "+ Task". Types "Build a tiny ToDo API in FastAPI." Speaker drafts task. Operator clicks "Add". Task appears in Backlog.
- Operator drags task to In Progress. Speaker drafts the prompt. Claude Code lane in Run tab executes it. Output streams.

**Bouncing Back Path:**
If M1 slips beyond 6 weeks, suspect MLX integration or WebSocket protocol churn. Cut: ship Chat tab only (drop Mission + Run wiring to M2 if needed). Mission and Run tab go-live can move to M4. The blocker is "Speaker speaks back," not "all tabs are live."

---

### M2 — Mind (4–5 weeks)

**Goal:** The Speaker remembers across sessions through hybrid retrieval.

**Scope:**

- `packages/mind/memory/`:
  - SQLite schema per PRD §28.B.
  - sqlite-vec extension for dense vectors (1024-dim default).
  - FTS5 virtual tables for sparse keyword search.
  - Migration framework (Alembic-equivalent for SQLite).
- `packages/mind/rag/`:
  - Hybrid search: dense + BM25 + metadata filter.
  - Reranker: Jina Reranker API + bge-reranker-v2-m3 fallback (auto-failover on API issue).
  - Query rewriting: Speaker rewrites operator query into structured search plan.
  - Router: time-bounded → SQL filter; semantic → hybrid; aggregation → SQL aggregation.
- `packages/reflex/data/normalize/`:
  - Convert raw `~/yamac-jr-data/raw/` snapshots into the normalized schema (PRD §8.1.2).
  - First ingest of accumulated session data into Memory store.
  - Idempotent: re-running on the same snapshot does not duplicate rows.
- `packages/mind/historian/`:
  - Decision recall surface: query → matching decisions from `docs/decisions/`.
  - Indexes `docs/decisions/*.md` and `Yamac_Jr_Nano_Kararlar.md` into a `decisions` table.
  - Citation service: surfaces `path:line` for cited claims.
- `packages/mind/compaction/`:
  - Summarizer: nightly cron uses Speaker to summarize each session.
  - Compressor: turns are compressed by removing tool noise.
- Cockpit Context tab live (no mock):
  - Real source list from `documents` table.
  - Real chunks from `chunks` table.
  - Real active retrieval from query log.
  - Real pinned notes.
  - Upload tile triggers ingest.
- Embeddings cache (Jina API + local fallback).
- GitHub webhook receiver:
  - `infra/scripts/webhook-receiver.py` runs on home Mac (Tailscale-funnel optional).
  - Resolves Open Question §27.6.
- AST chunking for repo collection:
  - Tree-sitter or `ast-grep` for Python / TS / JS.

**Deliverables:**
- 100+ sessions normalized and indexed (whatever has accumulated since M0; expect ~3 months of data).
- Hybrid search returns ranked results from session collection.
- Speaker takes operator question → query rewrite → retrieval → answer with citations.
- Cockpit Context tab fully live; zero mock.
- Nightly compaction job running.
- GitHub webhook ingesting commits live.
- M2 demo video.

**Exit Criteria:**
- **Recall@3 ≥ 0.70** on a hand-built test set of 30 questions about the operator's prior work.
- Speaker answers "What did I decide about the Watcher last week?" with the correct decision and a `path:line` citation.
- Cockpit upload tile accepts a PDF/MD/TXT, chunks it, indexes it, and it appears in retrieval within 10 seconds.
- RAG retrieval latency: p95 < 500 ms.
- Decision recall: returns the right decision for 24/30 hand-built decision queries.

**Documentation Outputs:**
- `docs/architecture/mind-pillar-deep-dive.md`
- `docs/architecture/hybrid-search-design.md`
- `docs/operations/data-normalize-pipeline.md`
- `docs/research/M2_korpus.md` (mem0 + cognee + git-context-controller deep reads)

**Test Coverage Targets:**
- `mind/memory/`: 90%.
- `mind/rag/`: 85%.
- `mind/historian/`: 80%.
- `mind/compaction/`: 75%.
- `reflex/data/normalize/`: 85%.
- Integration: 1 e2e test covering ingest → query → response with citation.

**Performance Benchmarks:**
- RAG retrieval: p95 < 500 ms.
- Recall@3: ≥ 0.70 on test set.
- Normalization throughput: ≥ 1000 turns/sec on operator's MBP.
- Embedding cost (Jina API): documented per 10K turns.

**Open Questions Resolved:**
- §27.6 (GitHub webhook receiver hosting)

**Risks:**
- Hybrid search tuning takes longer than expected. Mitigation: ship dense-only first, add BM25 in iteration, reranker last. Each addition is measurable improvement.
- Jina API key cost / rate limit. Mitigation: BGE local fallback ships at the same time, auto-failover.
- AST chunking edge cases (unusual symbol patterns). Mitigation: fall back to token-window chunking when AST parse fails.
- SQLite + sqlite-vec performance at scale. Mitigation: benchmark at 100K turns, 1M turns; if too slow, plan for shard / migrate decision at M5.

**Dependencies:** M1 complete.

**Demo:**
- Operator asks "What did we decide about CLI Surfing being v1 core?" Speaker retrieves the decision, replies with the answer and a citation to `docs/decisions/2026-04-XX_cli_surfing_v1_core.md:14`.
- Operator uploads a new spec PDF in Context tab. Within 10 s, it appears in indexed sources. Operator asks a question that requires the new doc; Speaker uses it.
- Operator views a session ID in Run timeline; clicks; Context tab shows summary + raw turn stream from that session.

**Bouncing Back Path:**
If M2 slips beyond 8 weeks, suspect hybrid search tuning or AST chunking complexity. Cut: ship dense + BM25 only; defer reranker to M3 polish. Cut: ship session-collection only; defer GitHub repo collection to M5. The blocker is "Speaker remembers prior sessions," not "Speaker remembers prior code."

---

### M3 — CLI Surfing (4–5 weeks) — runs in parallel with M4

**Goal:** The orchestrator autonomously switches CLIs on boredom / 429 / rate limits.

**Scope:**

- `packages/orchestrator/cli-surfer/adapters/`:
  - `claude-code/` (already built in M1; harden quota signal parsing).
  - `opencode/` with sub-models: `minimax`, `glm`, `gpt-4o-mini`. Each has its own auth and quota tracking.
  - `gemini-cli/`.
- `packages/orchestrator/scheduler/`:
  - Quota state tracker per provider (parses 429 responses, parses provider-specific quota windows).
  - Boredom heuristic: 3 failures on the same task → kill pane.
  - Frustration tracker: log Ctrl-C events; do not auto-trigger switch on Ctrl-C.
  - Cron-sleep: when all healthy lanes exhausted, write Linux `cron` / macOS `launchd` job.
  - Cross-platform shim (`scheduler/cron_compat.py`).
- `packages/orchestrator/tmux/`:
  - Pane lifecycle robust against unexpected exits.
  - State persistence across orchestrator restarts.
- Telegram bot integration (`packages/orchestrator/deployer/telegram/`):
  - Sleep notification: "Limitler bitti, 3 saat sonra devam."
  - Wake notification: "Aktif lanes: opencode-minimax, gemini-pro."
  - Configured for Yamaç's chat ID only (no public commands).
  - Resolves Open Question §27.7.
- Mind-aware switching:
  - Carries last 5 turns + top-3 RAG hits into new lane's context.
- Antigravity decision (Open Question §27.5): bridge or data-source-only? Resolved at M3 entry.

**Deliverables:**
- Operator opens 3 lanes manually; orchestrator detects 429 on Gemini → kills pane → switches workspace to `opencode --model minimax` → run continues with same context.
- All-lanes-exhausted scenario: orchestrator writes cron, sends Telegram, exits cleanly.
- Wake from cron resumes from checkpoint.
- Telegram bot configured and tested.
- Antigravity decision documented.
- M3 demo video showing the quota crisis vignette (PRD §6.2).

**Exit Criteria:**
- **CLI switch on 429: p95 < 5 seconds wall-clock.**
- All-quotas-exhausted scenario: cron job is registered, Telegram message arrives, orchestrator process exits without panic. Cron fires at the scheduled time and resumes.
- Memory continuity: post-switch, the new CLI receives the active task context (last N turns + RAG retrieval). Speaker doesn't restart from zero.
- Sleep-wake cycle reliability: 99% (out of 100 simulated runs, ≤ 1 failure).
- All four adapters (Claude Code, OpenCode w/ 3 sub-models, Gemini CLI) parse 429 / quota signals correctly.

**Documentation Outputs:**
- `docs/architecture/cli-surfing-state-machine.md`
- `docs/operations/cli-bridge-add-new.md` (template for future contributors)
- `docs/decisions/2026-XX_antigravity_role.md` (resolves §27.5)
- `docs/decisions/2026-XX_telegram_bot_ownership.md` (resolves §27.7)
- `docs/research/M3_korpus.md` (browser-use + skyvern read)

**Test Coverage Targets:**
- `cli-surfer/adapters/`: 85% per adapter.
- `scheduler/`: 90%.
- `deployer/telegram/`: 80%.
- Integration: 3 e2e tests:
  - 429 → switch → resume.
  - All-exhausted → sleep → wake → resume.
  - Switch carries memory context correctly.

**Performance Benchmarks:**
- 429-detection-to-switch: p95 < 5 s.
- Sleep-write-to-Telegram-arrival: p95 < 10 s.
- Wake-from-cron-to-first-prompt: p95 < 30 s.

**Open Questions Resolved:**
- §27.5 (Antigravity)
- §27.7 (Telegram bot)

**Risks:**
- Each provider's 429 / quota signal is different. Mitigation: build adapters one at a time, ship Claude Code first, then OpenCode (which is itself multi-model), then Gemini.
- Cron portability across operator's machines. Mitigation: macOS uses `launchd`; document a cron→launchd shim.
- Telegram bot misuse / abuse. Mitigation: bot accepts commands only from operator's chat ID.
- OpenCode sub-model quotas may be hard to discriminate (one OpenCode account, multiple billing tiers). Mitigation: track per-model usage from response metadata.

**Dependencies:** M2 complete (orchestrator needs Mind for memory continuity).

**Demo:**
- Operator starts a long-running task. Mid-task, manually trigger 429 (mock or real). Cockpit shows engine switch in Run timeline. Task continues in new lane. Operator sees no interruption.
- Manually exhaust all four lanes. Telegram message arrives: "All lanes exhausted. Wake at HH:MM UTC." Mac fan goes silent. Time-skip; cron fires; resume; Telegram says "Resumed."

**Bouncing Back Path:**
If M3 slips, ship single-CLI (Claude Code only) with manual switch; defer OpenCode + Gemini bridges. The "v1 core" promise of CLI Surfing means *some* surfing must work; it can be less than four bridges initially. Document the partial state in `docs/decisions/2026-XX_cli_surfing_partial_v1.md`.

---

### M4 — Cockpit Full Control (4–5 weeks) — runs in parallel with M3

**Goal:** All cockpit interactive elements operate live against the orchestrator. Zero mock data.

**Scope:**

- `apps/web/` backend wiring:
  - WebSocket telemetry channel: orchestrator → cockpit.
  - REST mutation API: cockpit → orchestrator.
  - Auth: passphrase login (single-user; bcrypt-hashed in `~/.selffork/passphrase.hash`).
  - Resolves Open Question §27.10 (cockpit theme), §27.11 (multi-language), §27.13 (preference persistence).
- All four Workspace tabs go live:
  - **Mission:** Kanban board mutations (drag-drop creates/moves tickets via API).
  - **Run:** terminal stream from real tmux state; viewport replay (placeholder until Body drivers attach in M5).
  - **Chat:** already wired in M1; add chat queue → Speaker breakpoint inject.
  - **Context:** already wired in M2; add control elements (delete chunk, repin note, edit decision).
- Project lifecycle: Fleet Command "+ New Project" creates a new tmux session + workspace + RAG namespace.
- Fleet Command: live status from orchestrator (active / sleeping / shipping).
- Quota windows in Fleet Command: live data from scheduler.
- Recent events feed: live from telemetry stream.
- Slider control: cockpit adjusts; orchestrator enforces threshold table.
- Emergency kill-switch button (cockpit-wide).

**Deliverables:**
- Operator drags a Backlog ticket to In Progress → orchestrator picks it up → Speaker generates a prompt → CLI lane begins work → Run tab shows live terminal.
- Operator types in Chat during Speaker generation → message queued → folded into next breakpoint.
- All mock data removed from `apps/web/src/App.tsx`; the file fetches state from the orchestrator API.
- Slider visible per workspace, location-aware.
- Emergency kill-switch tested.
- M4 demo video.

**Exit Criteria:**
- **WebSocket lag: p95 < 500 ms** on a localhost loop test.
- Zero mock data in the Cockpit. All state comes from the orchestrator (verified via grep on App.tsx for hard-coded arrays).
- Cockpit survives a full session: 2 hours of orchestrator activity, no cockpit reload, state stays consistent.
- Auth works: cockpit refuses connection without local credential file.
- All four tabs interactive end-to-end.

**Documentation Outputs:**
- `docs/architecture/cockpit-orchestrator-protocol.md`
- `docs/operations/cockpit-auth.md`
- `docs/operations/cockpit-themes-and-locale.md`
- `docs/research/M4_korpus.md` (clippy + UI patterns)

**Test Coverage Targets:**
- Cockpit components (Vitest + Playwright): 85%.
- Orchestrator REST API: 90%.
- WebSocket protocol: 80% (state-machine focused).
- Integration: 5 Playwright e2e tests covering each tab's primary flows.

**Performance Benchmarks:**
- WebSocket lag: p95 < 500 ms.
- Mutation roundtrip: p95 < 800 ms.
- Cockpit cold-start (page load): < 2 s on 2026 MBP.
- Memory under 2-hour session: cockpit < 200 MB; orchestrator < 4 GB (excluding model).

**Open Questions Resolved:**
- §27.2 (cockpit auth — passphrase only confirmed for v1; JWT deferred to v2)
- §27.10 (cockpit theme — light only for v1; dark deferred)
- §27.11 (multi-language — UI English only for v1; cockpit will respect operator-language Speaker output)
- §27.13 (operator preference persistence — local file `~/.selffork/cockpit-state.json`)

**Risks:**
- React 19 + TS 6 + Vite 8 are bleeding-edge; library compat issues. Mitigation: lock versions, document workarounds.
- WebSocket reconnection logic. Mitigation: standard patterns (auto-reconnect with exponential backoff + state resync on reconnect).
- 4 tabs going live simultaneously is a lot of integration work. Mitigation: deliver tab-by-tab in sub-milestones M4.1 (Mission), M4.2 (Run), M4.3 (Chat queue), M4.4 (Context control).

**Dependencies:** M2 complete (Cockpit Context tab needs Mind live). Independent of M3 (Cockpit can run with single Claude Code lane during M3 development).

**Demo:**
- Operator opens fresh cockpit. Logs in with passphrase.
- Fleet Command: 0 projects. Click "+ New Project". Type "test-prd-deploy". Workspace appears.
- Mission tab: "+ Task" → "Build a hello world Express server with /health endpoint." Speaker drafts task. Operator drags to In Progress. Run tab opens, lane spawns, output streams.
- Mid-generation, operator types in Chat: "Also add /version endpoint." Folded at next breakpoint. Speaker incorporates.
- Operator slides slider from 7 to 3 mid-task. Next action prompts for approval.

**Bouncing Back Path:**
If M4 slips beyond 7 weeks, suspect 4-tab simultaneous delivery overload. Cut: ship Mission + Run + Chat live at v1.0; defer Context controls (delete chunk, repin) to v1.1. Context view remains live, just read-only.

---

### M5 — Body Daemon (3–4 weeks)

**Goal:** The brain on the home Mac extends into work machines via Tailscale.

**Scope:**

- `packages/body/daemon/`:
  - Cross-platform daemon (Go binary preferred, or Python+PyInstaller).
  - macOS / Windows / Ubuntu builds.
  - Reads local terminal/CLI state. Sends to home orchestrator.
  - Receives prompts from home orchestrator. Injects into local CLI.
  - Heartbeat + reconnect logic (exponential backoff).
- `packages/body/drivers/desktop/`:
  - Local Claude Code / OpenCode / Gemini CLI control via tmux on the daemon-host machine.
- Tailscale ACL: home Mac authorized to talk to work Windows + Ubuntu (validated in M-1; codified here).
- Cockpit Fleet view: machines listed with status (online / offline / latency).
- Location-aware slider:
  - Daemon reports its host machine identity.
  - Cockpit auto-shifts slider to home or work value when operator switches machines.
- Cockpit "Surfaces" view per workspace: which machines this workspace is using.
- GitHub repo ingestion (M2 deferral): if not done, ship here.

**Deliverables:**
- Daemon installer for each platform (Homebrew tap for macOS; .msi for Windows; .deb for Ubuntu).
- Operator at work Ubuntu opens cockpit on the home Mac, assigns a task → daemon on Ubuntu spawns the CLI lane → run unfolds on Ubuntu → cockpit shows it from home.
- Slider on home = 7, slider at work = 4. When the operator is on the work daemon, threshold checks use 4.
- M5 demo video.

**Exit Criteria:**
- **Daemon round-trip: p95 < 2 seconds** for prompt → execute → result over Tailscale.
- Daemon gracefully reconnects after network drop.
- Cross-machine: home Mac kicks off a task → work Ubuntu daemon executes it → operator returns home → result is in the cockpit.
- All three daemons (macOS, Windows, Ubuntu) install and run.
- Location-aware slider switches automatically.

**Documentation Outputs:**
- `docs/architecture/body-daemon-protocol.md`
- `docs/operations/install-daemon-macos.md`
- `docs/operations/install-daemon-windows.md`
- `docs/operations/install-daemon-ubuntu.md`
- `docs/research/M5_korpus.md` (mobile-use + skyvern revisit; understand vision driver gap)

**Test Coverage Targets:**
- `body/daemon/`: 80%.
- `body/drivers/desktop/`: 75%.
- Integration: 1 e2e test (mocked Tailscale) for daemon round-trip.
- Real-network test: manual at M5 close.

**Performance Benchmarks:**
- Daemon round-trip: p95 < 2 s.
- Daemon startup: < 5 s.
- Daemon CPU: < 5% idle.
- Daemon RAM: < 100 MB.

**Open Questions Resolved:**
- None new (M5 builds on M4 resolutions).

**Risks:**
- Tailscale latency variability at work network. Mitigation: surface latency in cockpit; orchestrator tolerates 20–80 ms baseline; operator escalates if work network blocks Tailscale.
- Cross-platform daemon packaging. Mitigation: Go binary preferred (single static binary per platform); document install per platform.
- Windows tmux is awkward (WSL2 or nothing). Mitigation: support PowerShell job control as fallback on Windows; tmux-via-WSL2 is operator's call.

**Dependencies:** M3 + M4 both complete.

**Demo:**
- Operator at work on Ubuntu. Opens cockpit from work browser pointing to home Mac via Tailscale. Sees `selffork-work-ubuntu` daemon online.
- Assigns a long-running task to the Ubuntu daemon: "Profile the CPU usage of this script." Daemon executes locally; cockpit on home Mac shows progress.
- Operator commutes home. Opens cockpit on the home Mac directly. Slider auto-shifts from 4 to 7. Resumes work.

**Bouncing Back Path:**
If M5 slips beyond 6 weeks, suspect cross-platform daemon packaging. Cut: ship macOS daemon only at v1.0; Windows + Ubuntu daemons in v1.1. The blocker is "brain extends," even if only to one other machine.

---

### M6 — Polish (3–4 weeks)

**Goal:** Production-grade safety, deployment, and operator notification.

**Scope:**

- `packages/orchestrator/deployer/ssh/`:
  - Zero-footprint SSH delivery: rsync/git-pull to CPU production server.
  - Build verification: orchestrator runs the project's build/test inside the shadow Docker container before deploy.
  - Rollback path: every release captures a "reverse note"; cockpit can trigger rollback.
- `packages/orchestrator/deployer/payload/`:
  - Proof packet assembly: viewport screenshot (Puppeteer) + 15-second video (where applicable) + build checksum + rollback note.
  - Telegram payload: structured message with packet attached.
  - Resolves Open Question §27.3 (payload format).
- `packages/body/sandbox/`:
  - Threshold table enforcement (PRD §15.3).
  - Action audit log: append-only, signed, replayable.
  - Kill-switch UI in cockpit (already stubbed in M4, fully wired here).
- `packages/mind/compaction/` enhancements:
  - Deterministic Lossless Context Management.
  - Nightly job: Speaker generates session summaries → indexed alongside raw turns.
- Undo / checkpoint:
  - Every "important" action (deploy, file delete, git push) creates a system snapshot.
  - Cockpit "Operations" view (new) can rewind to last 50 checkpoints.
- Approval workflows:
  - When threshold check fails, cockpit shows an inline "Approve / Reject / Halt" prompt.
  - Telegram payload includes inline-keyboard buttons for approval-on-the-go.

**Deliverables:**
- Operator says "ship it" in Chat → orchestrator builds → tests pass in shadow → SSH to CPU server → deploy succeeds → screenshot captured → Telegram payload arrives.
- Threshold enforcement: at slider 5, "git push" is blocked (threshold 9); cockpit shows the prompt for operator approval.
- Nightly compaction job runs and produces summaries indexed in Mind.
- Audit log replays a full 1-hour session deterministically.
- M6 demo video covering end-to-end deploy.

**Exit Criteria:**
- **End-to-end deploy in p95 < 5 minutes** (build + test + ship + verify) for a small project.
- Rollback verified: orchestrator reverts a deployment cleanly via the captured rollback note.
- Audit log replays a full 1-hour session deterministically (no missing entries, no order drift).
- Threshold table cannot be bypassed from cockpit (UI option for slider 10 + emergency override is logged but cannot lower PROD threshold below ∞).
- Telegram payload arrives within p95 < 10 s of done-state.

**Documentation Outputs:**
- `docs/architecture/deployment-and-rollback.md`
- `docs/architecture/audit-and-checkpoint-design.md`
- `docs/operations/runbook-incident-response.md`
- `docs/decisions/2026-XX_telegram_payload_format.md` (resolves §27.3)
- `docs/research/M6_korpus.md` (revisit deployment patterns from clippy + agent frameworks)

**Test Coverage Targets:**
- `orchestrator/deployer/`: 90% (high-stakes code).
- `body/sandbox/`: 95% (security-critical).
- `mind/compaction/`: 80%.
- Integration: 5 e2e tests:
  - End-to-end deploy success.
  - Deploy failure → no-deploy.
  - Rollback round-trip.
  - Threshold block path.
  - Audit replay.

**Performance Benchmarks:**
- End-to-end deploy: p95 < 5 min.
- Rollback: p95 < 2 min.
- Telegram payload latency: p95 < 10 s.
- Audit log write: p95 < 50 ms (per entry).
- Audit log replay (1h session): p95 < 30 s.

**Open Questions Resolved:**
- §27.3 (Telegram payload format)

**Risks:**
- SSH key management on the home Mac. Mitigation: macOS Keychain integration; never log keys.
- Production deploy is a high-blast-radius action. Mitigation: M6 only deploys to a *test* CPU server; real production deploys require operator approval beyond threshold for the entire v1.
- Puppeteer screenshot in headless mode failing on dynamic content. Mitigation: explicit wait conditions; retry with longer timeouts.
- Audit log signature validation overhead. Mitigation: use HMAC-SHA256, batch verify on replay.

**Dependencies:** M5 complete.

**Demo:**
- Operator: "Ship Atlas to test server."
- Orchestrator: build inside shadow Docker → tests pass → SSH to test CPU server → rsync artifacts → run health check → capture screenshot of deployed page.
- Telegram: "🟢 Atlas deployed. https://test.foundry.local. 42 KB shipped. Rollback: /rollback abc123."
- Operator opens link, looks. Replies "👍" in Telegram. State recorded.

**Bouncing Back Path:**
If M6 slips beyond 6 weeks, suspect SSH-deploy-with-shadow-CI complexity. Cut: ship simple SCP-based deploy without shadow-CI for v1.0; keep approval gates and Telegram payload, defer shadow-CI to v1.1. The blocker is "operator gets a Perfect Payload," not "build runs in shadow first."

---

### M7 — Reflex (4–6 weeks) — THE LAST MILE

**Goal:** Yamaç-style adapter ships. Stock E2B-it is replaced by `yamac-adapter-v1`.

**Scope:**

- `packages/reflex/data/cot/`:
  - CoT scoring pipeline: each turn gets a CoT-value score (length + decision keywords + context shift + new-topic).
  - High-score subset (~3K–4K) sent to Google AI Studio (Gemma 4 26B free tier) for synthetic CoT generation.
  - Low-score turns kept raw.
- `packages/reflex/data/review/`:
  - Operator's 1-week review sprint:
    - Read every CoT-augmented sample.
    - Tag each: `perfect` / `good` / `fix` / `kill`.
  - `perfect` → 2–3× training weight.
  - `kill` → excluded from dataset.
  - `fix` → operator hand-edits then re-categorizes.
- `packages/reflex/training/qlora/`:
  - QLoRA pipeline: attention-projection LoRA on Gemma 4 E2B-it Q4_0.
  - Yamaç-only weighted loss (PRD §8.1.3): 0.0 / 0.3 / 1.0 schedule.
  - Session-aware chat formatting with full session prefix.
  - **Decision: MLX LoRA vs Unsloth vs Lambda Labs A100** finalized at M7 kickoff (Open Question §27.1).
- `packages/reflex/eval/`:
  - Held-out corpus from `benchmarks/yamac_session_holdouts/`.
  - LLM-as-judge style win rate measurement.
  - Decision recall accuracy.
  - Refusal pattern match.
  - General capability regression (LiveCodeBench v6 subset).
- `packages/reflex/speaker/` adapter swap:
  - `config.yaml`: `adapter.enabled: true`, `adapter.path: ./artifacts/yamac-adapter-v1/`.
  - Hot-swap test: cockpit Chat tab can toggle stock vs adapter and the operator can A/B feel the difference.
  - Adapter metadata file (`metadata.yaml`) per PRD §9.3.
- Cockpit "Reflex" settings panel:
  - Show current adapter.
  - A/B toggle with prior version.
  - "I feel a drift" trigger for next 6-month retrain.
- Documentation: comprehensive write-up of training methodology, results, and known limitations.

**Deliverables:**
- ~8,000–12,000 normalized + reviewed training samples.
- `yamac-adapter-v1/` artifact (LoRA weights, ~hundreds of MB).
- Held-out evaluation report: win rate, recall, refusal match per category.
- Adapter loaded as default for Speaker.
- Cockpit Reflex panel live.
- M7 demo video showing A/B comparison.

**Exit Criteria:**
- **Adapted Speaker beats stock E2B-it at ≥ 60% style win rate** on held-out evaluation (LLM-as-judge with rubric).
- Held-out decision recall: ≥ 80% on questions whose answers exist in training data.
- Refusal pattern match: ≥ 90% on hand-built scenarios.
- General capability regression: ≤ 5% drop on LiveCodeBench v6 subset.
- Operator subjective acceptance: 1-week dogfood period; daily 1–10 score, mean ≥ 7.

**Documentation Outputs:**
- `docs/architecture/reflex-training-methodology.md`
- `docs/architecture/identity-continuity-and-drift.md`
- `docs/research/M7_eval_report.md` (full eval results, with citations)
- `docs/decisions/2026-XX_adapter_training_infrastructure.md` (resolves §27.1)
- `docs/decisions/2026-XX_adapter_distribution.md` (resolves §27.8 — likely local-only)
- `docs/decisions/2026-XX_adapter_acceptance_threshold.md` (resolves §27.14)
- `docs/operations/adapter-retrain-cadence.md`

**Test Coverage Targets:**
- `reflex/data/cot/`: 80%.
- `reflex/data/review/`: 70% (mostly UI).
- `reflex/training/qlora/`: 75% (training code is pipeline-heavy).
- `reflex/eval/`: 90% (high-stakes).

**Performance Benchmarks:**
- Adapter inference latency: ≤ 110% of stock (small overhead acceptable).
- Adapter load time on hot-swap: < 5 s.
- Eval pipeline runtime (full held-out): < 30 min.

**Open Questions Resolved:**
- §27.1 (adapter training infrastructure)
- §27.8 (adapter distribution)
- §27.14 (acceptance threshold)

**Risks:**
- 16 GB MBP may not be sufficient for QLoRA on E2B at meaningful rank. Mitigations:
  1. Start with rank 8 (smallest); evaluate; raise if quality insufficient.
  2. Fall back to Lambda Labs A100 rental (~$5 one-shot). Training-only cloud touch is permitted (PRD §12.3).
- Sample volume below 8K by M7 entry. Mitigation: extend M7 by 2 months if needed; delay rather than ship undertrained.
- Adapter regression: model loses general capability. Mitigation: held-out general benchmarks alongside style metrics. Hard gate: ≤ 5% drop.
- LLM-as-judge bias toward verbose responses. Mitigation: rubric explicitly weights conciseness; use multiple judge models (Claude Sonnet + GPT-4o); take majority.

**Dependencies:** M6 complete + ≥ 8K usable samples accumulated since M0.

**Demo:**
- Operator opens cockpit Reflex panel. Toggles between stock and `yamac-adapter-v1`. Asks the same question to both: "What should I prioritize when reviewing a PR?"
- Stock E2B-it: generic answer ("check tests, code quality, …").
- Adapter: Yamaç-voice answer ("İlk bakışta: kapsam doğru mu? Sonra refactor scope creep var mı? Sonra test coverage…").
- Operator records reaction in dogfood log.

**Bouncing Back Path:**
If M7 fails the 60% style win rate gate, the diagnosis options are:
1. **More data needed:** extend collection, retry in 2 months.
2. **Higher rank LoRA:** try rank 16 or 32; if 16 GB MBP can't, rent cloud GPU.
3. **MLP layers added to LoRA target:** increase capacity.
4. **Review sprint redo:** maybe `kill` filter was too lax; re-pass.
M7 does not ship a sub-quality adapter. v1.0 holds until adapter passes.

---

### M8 — Autonomous Yamaç (Layer 4) — DEFERRED, sub-PRD

**Goal:** Server-side fully-autonomous Jr. that takes a PRD and ships an application over days/weeks.

**Status:** Out of v1 scope. Tracked as a separate sub-PRD to be drafted ~12 months after M7 ships.

**Pre-conditions before sub-PRD kickoff:**
- M7 adapter has been in dogfood for ≥ 3 months.
- Operator has migrated to Mac Studio Ultra-class hardware (or 26B A4B is comfortable on whatever they're on).
- Operator has identified concrete projects suitable for fully-autonomous, multi-day runs.
- Open-source community engagement has matured (issues, contributors, forks).

**Vision sketch (placeholder, NOT a commitment):**
- Hetzner / Bulutova-class VPS hosts the running Jr. (this is the *one* legitimate cloud touch — execution server, not training; per PRD §12.3 carve-out).
- Agentic loop with self-correction and multi-step planning.
- Executor model is a separate, larger model (Claude Code-class). Yamaç Jr. is the *manager* in the loop.
- Telegram-only operator interface during a run.
- New milestone series M8.1 → M8.7 (mirroring Layer 1 structure but for Layer 4).

**Sub-PRD will cover:**
- Manager / Executor split protocol.
- VPS provisioning and security model.
- Multi-day state persistence.
- Cost economics (VPS + executor model API).
- Self-correction patterns.
- Failure recovery strategies.

---

## 3. Critical Path & Parallelization

### 3.1 Hard Dependencies

```
M-1 → M0 → M1 → M2 → (M3 ∥ M4) → M5 → M6 → M7
                                                  ↓
                                                v1.0

All deferred to v2.0+:
  M8 (Autonomous, sub-PRD)
  Vision drivers (Body web/android/ios)
  Watcher revival
```

### 3.2 Parallelization Map

| Pair | Independent? | Notes |
|---|---|---|
| M3 ∥ M4 | ✅ | Both depend on M2; both end before M5. |
| M2 ∥ M3 | ❌ | M3 needs M2's Mind for memory continuity. |
| M2 ∥ M4 | ❌ | M4's Context tab needs M2's Mind. |
| M5 ∥ M6 | ⚠️ | Mostly independent but M6 audit log reaches across pillars including M5 daemon actions; risk of integration debt. **Sequential preferred.** |
| Data collection ∥ all milestones | ✅ | Passive, no integration cost. |
| Korpus reflex reads ∥ each milestone | ✅ | Done before milestone arch work begins. |

### 3.3 Calendar Estimate

| Milestone | Estimate | Earliest Start | Earliest End |
|---|---|---|---|
| M-1 | 0.5 wk | 2026-04 | 2026-05 |
| M0 | 1.5 wk | 2026-05 | 2026-05 |
| M1 | 3 wk | 2026-05 | 2026-06 |
| M2 | 4 wk | 2026-06 | 2026-07 |
| M3 ∥ M4 | 4 wk (max of pair) | 2026-07 | 2026-08 |
| M5 | 3 wk | 2026-09 | 2026-09 |
| M6 | 3 wk | 2026-10 | 2026-10 |
| M7 | 5 wk + 1 wk operator review | 2026-11 | 2027-01 |
| **Nano v1.0 ship** | — | — | **~2027-01** |

Adjusted for slippage budget (+30%): **~2027-04**.

---

## 4. Passive Data Collection Cadence

Starts the day M0 lands. Runs every working day until M7 ingests it.

| Source | Cadence | Mechanism | Cumulative target by M7 |
|---|---|---|---|
| Claude Code session JSONL | Weekly | Cron: `cp -R ~/.claude/projects/ ~/yamac-jr-data/raw/claude-code/projects-$(date +%Y%m%d)/` | ~600 sessions, ~25K turns |
| OpenCode sessions | Manual, monthly | Operator runs `opencode export --json` to `~/yamac-jr-data/raw/opencode/` | ~150 sessions, ~6K turns |
| Gemini CLI logs | Monthly | Manual export | ~100 sessions, ~3K turns |
| Antigravity logs | Monthly | Manual export | ~50 sessions, ~1.5K turns |
| ChatGPT export | Every 2 months | Operator requests account export, dumps zip | ~150 conversations, ~3K turns post-filter |
| Claude.ai export | Every 2 months | Same | ~100 conversations, ~2K turns post-filter |
| GitHub repo sync | Hourly (M2 onwards) | Webhook → orchestrator → Mind ingest | live |

**Total cumulative target: ~10K–12K usable samples by M7.** Sweet spot for QLoRA personalization.

**Operator effort:** ~30 minutes per month after the initial setup. The system feeds itself.

---

## 5. Adapter Version Roadmap

| Version | Released | Trained On | Hardware Tier | Eval Highlights |
|---|---|---|---|---|
| (none) | M0–M6 | — | Nano | Stock E2B-it baseline |
| `yamac-adapter-v1` | M7 (~2027-01) | ~10K samples through 2026-12 | Nano (E2B-it Q4) | Style win ≥ 60%, recall ≥ 80%, refusal ≥ 90% |
| `yamac-adapter-v2` | ~2027-07 | +6 months data, retrain | Nano | Drift correction; style win ≥ 65% |
| `yamac-adapter-v3` | ~2028-01 | +6 months data; possibly Mid tier (E4B) | Nano or Mid | Multi-tier portability test |
| `yamac-adapter-v4` | ~2028-07 | +6 months data; Full Vision tier (26B A4B) | Full Vision (post-Mac-Studio-Ultra) | First adapter trained on bigger base |
| `yamac-adapter-vN` | every 6 months | +6 months data | tier-aligned | Continuous identity refresh |

**Trigger:** subjective drift, not schedule. The operator says "this doesn't feel like me anymore."

---

## 6. CLI Bridge Roadmap

| Bridge | Milestone | Notes |
|---|---|---|
| `claude-code/` | M1 | Initial; full quota signal parsing in M3 |
| `opencode/minimax` | M3 | Sub-model adapter |
| `opencode/glm` | M3 | Sub-model adapter |
| `opencode/gpt-4o-mini` | M3 | Sub-model adapter |
| `gemini-cli/` | M3 | Standalone provider |
| `antigravity/` | M3 (decision) or v1.1 | If decided as bridge in §27.5 |
| `cursor-cli/` | v1.2 | If/when Cursor exposes a CLI |
| `aider/` | v1.2 | Open-source CLI; community-driven addition |

---

## 7. Driver Roadmap (Body)

Vision-grounded UI control depends on Speaker tier.

| Driver | Tier required | Earliest Milestone | Notes |
|---|---|---|---|
| `desktop/` (CLI control via tmux) | Nano | M5 | All v1 surfaces |
| `web/` (browser-use / skyvern reference) | Full Vision | post-v2.0 | Needs 26B A4B vision |
| `android/` (mobile-mcp + docker-android) | Full Vision | post-v2.0 | Needs 26B A4B vision |
| `ios/` (appium-mcp) | Full Vision | post-v2.0 | Needs 26B A4B vision |
| `desktop-vision/` (OS click + type) | Full Vision | post-v2.0 | Bonus driver |

---

## 8. Documentation Cadence

Each milestone produces docs that **must** land before exit. The doc structure across the project:

```
docs/
├── PRD.md                              # this PRD
├── ROADMAP.md                          # this roadmap
├── Yamac_Jr_Nano_Kararlar.md           # historical decision SSOT
├── decisions/
│   └── 2026-XX_<topic>.md              # per-decision SSOT (post-M0)
├── architecture/
│   ├── diagram.md
│   ├── cross-pillar-boundaries.md
│   ├── sequence-cockpit-to-speaker.md
│   ├── cli-bridge-protocol.md
│   ├── mind-pillar-deep-dive.md
│   ├── hybrid-search-design.md
│   ├── cli-surfing-state-machine.md
│   ├── cockpit-orchestrator-protocol.md
│   ├── body-daemon-protocol.md
│   ├── deployment-and-rollback.md
│   ├── audit-and-checkpoint-design.md
│   ├── reflex-training-methodology.md
│   └── identity-continuity-and-drift.md
├── operations/
│   ├── install.md
│   ├── data-collection.md
│   ├── run-locally.md
│   ├── data-normalize-pipeline.md
│   ├── cli-bridge-add-new.md
│   ├── cockpit-auth.md
│   ├── cockpit-themes-and-locale.md
│   ├── install-daemon-{macos,windows,ubuntu}.md
│   ├── runbook-incident-response.md
│   └── adapter-retrain-cadence.md
├── research/
│   ├── M-1_data_inventory.md
│   ├── M1_korpus.md (Letta, Hexis)
│   ├── M2_korpus.md (mem0, cognee, git-context-controller)
│   ├── M3_korpus.md (browser-use, skyvern)
│   ├── M4_korpus.md (clippy, UI patterns)
│   ├── M5_korpus.md (mobile-use, skyvern revisit)
│   ├── M6_korpus.md (deployment patterns)
│   └── M7_eval_report.md
├── retros/
│   └── M{n}.md                         # post-milestone retrospective
└── archive/
    ├── Yamac_Jr_ARGE.pdf
    └── Yamac_Jr_Donanim_Arastirmasi.pdf
```

---

## 9. Risk Register (Project-Level)

| # | Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|---|
| 1 | Stock E2B-it quality is too weak for M3+M4 demos | Medium | Medium | Document the gap; the operator drives it; M7 fixes it | Reflex |
| 2 | 16 GB RAM exhausted under cockpit + Vite + MLX | Medium | High | Profile at M1; suspend Vite during heavy generation; consider OrbStack to constrain helpers | Reflex |
| 3 | QLoRA on 16 GB infeasible at usable rank | Medium | High | Cloud GPU one-shot for M7 training only; not a manifesto violation (training ≠ runtime) | Reflex |
| 4 | Tailscale latency unstable at work network | Low | Medium | Surface latency in cockpit; design for 20–80 ms; document fallback | Body |
| 5 | Provider 429 detection fragile across CLIs | Medium | Medium | Adapter-per-CLI design; ship Claude Code first, validate, then expand | Orchestrator |
| 6 | Decision SSOT structure churn (one-file vs split) | Low | Low | Decide on day 1 of M0; accept; move on | Operator |
| 7 | Sample volume below 8K by M7 | Low | High | Extend M7 by 2 months if needed; delay rather than ship undertrained | Reflex |
| 8 | Mac Studio Ultra acquisition window narrows | Low | Medium | Nano runs on existing MBP through v1; scaling is post-v1 | Operator |
| 9 | Open-source contributor confusion (hybrid pillar names) | Low | Low | Glossary in PRD; clear comments in `packages/__init__.py`; cross-link decision file | Operator |
| 10 | Cockpit dependencies (Vite 8, TS 6, React 19) churn break | Low | Medium | Lockfile commit; document workarounds; prefer LTS where available | Cockpit |
| 11 | Telegram bot misuse (someone else gets the token) | Low | Medium | Bot accepts commands only from operator's chat ID; rotate token if leaked | Orchestrator |
| 12 | SSH key compromise | Very Low | Critical | macOS Keychain; never log keys; rotate on hardware change | Orchestrator |
| 13 | Data loss in `~/yamac-jr-data/` | Low | High | Time Machine + monthly off-site encrypted snapshot (decision §27.9) | Operator |
| 14 | LLM-as-judge bias in eval | Medium | Medium | Multi-judge majority (Claude Sonnet + GPT-4o); rubric anti-verbose weighting | Reflex |
| 15 | Operator burnout on review sprint (M7) | Medium | High | Limit sprint to 5 days; spread across 1–2 weeks; allow `defer` category | Operator |
| 16 | Watcher revival creating retroactive integration debt | Low | Medium | Architecture (§7.2 + §10.1) reserves the slot; addition is opt-in | Reflex |
| 17 | Apache 2.0 license incompatibility with a future dependency | Very Low | Medium | License audit at M0; restrict deps to Apache-compatible | Operator |
| 18 | Dependency on Jina API pricing or availability | Low | Medium | Local fallback (BGE-m3) ships in tandem from M2 | Mind |

---

## 10. Operating Cadence

### 10.1 Decision Discipline

- Every locked decision lands in `docs/decisions/<date>_<topic>.md` within 24 hours.
- Decisions never live only in chat or PR comments. They graduate to a file or they are not locked.

### 10.2 Milestone Reviews

End-of-milestone retrospective written to `docs/retros/M{n}.md`:
- What worked.
- What slipped.
- Decisions made during the milestone.
- Risks discovered.
- Adjustments to upcoming milestones.

### 10.3 PRD / Roadmap Revisions

- PRD is versioned (PRD §31).
- Roadmap is also versioned (per §11 below).
- A locked decision that contradicts the PRD or Roadmap bumps the affected document with a changelog entry.
- A milestone slipping by more than 50% of estimate triggers a roadmap re-baseline with the change explained.

### 10.4 Korpus Reflex Cadence

- Each milestone consults at least one `examples_crucial/` rival in the relevant pillar before architecture work begins.
- Findings recorded in `docs/research/M{n}_korpus.md`.
- A new entry in `examples_crucial/` triggers a 24-hour read by an agent.

### 10.5 Three Experts Test

For any decision affecting the architecture (PRD §22):
- Defender: why might the current state be this way?
- Critic: what concretely breaks?
- Pragmatist: worth fixing now?

If only the Critic complains and evidence is weak, the change is dropped.

### 10.6 Anti-Hallucination Discipline

Every claim about the codebase in a decision doc, retrospective, or PR description must be backed by a file read with `path:line` reference. "I think" is not evidence.

---

## 11. Definition of Nano v1.0 Release

SelfFork ships **Nano v1.0** when **all of the following are true**:

- ✅ M7 adapter passes its exit criteria (≥ 60% Yamaç-style win rate on held-out + ≥ 80% decision recall + ≥ 90% refusal pattern + ≤ 5% capability regression).
- ✅ End-to-end vignette works (PRD §6.1): operator opens cockpit → assigns a task → walks away → returns to a Telegram Perfect Payload with a deployed test app.
- ✅ All cockpit tabs are live; zero mock data anywhere in `apps/web/src/`.
- ✅ All three machines (home macOS, work Windows, work Ubuntu) have daemons reporting (or the documented Bouncing Back exception).
- ✅ At least one CPU server has received a zero-footprint deployment with rollback verified.
- ✅ Documentation: PRD, ROADMAP, decision SSOT, install guide, operator runbook all current.
- ✅ License: Apache 2.0 across all packages (license audit done at M0).
- ✅ Test coverage: ≥ 80% per-pillar weighted average.
- ✅ Performance: all SLOs in PRD §25 met.
- ✅ Operator subjective acceptance: 1-week dogfood, mean 1–10 score ≥ 7.
- ✅ Tag `v1.0.0-nano` on `main`; GitHub release with the full Perfect Payload demo video attached.
- ✅ Public README updated to reflect "Nano v1.0 shipping; Full Vision in development."

---

## 12. Definition of Full Vision v2.0 Release (Forward-Looking)

The Full Vision v2.0 release ships when:

- Operator has migrated to Mac Studio Ultra-class hardware.
- Speaker upgrades to Gemma 4 26B A4B Q4 with `yamac-adapter-v3` or v4.
- At least one vision driver (web, android, or ios) is live and demonstrably controls a UI surface.
- Watcher revival completed (optional but recommended at this tier).
- Sub-PRD for M8 (Autonomous Yamaç) drafted and approved.
- Tag `v2.0.0-full-vision` on `main`.

---

## 13. Anniversary Reviews & Strategic Pauses

### 13.1 6-Month Anniversary

Mid-build (~2026-10), pause for 1 week:
- Re-read the PRD end-to-end.
- Audit all decisions against the manifesto.
- Confirm the roadmap calendar is still realistic.
- Adjust if the operator's goals or hardware reality has shifted.

### 13.2 12-Month Anniversary

Post-Nano-v1.0 (~2027-04):
- Comprehensive retrospective in `docs/retros/v1.0_anniversary.md`.
- Plan for Full Vision: hardware purchase commitment, sub-PRD scope.
- Public release announcement on GitHub: "Nano v1.0 shipped; here's what we learned."

### 13.3 24-Month Anniversary

Post-Full-Vision-v2.0 (~2028-04):
- Open-source community state-of-the-fork.
- Sub-PRD for M8 Autonomous launches.

---

## 14. Community & Adoption Plan

### 14.1 v1.0 Pre-Release

- README.md updated with realistic install instructions.
- Apache 2.0 LICENSE clearly visible.
- "Why this exists" section in README appealing to potential future scalers.
- Demo video pinned as GitHub release asset.

### 14.2 v1.0 Release Announcement

- Tag `v1.0.0-nano`.
- GitHub release with notes:
  - What works in Nano v1.0.
  - What's deferred to Full Vision v2.0.
  - How to fork and train your own adapter.
- Hacker News / Lobste.rs / Reddit r/LocalLLaMA submission (operator's call; not pushed in v1).

### 14.3 v1.1+ Iterations

Each minor release:
- Resolves at least one v1 deferred item (e.g., a vision driver, dark mode, a new CLI bridge).
- Documents what changed in `CHANGELOG.md`.

### 14.4 Open-Source Governance

- Operator is BDFL (Benevolent Dictator For Life) until v3.0 or until ill-suited.
- PRs accepted with operator review (no auto-merge).
- Architectural changes require a `docs/decisions/` entry.
- Forks encouraged; data sharing forbidden.

### 14.5 Code of Conduct

- Standard Apache-flavored CoC.
- Sensitive data discussions explicitly out of scope (each fork's data is their own).

---

## 15. Versioning

- **1.0.0** — 2026-04-27 — initial roadmap, capability-based M0–M7 with fine-tune deferred to M7.

Future revisions follow semver:
- **MAJOR** bump on milestone reordering or addition/removal.
- **MINOR** bump on scope changes within a milestone.
- **PATCH** bump on calendar adjustments, clarifications, or risk-register additions.

A roadmap revision must include:
- A changelog entry.
- A PR linked to the decision(s) that motivated the change.
- An updated PRD if the change reflects a vision-level shift.

---

## 16. Appendix: Sub-Milestone Breakdowns (Indicative)

For milestones that may benefit from sub-staging during execution:

### M2 sub-stages
- M2.1: SQLite schema + sqlite-vec/FTS5 wiring (1 wk)
- M2.2: Dense retrieval pipeline + Jina API + BGE fallback (1 wk)
- M2.3: BM25 + hybrid search + reranker (1 wk)
- M2.4: Query rewriting + router (0.5 wk)
- M2.5: Historian + decision indexer (0.5 wk)
- M2.6: Compaction night job + cockpit Context tab live (1 wk)

### M3 sub-stages
- M3.1: Claude Code adapter quota signal hardening (0.5 wk)
- M3.2: OpenCode adapter (Minimax + GLM + GPT-4o-mini) (1.5 wk)
- M3.3: Gemini CLI adapter (1 wk)
- M3.4: Scheduler quota tracker + cron-sleep (1 wk)
- M3.5: Telegram bot integration (0.5 wk)
- M3.6: Memory continuity across switch (0.5 wk)

### M4 sub-stages
- M4.1: Mission tab live (1 wk)
- M4.2: Run tab live (1 wk)
- M4.3: Chat queue + breakpoint inject (1 wk)
- M4.4: Context controls live + Fleet live + auth + slider (1 wk)

### M7 sub-stages
- M7.1: CoT scoring pipeline + Google AI Studio integration (1 wk)
- M7.2: Operator review sprint (1 wk dedicated; in parallel with M7.3)
- M7.3: QLoRA pipeline + training infrastructure (1 wk)
- M7.4: Eval harness + held-out scoring (1 wk)
- M7.5: Adapter swap in production + dogfood (1 wk)

---

**End of ROADMAP.**

*Tam olsun, bizim olsun. Kolaya kaçmadık.*
*Yamaç Jr. doğmak için sabırla bekliyor.*
