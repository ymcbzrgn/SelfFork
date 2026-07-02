# SelfFork (SelfFork Jr)

> **Autonomous Coding Orchestrator** — local Gemma + multi-CLI surfing +
> sandboxed execution + memory + cross-UI body control. The SelfFork Jr
> vision, four pillars deep.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

---

## What is SelfFork?

SelfFork wraps CLI coding agents (`opencode`, `claude-code`, `gemini-cli` +
snapper fleet) and points them at a **non-fine-tuned local LLM**
(Gemma 4 E2B-it via mlx-server). Given a PRD, it spins up an isolated
environment, hands the PRD to the agent, and watches the agent execute it
end-to-end — with memory, a heartbeat autonomy loop, a Telegram bridge to
the operator, and a 289-tool body fleet spanning mobile/browser/desktop/VR.

The four pillars — **Reflex** (fine-tuned adapter), **Body** (vision +
cross-UI control), **Mind** (memory + RAG), **Orchestrator** (CLI surfing +
scheduler) — see [`docs/PRD.md`](docs/PRD.md) and
[`docs/ROADMAP.md`](docs/ROADMAP.md).

---

## Status (as of S-ToolFleet close, 2026-05-26)

| Pillar / surface | Status |
|---|---|
| **Orchestrator** — round-loop session lifecycle, multi-CLI router (quota + affinity + operator override), spawn multi-child, heartbeat autonomy daemon (ADR-008), stuck detector, auto-PR tool, FastAPI dashboard API, two-way Telegram bridge (voice + corrections) | ✅ implemented |
| **Tool fleet** — 289 tools (87 eager + 202 deferred via RAG `tool_search`): mobile (iOS/Android/Expo), browser (Playwright + stealth + network interception), desktop (macOS), GitHub, skills, VR (Quest / Vision Pro) — ADR-010 §9 | ✅ implemented |
| **Mind** — six-tier memory (DuckDB + LanceDB), hybrid retrieval (vector + BM25 + tag fusion) with HippoRAG-2 PPR graph blend, dual-pool PROJECT/GLOBAL scoping (ADR-009), reflection + auto-dream pipeline | ✅ implemented (some orchestrator wiring pending) |
| **Body** — drivers for iOS/Android/web/macOS/Quest/VisionPro, vision loop, action-level warden, screenshot store; Go remote daemon | ✅ implemented (daemon intake WS pending) |
| **Cockpit web UI** (`apps/web`) — v3: Dashboard / Workspace (Kanban + Live Run Theater + Notes) / Talk / Connections / Settings, live WS streams | ✅ implemented (ADR-007 S1–S8) |
| **Reflex** — fine-tune pipeline | 📦 skeleton — **M7 last mile**; `selffork train` CLI is a dry-plan stub |
| **Next** | **S-Train sprint → M7 freeze** (ADR-010 §9.17): fine-tune corpus stabilization on the Format Freeze |

3019 backend tests (Faz 4 close baseline), mypy `--strict`, ruff
lint+format, GH Actions CI. Milestone history M-1→M6 + the seven
post-ADR-007 sprints: see [`docs/ROADMAP.md`](docs/ROADMAP.md) banner and
ADR-006→011 in [`docs/decisions/`](docs/decisions/).

---

## Quickstart

```bash
# 1. Clone + install dev workspace.
uv sync --all-packages --group dev

# 2. (Optional) Install the actual runtime + agent on your machine.
#    These are deployment-time deps, not vendored:
#       uv pip install mlx-lm                # Apple Silicon LLM runtime
#       npm install -g opencode-ai           # CLI coding agent

# 3. Run a PRD end-to-end.
uv run selffork run docs/PRD.md --mode subprocess
```

**What happens under the hood**:

1. `mlx-server` is spawned as a subprocess on `localhost:8001`, serving
   Gemma 4 E2B Q4 (MLX 4-bit on Apple Silicon, GGUF Q4_0 on Linux) over an OpenAI-compatible HTTP API.
2. A workspace dir is created at `~/.selffork/workspaces/<session_id>/`.
3. The selected CLI agent is spawned in that workspace, env-redirected to
   talk to the local mlx-server (`OPENAI_BASE_URL`).
4. The PRD is fed to the agent via `--print --output-format stream-json`.
5. The agent executes the PRD; SelfFork streams events, updates a plan
   document at `<workspace>/.selffork/plan.json`, writes a JSONL audit
   log at `~/.selffork/audit/<session_id>.jsonl`.
6. On exit, sandbox is torn down and runtime is stopped.

Dashboard + heartbeat: `uv run selffork ui` serves the FastAPI backend
for `apps/web` (Next.js). Configuration: edit
[`selffork.yaml`](selffork.yaml) or set `SELFFORK_*` env vars
(e.g. `SELFFORK_RUNTIME__PORT=9000`).

---

## Project Structure

```text
SelfFork/
├── packages/
│   ├── orchestrator/       # runtime, sandbox, cli_agent, router, lifecycle,
│   │                       # heartbeat, telegram, spawn, tools (289-tool fleet),
│   │                       # dashboard API, cli
│   ├── shared/             # config, logging, errors, audit, ports, ulid, shellquote
│   ├── reflex/             # M7 LAST MILE — fine-tune pipeline (skeleton)
│   ├── body/               # drivers (ios/android/web/macos/vr), vision,
│   │                       # action warden, storage + Go remote daemon
│   └── mind/               # six-tier memory, GraphRAG, dual-pool, reflection
├── apps/
│   └── web/                # v3 Cockpit UI (Next.js): Dashboard/Workspace/Talk/
│                           # Connections/Settings
├── infra/                  # docker, deploy, install scripts, tailscale
├── tests/
│   └── e2e/                # End-to-end smoke tests
├── benchmarks/
│   └── m5_vision_eval/     # M5 vision eval harness (placeholder corpus)
├── docs/
│   ├── PRD.md              # Product requirements (full vision)
│   ├── ROADMAP.md          # Milestones M-1 → M8 (+ 2026-05-26 status banner)
│   ├── decisions/          # ADR-001 → ADR-011 (locked decisions)
│   ├── plans/              # Milestone implementation plans + smoke checklists
│   └── archive/            # ARGE PDFs (SelfFork Jr. design history)
├── selffork.yaml           # Default config (annotated)
├── pyproject.toml          # uv workspace root
└── LICENSE                 # Apache 2.0
```

---

## Development

```bash
# Lint / format / type-check / test — what CI runs.
uv run ruff check packages/ tests/
uv run ruff format --check packages/ tests/
uv run mypy packages/ tests/
uv run pytest -m "not real_runtime and not real_docker"

# Pre-commit hooks (one-time setup).
uv run pre-commit install
```

`mypy --strict` is non-negotiable. No `print()`, no bare `Exception`, no
`--no-verify`. Code is enterprise-grade. See
[ADR-001 §3](docs/decisions/ADR-001_MVP_v0.md#3-language--tooling).

---

## Mottos

* **TAM OLSUN, BİZİM OLSUN** — quality before speed, always.
* **KOLAYA KAÇMAYIZ** — the hard path is the right one.
* **BENİ TANISIN YETER** — we teach reflex, not facts.
* **HER MESAJ SIFIRDAN DEĞİL** — sessions remember.

---

## License

Apache License 2.0. See [LICENSE](LICENSE).
