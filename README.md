# SelfFork (SelfFork Jr)

> **Autonomous Coding Orchestrator** — local Gemma + opencode + sandboxed
> execution. The first slice of the SelfFork Jr vision (CLAUDE.md).

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

---

## What is SelfFork?

SelfFork wraps a CLI coding agent (`opencode` today; `claude-code`, `codex`,
`gemini-cli` planned) and points it at a **non-fine-tuned local LLM**
(Gemma 4 E2B-it via mlx-server today; ollama / llama.cpp / vllm planned).
Given a PRD, it spins up an isolated environment, hands the PRD to the
agent, and watches the agent execute it end-to-end.

The full vision is a four-pillar autonomous system — **Reflex** (fine-tuned
adapter), **Body** (vision + cross-UI control), **Mind** (memory + RAG),
**Orchestrator** (CLI surfing + scheduler) — see [`docs/PRD.md`](docs/PRD.md)
and [`docs/ROADMAP.md`](docs/ROADMAP.md). MVP v0 ships only the
Orchestrator pillar's first slice; the others are skeleton packages today.

---

## MVP v0 — Status

| Component | Status |
|---|---|
| `selffork run <prd>` CLI | ✅ |
| `LLMRuntime` ABC + `MlxServerRuntime` | ✅ (3 stub backends ready for ollama / llama-cpp / vllm) |
| `Sandbox` ABC + `SubprocessSandbox` (Mac dev) + `DockerSandbox` (server) | ✅ |
| `CLIAgent` ABC + `OpenCodeAgent` | ✅ (3 stub backends ready for claude-code / codex / gemini-cli) |
| `Plan` model + `FilesystemPlanStore` | ✅ (git stub ready for M2+) |
| `Session` lifecycle state machine + audit log | ✅ |
| Reflex / Body / Mind packages | 📦 skeleton — implementations land in M7 / M5 / M2 |
| Cockpit web UI | ⏳ M4 |
| Multi-CLI surfing + scheduler | ⏳ M3 |

239 tests, mypy `--strict`, ruff lint+format, GH Actions CI.

Architecture: see [`docs/decisions/ADR-001_MVP_v0.md`](docs/decisions/ADR-001_MVP_v0.md).

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
   `gemma-3-e2b-it-q4_0` over an OpenAI-compatible HTTP API.
2. A workspace dir is created at `~/.selffork/workspaces/<session_id>/`.
3. `opencode` is spawned in that workspace, env-redirected to talk to the
   local mlx-server (`OPENAI_BASE_URL`).
4. The PRD is fed to `opencode` via `--print --output-format stream-json`.
5. opencode executes the PRD; SelfFork streams events, updates a plan
   document at `<workspace>/.selffork/plan.json`, writes a JSONL audit
   log at `~/.selffork/audit/<session_id>.jsonl`.
6. On exit, sandbox is torn down and runtime is stopped.

Configuration: edit [`selffork.yaml`](selffork.yaml) or set
`SELFFORK_*` env vars (e.g. `SELFFORK_RUNTIME__PORT=9000`).

---

## Project Structure

```text
SelfFork/
├── packages/
│   ├── orchestrator/       # MVP v0 — runtime, sandbox, cli_agent, plan, lifecycle, cli
│   ├── shared/             # config, logging, errors, audit, ports, ulid, shellquote
│   ├── reflex/             # M7 LAST MILE — fine-tune pipeline (skeleton)
│   ├── body/               # M5 — vision + cross-UI control (skeleton)
│   └── mind/               # M2 — memory + RAG + compaction (skeleton)
├── apps/                   # M4 — Cockpit web/mobile/desktop UI (empty until then)
├── infra/
│   └── docker/
│       └── opencode-runtime/  # Base image for DockerSandbox mode
├── tests/
│   └── e2e/                # End-to-end smoke tests
├── docs/
│   ├── PRD.md              # Product requirements (full vision)
│   ├── ROADMAP.md          # Milestones M-1 → M8
│   ├── decisions/          # ADRs (locked decisions)
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
`--no-verify`. Code is enterprise-grade; functional scope is small. See
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
