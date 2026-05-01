# ADR-001 — SelfFork MVP v0 Architecture

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-05-01 |
| **Authors** | Yamaç Bezirgan (decisions), Claude Code (drafting) |
| **Supersedes** | — |
| **Related** | `docs/PRD.md`, `docs/ROADMAP.md`, `docs/decisions/Operator_UI_Vision_archive.md`, `docs/Operator_Locked_Decisions.md` |
| **Pillars affected** | Orchestrator (primary); Shared, Reflex/Body/Mind (skeletons only) |

---

## TR — Yönetici Özeti

SelfFork'un ilk çalışan dilimi. `selffork run <prd-path> [--mode docker|subprocess]` komutu:

1. **mlx-server**'da non-fine-tuned **Gemma 4 E2B-it** ayağa kaldırır (OpenAI-compatible HTTP).
2. İzole bir env açar — Mac dev'de subprocess shell, sunucuda Docker container.
3. İçeride **opencode** CLI agent'ını spawn eder, `OPENCODE_BASE_URL`'i mlx-server'a yönlendirir.
4. PRD'yi opencode'a besler, JSON-line stream'ini dinler, plan-doc'u günceller, audit log yazar.
5. Bittiğinde teardown.

**Fonksiyonel scope minik, kod enterprise.** Pluggable interface'ler (LLMRuntime / Sandbox / CLIAgent / PlanStore) day 1'den. Reflex/Body/Mind paketleri iskelet halinde bekler. Python 3.12, Pydantic v2 config, structlog, mypy strict, pytest, GH Actions CI.

Bu ADR; package layout, 4 ana interface, state machine, config schema, audit format, error hierarchy, test stratejisi ve done-tanımını sabitler. **Kod yazımına başlanmadan önce onay alınır** (Bölüm 16).

---

## 1. Context

SelfFork, dört ayaklı (Reflex / Body / Mind / Orchestrator) otonom kodlama orchestrator'ı olarak tasarlanmıştır (bkz. `docs/PRD.md`). Tam vizyon, PRD'nin §3 ve §7'sinde, ROADMAP'in M-1 → M8 milestone planında detaylanmıştır.

Bu ADR, **MVP v0** için en küçük çalışır dilimi tanımlar. Hedef:

> *"Kullanıcı `selffork` çalıştırır → izole bir terminal açılır → içinde opencode başlar → opencode lokal Gemma'ya bağlanır → ona verdiğim PRD'yi gerçekleştirir."*

Bu dilim, ROADMAP'teki M0 (Foundation) ile M1 (Speaker Stub) arası bir konumda yer alır; **fine-tune yoktur** (M7), Body yoktur (M5), Mind yoktur (M2). Sadece Orchestrator pillar'ının iskeleti + non-fine-tuned model runtime + tek-CLI-agent spawn.

### 1.1 Prior art consulted

Six structured prior-art surveys (over agentic-CLI orchestration tools)
sabitledi MVP'nin pattern'larını. Patterns harvested by category:

| Category | Verdict | Strongest contribution |
|---|---|---|
| Tmux session lifecycle | PATTERN-ONLY | session lifecycle + zsh shell-quote helpers |
| CLI agent runner shell | PATTERN-ONLY | binary resolver + CLI arg/env builders + state machine |
| Local LLM desktop shell | PATTERN-ONLY | GGUF catalog + disk layout (NOT runtime — no HTTP API exposed) |
| Async subprocess wrapper | ADOPT | `asyncio.create_subprocess_exec` wrapper + `BASE_URL` env redirect |
| Plan-as-state launcher | PATTERN-ONLY | Launcher + plan-as-state-document combination |
| Sandboxed CLI runner | combined | Subprocess sandbox + port allocation + Docker container shape |

Aggregate observations land in §13 as anonymized "prior art" attributions.

### 1.2 Mandates honored

- **CLAUDE.md MANDATE 5** — kod ajanlar değil, ana orchestrator (Claude/the operator) tarafından yazılır.
- **CLAUDE.md MANDATE 7** — üç ayağı birlikte tut. MVP v0 sadece Orchestrator implement etse de Reflex/Body/Mind iskeletleri day 1'den repo'da yer alır.
- **CLAUDE.md MANDATE 9** — korpus refleksi: her mimari karar bir veya daha fazla rakip bulgusuna dayanır (Bölüm 13).
- **`feedback_backend_first.md`** — UI yok; pillar contracts önce.
- **`feedback_enterprise_code.md`** — fonksiyonel scope minik, kod enterprise + ileriye dönük.
- **PRD §3.2 Tenet 4 — Local Sovereignty** — model lokal, runtime lokal; cloud LLM API çağrısı yok.

---

## 2. Decision Summary

| Konu | Karar |
|---|---|
| Dil | Python 3.12+ |
| Paket yöneticisi | `uv` (lockfile + hızlı resolution); fallback `pip` |
| Type checking | `mypy --strict` |
| Lint | `ruff check` (B, E, F, I, N, UP, ASYNC, RET) |
| Format | `ruff format` |
| Test | `pytest` + `pytest-asyncio` + `pytest-cov` (≥80% orchestrator, ≥60% shared) |
| Config | Pydantic v2 (`BaseSettings`), YAML + env override |
| Logging | `structlog` (JSON), correlation IDs |
| Errors | `SelfForkError` rooted hierarchy |
| Audit | jsonl per session, structured categories |
| CI | GitHub Actions, macOS + Linux matrix |
| Repo layout | 4 pillar (orchestrator full, reflex/body/mind skeleton), shared, apps (empty), infra/docker |
| LLMRuntime impls | `mlx-server` (MVP); ollama / llama-cpp / vllm stubs |
| Sandbox impls | `subprocess` + `docker` (both MVP) |
| CLIAgent impls | `opencode` (MVP); claude-code / codex / gemini-cli stubs |
| PlanStore impls | `filesystem` (MVP); git-tracked stub |

---

## 3. Language & Tooling

**Decision:** Python 3.12+.

**Rationale:**
- mlx-server ve mlx-lm Apple-resmi Python kütüphaneleri.
- `free-claude-code/cli/session.py:26-279` (subprocess wrapper) Python; verbatim adapt edilir (lines 127-133, 142-178, 261-278).
- ROADMAP M7'de Reflex eğitimi MLX/Unsloth — Python ekosistemi.
- opencode TypeScript ama subprocess olarak çağrılır; parent dil bağımsız.
- CLAUDE.md proje yapısında root `pyproject.toml` (ML + agent core) öngörülmüştür.
- mypy strict + Pydantic v2 ile enterprise type safety.

**Rejected alternatives:** §14.1, §14.2.

**Tooling stack:**
```
Python 3.12+
├── uv (package manager + venv)
├── pyproject.toml (single source of truth for deps)
├── mypy --strict (type checking)
├── ruff check + format (lint + format)
├── pytest + pytest-asyncio + pytest-cov (test)
├── pre-commit (hook chain)
└── GitHub Actions (CI: macOS + Linux)
```

---

## 4. Repository Layout

Final tree for MVP v0 commit. Pillar packages exist from day 1; only Orchestrator and Shared have implementation today. Reflex/Body/Mind contain typed stubs and TODO docstrings.

```
SelfFork/
├── packages/
│   ├── orchestrator/                    # MVP v0 — implementation lives here
│   │   ├── pyproject.toml
│   │   ├── src/selffork_orchestrator/
│   │   │   ├── __init__.py
│   │   │   ├── runtime/                 # LLMRuntime ABC + impls
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py
│   │   │   │   ├── mlx_server.py        # MVP impl
│   │   │   │   ├── ollama.py            # stub (NotImplementedError + docstring)
│   │   │   │   ├── llama_cpp.py         # stub
│   │   │   │   └── vllm.py              # stub
│   │   │   ├── sandbox/                 # Sandbox ABC + impls
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py
│   │   │   │   ├── subprocess.py        # MVP impl
│   │   │   │   └── docker.py            # MVP impl
│   │   │   ├── cli_agent/               # CLIAgent ABC + impls
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py
│   │   │   │   ├── events.py            # AgentEvent typed model
│   │   │   │   ├── opencode.py          # MVP impl
│   │   │   │   ├── claude_code.py       # stub
│   │   │   │   ├── codex.py             # stub
│   │   │   │   └── gemini_cli.py        # stub
│   │   │   ├── plan/                    # plan-as-state document
│   │   │   │   ├── __init__.py
│   │   │   │   ├── model.py             # Pydantic Plan, SubTask
│   │   │   │   ├── store_base.py        # PlanStore ABC
│   │   │   │   └── store_filesystem.py  # MVP impl
│   │   │   ├── lifecycle/               # session state machine
│   │   │   │   ├── __init__.py
│   │   │   │   ├── states.py            # SessionState enum + transitions
│   │   │   │   └── session.py           # Session orchestration
│   │   │   ├── supervisor.py            # multi-project supervisor (single-project today)
│   │   │   └── cli.py                   # `selffork` entrypoint (Click/Typer)
│   │   ├── tests/
│   │   │   ├── unit/
│   │   │   ├── integration/
│   │   │   └── e2e/
│   │   └── README.md
│   │
│   ├── shared/                          # cross-pillar primitives, day 1
│   │   ├── pyproject.toml
│   │   ├── src/selffork_shared/
│   │   │   ├── __init__.py
│   │   │   ├── config.py                # Pydantic settings + selffork.yaml loader
│   │   │   ├── logging.py               # structlog setup, correlation IDs
│   │   │   ├── errors.py                # SelfForkError hierarchy
│   │   │   ├── audit.py                 # jsonl audit logger
│   │   │   ├── ports.py                 # free port allocation
│   │   │   ├── ulid.py                  # correlation/session ID generation
│   │   │   └── shellquote.py            # zsh-safe shell quoting (amux:171-194 pattern)
│   │   ├── tests/unit/
│   │   └── README.md
│   │
│   ├── reflex/                          # M7 LAST MILE — skeleton only
│   │   ├── pyproject.toml
│   │   ├── src/selffork_reflex/
│   │   │   ├── __init__.py              # `__all__ = []` + TODO docstring
│   │   │   ├── data/__init__.py         # placeholder
│   │   │   ├── training/__init__.py
│   │   │   ├── eval/__init__.py
│   │   │   └── adapter/__init__.py
│   │   └── README.md                    # "M7 LAST MILE — see ROADMAP §M7"
│   │
│   ├── body/                            # M5 — skeleton only
│   │   ├── pyproject.toml
│   │   ├── src/selffork_body/
│   │   │   ├── __init__.py
│   │   │   ├── vision/__init__.py
│   │   │   ├── drivers/{android,ios,web,desktop}/__init__.py
│   │   │   └── sandbox/__init__.py      # NB: Body's sandbox is action-level, not orchestrator-level
│   │   └── README.md
│   │
│   └── mind/                            # M2 — skeleton only
│       ├── pyproject.toml
│       ├── src/selffork_mind/
│       │   ├── __init__.py
│       │   ├── memory/__init__.py
│       │   ├── rag/__init__.py
│       │   ├── compaction/__init__.py
│       │   └── historian/__init__.py
│       └── README.md
│
├── apps/                                # empty until M4 (Cockpit)
│   └── README.md                        # "Surfaces land in M4"
│
├── infra/
│   └── docker/
│       └── opencode-runtime/
│           ├── Dockerfile               # base image: opencode + mlx-server
│           ├── entrypoint.sh
│           └── README.md
│
├── tests/                               # cross-package integration + e2e
│   └── e2e/
│       └── test_selffork_run_smoke.py   # MVP v0 done-criterion
│
├── docs/
│   ├── PRD.md                           # already exists
│   ├── ROADMAP.md                       # already exists
│   ├── Operator_Locked_Decisions.md        # already exists (Turkish locked decisions)
│   ├── decisions/
│   │   ├── Operator_UI_Vision_archive.md  # already exists
│   │   └── ADR-001_MVP_v0.md            # this file
│   └── archive/                         # already exists
│
│
├── .claude/                             # Claude Code agent definitions + memory
├── .opencode/                           # OpenCode agent definitions
├── .github/
│   └── workflows/
│       ├── ci.yml                       # lint + type + unit + integration
│       └── e2e.yml                      # smoke on macOS (Apple Silicon)
│
├── pyproject.toml                       # workspace root, defines uv workspace
├── selffork.yaml                        # default config (commented)
├── README.md
├── CLAUDE.md
├── GEMINI.md
├── LICENSE                              # Apache 2.0
└── .gitignore
```

**Workspace model:** `uv workspace` with one root `pyproject.toml` declaring the 5 packages (`packages/orchestrator`, `packages/shared`, `packages/reflex`, `packages/body`, `packages/mind`). Inter-package imports via standard package paths; no cross-imports outside `packages/shared` (per CLAUDE.md MANDATE 7 boundary discipline).

---

## 5. Core Interfaces

The four ABCs that anchor MVP v0's pluggability promise. Every implementation, present or future, conforms to these. Writing a new backend (Ollama, vLLM, Codex, Git-tracked plan store) means implementing one ABC — not modifying SelfFork core.

### 5.1 LLMRuntime

**Purpose:** Bring up a local LLM that exposes an OpenAI-compatible HTTP API on a localhost port. opencode (and any OpenAI-SDK-compatible client) connects via `OPENCODE_BASE_URL`-style env var.

**Implementations:** `MlxServerRuntime` (MVP), `OllamaRuntime` (M1+), `LlamaCppServerRuntime` (M1+), `VllmRuntime` (M2+).

```python
from abc import ABC, abstractmethod
from typing import AsyncContextManager

class LLMRuntime(ABC):
    """Local LLM runtime exposing an OpenAI-compatible HTTP API.

    Lifecycle: instantiate → start() → (use base_url) → stop().
    Implementations must be safe to start/stop multiple times in a
    process; multiple instances may coexist (multi-project).
    """

    @abstractmethod
    async def start(self) -> None:
        """Spawn runtime subprocess, wait for /v1/models readiness.

        Raises:
            RuntimeStartError: subprocess failed to spawn or never became
                healthy within RuntimeConfig.startup_timeout_seconds.
        """

    @abstractmethod
    async def stop(self) -> None:
        """Graceful shutdown: SIGTERM, wait grace, SIGKILL fallback.

        Idempotent — safe to call when already stopped.
        """

    @property
    @abstractmethod
    def base_url(self) -> str:
        """OpenAI-compatible base URL, e.g. 'http://127.0.0.1:8001/v1'.

        Available only between start() and stop(). Raises RuntimeNotStarted
        if accessed outside that window.
        """

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Model identifier the runtime is serving, e.g. 'gemma-3-e2b-it-q4_0'."""

    @abstractmethod
    async def health(self) -> bool:
        """True if the runtime accepts requests right now."""
```

**MVP impl note (`MlxServerRuntime`):** spawns `mlx_lm.server` (or `mlx-server` CLI) as a subprocess, polls `/v1/models` until 200 OK or timeout. Port from `RuntimeConfig.port` or auto-allocated via `selffork_shared.ports.find_free_port()`. Stop = SIGTERM + 5s wait + SIGKILL.

### 5.2 Sandbox

**Purpose:** Isolated execution environment for a coding agent. Two MVP modes (subprocess on Mac dev, Docker container on server) behind a single interface.

**Implementations:** `SubprocessSandbox` (MVP), `DockerSandbox` (MVP). Future: VM, k8s pod.

```python
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Mapping

class SandboxProcess(ABC):
    """Handle to a process running inside a sandbox."""

    @property
    @abstractmethod
    def pid(self) -> int: ...

    @abstractmethod
    async def stdout(self) -> AsyncIterator[bytes]:
        """Async iterator of stdout chunks."""

    @abstractmethod
    async def stderr(self) -> AsyncIterator[bytes]: ...

    @abstractmethod
    async def wait(self) -> int:
        """Block until process exits, return exit code."""

    @abstractmethod
    async def kill(self, grace_seconds: float = 1.0) -> None:
        """SIGTERM, wait grace, SIGKILL."""


class Sandbox(ABC):
    """Isolated execution environment for an autonomous agent."""

    @abstractmethod
    async def spawn(self) -> None:
        """Create the isolated environment.

        For SubprocessSandbox: prepare workspace dir, no subprocess yet.
        For DockerSandbox: docker run --rm -d ... → container ID stored.

        Raises:
            SandboxSpawnError: env could not be created.
        """

    @abstractmethod
    async def exec(
        self,
        command: list[str],
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> SandboxProcess:
        """Run a process inside the sandbox; returns a streaming handle.

        For SubprocessSandbox: asyncio.create_subprocess_exec with cwd+env.
        For DockerSandbox: docker exec -i <container> ... with --env-file.

        Multiple concurrent exec() calls are allowed (e.g. agent + side proc).
        """

    @abstractmethod
    async def teardown(self) -> None:
        """Stop all running processes, clean up resources.

        Idempotent. Always called on session end (success or failure).
        """

    @property
    @abstractmethod
    def workspace_path(self) -> str:
        """Absolute path to the project workdir as seen FROM INSIDE the sandbox.

        For SubprocessSandbox: same as host path.
        For DockerSandbox: bind mount target, e.g. '/workspace'.
        """

    @property
    @abstractmethod
    def host_workspace_path(self) -> str:
        """Path on the HOST filesystem. Equals workspace_path for subprocess mode."""
```

**MVP impl notes:**
- `SubprocessSandbox`: workspace under `~/.selffork/workspaces/<session_id>/`, exec via `asyncio.create_subprocess_exec(cwd=..., env=...)`. Kill: SIGTERM → 1s → SIGKILL (understudy `exec-tool.ts:244-252`). Stdout/stderr piped to log file (headroom `wrap.py:135-138` — pipe-buffer deadlock mitigation).
- `DockerSandbox`: image from `infra/docker/opencode-runtime/Dockerfile`, `docker run --rm -d -v <host>:<workspace>` + port maps. Exec via `docker exec`. Teardown: `docker stop`.

### 5.3 CLIAgent

**Purpose:** Adapter for an external CLI coding agent. Knows how to (a) locate the binary, (b) build args, (c) inject env (notably the LLM base URL redirect), (d) parse the agent's structured output, (e) detect completion.

**Implementations:** `OpenCodeAgent` (MVP), `ClaudeCodeAgent` (M1+), `CodexAgent` (M3+), `GeminiCliAgent` (M3+).

```python
from abc import ABC, abstractmethod
from typing import Mapping

from selffork_orchestrator.cli_agent.events import AgentEvent

class CLIAgent(ABC):
    """Adapter for an external CLI coding agent."""

    @abstractmethod
    def resolve_binary(self) -> str:
        """Locate the agent binary. Returns absolute path.

        Resolution order (Codeman opencode-cli-resolver.ts:1-72 pattern):
          1. Explicit path from CLIAgentConfig.binary_path
          2. Project-local node_modules/.bin
          3. PATH lookup
          4. Common install locations (~/.local/bin, /opt, /usr/local/bin)

        Raises:
            AgentBinaryNotFoundError: with a helpful install hint.
        """

    @abstractmethod
    def build_args(self, prd_path: str, plan_path: str, workspace: str) -> list[str]:
        """Construct CLI args for spawning the agent with the PRD task."""

    @abstractmethod
    def build_env(
        self,
        runtime_base_url: str,
        runtime_model_id: str,
        base_env: Mapping[str, str],
    ) -> dict[str, str]:
        """Env vars to inject. Notably: redirect LLM calls to local runtime.

        Pattern reference: free-claude-code cli/session.py:76-86 sets
        ANTHROPIC_BASE_URL + a placeholder API key + TERM=dumb.
        OpenCodeAgent sets the equivalent env vars for opencode's
        OpenAI-compatible client.
        """

    @abstractmethod
    async def parse_event(self, line: bytes) -> AgentEvent | None:
        """Parse a single line of stdout into a typed event.

        Returns None for non-event lines (banner, progress noise).
        For opencode --output-format stream-json: json.loads each line.
        """

    @abstractmethod
    def is_done(self, event: AgentEvent) -> bool:
        """True if this event signals the agent is finished its work."""
```

`AgentEvent` is a discriminated union (Pydantic Tagged) over the categories the agent emits: `started`, `tool_call`, `tool_result`, `assistant_message`, `error`, `done`, `exit`. `OpenCodeAgent.parse_event` maps opencode's stream-json shape to this canonical form. Future agents map their own formats.

### 5.4 PlanStore

**Purpose:** Persistent plan-as-state document. The PRD is decomposed into a `Plan` of `SubTask`s with states; SelfFork writes it once at session start, the agent reads/updates it as it works (via filesystem). Inspired by `agentscope/plan/_plan_model.py:11-66, _plan_notebook.py:16-167`.

**Implementations:** `FilesystemPlanStore` (MVP), `GitPlanStore` (M2+, version-tracked).

```python
from abc import ABC, abstractmethod
from enum import StrEnum
from datetime import datetime

from pydantic import BaseModel, Field

class SubTaskState(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    ABANDONED = "abandoned"

class SubTask(BaseModel):
    id: str
    title: str
    description: str
    expected_outcome: str
    state: SubTaskState = SubTaskState.TODO
    notes: str = ""
    updated_at: datetime | None = None

class Plan(BaseModel):
    session_id: str
    prd_path: str
    created_at: datetime
    updated_at: datetime
    subtasks: list[SubTask] = Field(default_factory=list)


class PlanStore(ABC):
    """Persistent plan-as-state document."""

    @abstractmethod
    async def load(self, session_id: str) -> Plan: ...

    @abstractmethod
    async def save(self, plan: Plan) -> None: ...

    @abstractmethod
    async def update_subtask_state(
        self,
        session_id: str,
        subtask_id: str,
        new_state: SubTaskState,
        notes: str | None = None,
    ) -> Plan:
        """Atomic single-subtask state transition + persist."""
```

**MVP impl note:** `FilesystemPlanStore` writes to `<workspace>/.selffork/plan.json`. The agent (opencode) is told (via the prompt template) where to find this file and how to update it. Updates are atomic via temp-file-then-rename.

---

## 6. Session Lifecycle State Machine

A single `Session` orchestrates one `selffork run` invocation. State transitions are explicit, every transition emits an audit event.

```
                    ┌──────────────────────┐
                    │       IDLE           │  (initial)
                    └─────────┬────────────┘
                              │ run() called
                              ▼
                    ┌──────────────────────┐
                    │      PREPARING       │  (boot runtime + sandbox)
                    └─────────┬────────────┘
                              │ runtime_ready & sandbox_ready
                              │ & agent_spawned
                              ▼
                    ┌──────────────────────┐
                    │       RUNNING        │  (agent working)
                    └─────────┬────────────┘
                              │ agent emitted "done" event
                              ▼
                    ┌──────────────────────┐
                    │      VERIFYING       │  (optional verifier pass)
                    └─────┬────────────┬───┘
                          │            │
                  passed  │            │ rejected/timeout/crash
                          ▼            ▼
                    ┌──────────┐  ┌──────────┐
                    │COMPLETED │  │  FAILED  │
                    └─────┬────┘  └────┬─────┘
                          │            │
                          └─────┬──────┘
                                ▼
                    ┌──────────────────────┐
                    │     TORN_DOWN        │  (terminal)
                    └──────────────────────┘
```

```python
from enum import StrEnum

class SessionState(StrEnum):
    IDLE = "idle"
    PREPARING = "preparing"
    RUNNING = "running"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    TORN_DOWN = "torn_down"
```

**Transition discipline:**
- Every transition is logged as `category="session.state"` audit event with `from`/`to`.
- Failure transitions carry `reason` and `error_class`.
- Teardown is **always called** on session end (try/finally), regardless of state.
- `VERIFYING` is **skippable** in MVP via `LifecycleConfig.skip_verify=True` — RUNNING → COMPLETED directly when agent reports done.
- The verifier itself is a `Verifier` strategy (deferred; MVP ships `NoopVerifier` + `BasicSmokeVerifier` modeled on Codeman's `orchestrator-verifier.ts:65-102` strict/moderate/lenient).

---

## 7. Configuration

**Decision:** Pydantic v2 `BaseSettings` with YAML file + env override + CLI flag override (in that precedence order, last wins).

**File:** `selffork.yaml` at project root (default), overrideable via `--config` CLI flag.

**Env prefix:** `SELFFORK_`, nested via `__`. Example: `SELFFORK_RUNTIME__BACKEND=ollama`.

**Strict mode:** `extra="forbid"` — unknown fields fail validation at boot. No silent typo absorption.

```python
from typing import Literal
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class RuntimeConfig(BaseModel):
    backend: Literal["mlx-server", "ollama", "llama-cpp", "vllm"] = "mlx-server"
    model_id: str = "google/gemma-3-e2b-it-q4_0"
    host: str = "127.0.0.1"
    port: int = Field(default=8001, ge=0, le=65535)  # 0 = auto-allocate
    startup_timeout_seconds: int = Field(default=120, ge=1)
    health_check_interval_seconds: float = Field(default=2.0, gt=0)

class SandboxConfig(BaseModel):
    mode: Literal["subprocess", "docker"] = "subprocess"
    workspace_root: str = "~/.selffork/workspaces"
    docker_image: str = "selffork/opencode-runtime:latest"
    docker_run_extra_args: list[str] = Field(default_factory=list)
    cpu_limit: float | None = None       # cores, None = unlimited
    memory_limit_mb: int | None = None   # MB, None = unlimited
    timeout_seconds: int = Field(default=3600, ge=1)

class CLIAgentConfig(BaseModel):
    agent: Literal["opencode", "claude-code", "codex", "gemini-cli"] = "opencode"
    binary_path: str | None = None       # None = auto-resolve
    extra_args: list[str] = Field(default_factory=list)

class PlanConfig(BaseModel):
    backend: Literal["filesystem", "git"] = "filesystem"
    plan_filename: str = ".selffork/plan.json"

class LifecycleConfig(BaseModel):
    skip_verify: bool = False
    verifier_mode: Literal["strict", "moderate", "lenient", "noop"] = "lenient"

class LoggingConfig(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    json_output: bool = True
    log_dir: str = "~/.selffork/logs"

class AuditConfig(BaseModel):
    enabled: bool = True
    audit_dir: str = "~/.selffork/audit"
    redact_secrets: bool = True

class SelfForkSettings(BaseSettings):
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    cli_agent: CLIAgentConfig = Field(default_factory=CLIAgentConfig)
    plan: PlanConfig = Field(default_factory=PlanConfig)
    lifecycle: LifecycleConfig = Field(default_factory=LifecycleConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)

    model_config = SettingsConfigDict(
        env_prefix="SELFFORK_",
        env_nested_delimiter="__",
        yaml_file="selffork.yaml",
        extra="forbid",
        case_sensitive=False,
    )
```

A fully-commented example `selffork.yaml` ships at repo root (PRD §8.5.1).

---

## 8. Logging

**Decision:** `structlog` with JSON output by default, TTY-pretty in dev mode.

**Every log entry carries:**
- `ts` — ISO 8601 timestamp (UTC)
- `level` — DEBUG/INFO/WARNING/ERROR
- `correlation_id` — ULID per top-level invocation, propagated via `contextvars`
- `session_id` — ULID per Session (= correlation_id today, distinct in M3+ multi-CLI surfing)
- `event` — short snake_case event name
- `payload` — arbitrary structured fields

**No `print()`. No bare `logging.basicConfig`.** `selffork_shared.logging.setup(config)` is the single configuration entry point, called once at CLI startup.

---

## 9. Error Hierarchy

```python
class SelfForkError(Exception):
    """Root for all SelfFork errors."""

class ConfigError(SelfForkError):
    """Configuration is invalid, missing, or contradictory."""

class RuntimeError(SelfForkError):
    """LLM runtime failure umbrella."""

class RuntimeStartError(RuntimeError):
    """Runtime subprocess failed to spawn or never became healthy."""

class RuntimeUnhealthyError(RuntimeError):
    """Runtime stopped responding mid-session."""

class SandboxError(SelfForkError):
    """Sandbox failure umbrella."""

class SandboxSpawnError(SandboxError): ...
class SandboxExecError(SandboxError): ...
class SandboxTeardownError(SandboxError): ...

class AgentError(SelfForkError):
    """CLI agent failure umbrella."""

class AgentBinaryNotFoundError(AgentError): ...
class AgentSpawnError(AgentError): ...
class AgentParseError(AgentError): ...
class AgentTimeoutError(AgentError): ...
class AgentExitError(AgentError):
    """Agent exited with a non-zero code."""

class PlanError(SelfForkError):
    """Plan store failure umbrella."""

class PlanLoadError(PlanError): ...
class PlanSaveError(PlanError): ...
```

Every error message includes enough context to debug without re-running: which subprocess, which path, which exit code, which port. **No raw `raise Exception("...")`** — every raise uses a typed subclass.

---

## 10. Audit Log Format

**File:** `~/.selffork/audit/<session_id>.jsonl`. One JSON object per line.

**Schema (every event):**
```json
{
  "ts": "2026-05-01T10:00:00.123Z",
  "correlation_id": "01HJABCDEFGHIJKLMNOPQRSTUV",
  "session_id": "01HJABCDEFGHIJKLMNOPQRSTUV",
  "category": "session.state",
  "level": "INFO",
  "event": "transition",
  "payload": { "from": "IDLE", "to": "PREPARING" }
}
```

**Categories (closed set, extensible):**

| Category | Emitted by | Payload examples |
|---|---|---|
| `session.state` | `lifecycle.session` | `{from, to, reason?}` |
| `runtime.spawn` | `runtime.<impl>` | `{backend, model, port, pid}` |
| `runtime.health` | `runtime.<impl>` | `{healthy, latency_ms}` |
| `runtime.stop` | `runtime.<impl>` | `{exit_code, signal}` |
| `sandbox.spawn` | `sandbox.<impl>` | `{mode, workspace, container_id?}` |
| `sandbox.exec` | `sandbox.<impl>` | `{command, cwd, pid}` |
| `sandbox.teardown` | `sandbox.<impl>` | `{containers_stopped, processes_killed}` |
| `agent.spawn` | `cli_agent.<impl>` | `{agent, binary, args, env_overrides_keys, pid}` |
| `agent.event` | `cli_agent.<impl>` | `{type, summary}` (raw event truncated/redacted) |
| `agent.done` | `cli_agent.<impl>` | `{duration_seconds, exit_code}` |
| `plan.load` / `plan.save` / `plan.update` | `plan.store_<impl>` | `{path, subtask_id?, state?}` |
| `error` | any | `{class, message, traceback?}` |

**Redaction:** `selffork_shared.audit` strips known secret patterns (API keys, tokens) before write when `audit.redact_secrets=true` (default). Env var values for keys matching `*_KEY|*_TOKEN|*_SECRET` are replaced with `<redacted>`.

---

## 11. Testing Strategy

**Coverage targets:** ≥80% on `packages/orchestrator`, ≥60% on `packages/shared`. Reflex/Body/Mind skeletons exempt (no impl yet).

**Test layout (per package):**
```
tests/
├── unit/                # pure unit tests, no I/O
├── integration/         # spawn real subprocesses, real Docker (if available)
└── e2e/                 # full `selffork run` smoke
```

**MVP done-criterion test:** `tests/e2e/test_selffork_run_smoke.py` runs `selffork run prior art --mode subprocess` end-to-end against a fake/stubbed mlx-server runtime (a tiny FastAPI app emulating the OpenAI /v1/chat/completions surface) and asserts:
- session reaches `COMPLETED` (or `FAILED` only with an explicit, expected reason)
- audit log has all expected categories in order
- plan-doc was updated at least once
- workspace has the agent's output

**Real-runtime tests:** marked `@pytest.mark.real_runtime` and `@pytest.mark.real_docker`, gated by env vars in CI. Always opt-in; default `pytest` run uses fakes.

**Property-based tests** via `hypothesis` for: plan state transitions, port allocator, ULID parsing, config validation.

---

## 12. CI/CD

**`.github/workflows/ci.yml`:**
- Triggers: push, PR.
- Matrix: `[macos-14, ubuntu-22.04]` × `[python-3.12]`.
- Steps: checkout → install uv → `uv sync` → `ruff check` → `ruff format --check` → `mypy --strict packages/` → `pytest` → coverage report.

**`.github/workflows/e2e.yml`:**
- Triggers: push to main, nightly schedule.
- Runs full e2e smoke (subprocess mode on macOS, docker mode on Linux), real backends if available.

**Pre-commit hooks** (`.pre-commit-config.yaml`):
- ruff (check + format)
- mypy (subset, fast)
- typos (typo check)
- trailing-whitespace, end-of-file-fixer

**No `--no-verify` ever** (CLAUDE.md MANDATE 1). Hook failure = real fix, not bypass.

---

## 13. Implementation References

Each MVP component is informed by patterns observed in **prior art in the
agentic-CLI orchestration space** (subprocess sandboxes, opencode-style
CLI runners, plan-as-state launchers, GGUF runtime shells, etc.). The
table below records the *pattern category* and *adoption tier* without
naming specific upstream repositories — concrete attribution is omitted
to keep this ADR self-contained.

| Component | Pattern category | Adoption tier |
|---|---|---|
| Subprocess wrapper (asyncio) | async subprocess + line streaming | LOW (verbatim adapt) |
| Provider env redirect (`OPENAI_BASE_URL` style) | env-injection layer for unattended CLI runs | LOW |
| opencode binary resolution | which/PATH/known-paths fallback chain | LOW (~50 LOC port) |
| CLI args + env builders | composable per-CLI command shape | LOW |
| Session state machine | orchestrator-loop state diagram | MED (adapted to MVP states) |
| Verifier modes (strict/moderate/lenient) | post-run output check tiering | LOW (deferred to noop+basic in MVP) |
| Plan-as-state document model | shared plan file the agent reads + updates | LOW (Pydantic port) |
| Launcher pattern (env owns metadata, agent owns loop) | thin orchestrator over a self-driving CLI | PATTERN-ONLY |
| Subprocess kill (SIGTERM → grace → SIGKILL) | safe child-process lifecycle | LOW |
| Subprocess output cap | bounded buffer to avoid runaway consumers | LOW |
| Background proxy + log-to-file (64KB pipe deadlock fix) | non-blocking subprocess I/O | LOW |
| Free port probe | bind-port-zero allocation | LOW |
| Docker container shape (port maps + bind mounts + env) | sandbox-as-container | PATTERN-ONLY |
| Per-project supervisor (cwd registry + SSE) | multi-project parent process | PATTERN-ONLY (M2+) |
| zsh-safe shell-quote helpers | argv glob escaping | LOW (Python `shlex`) |
| GGUF model catalog | static model-id list with size hints | LOW (Python dict literal) |
| Plan state enum (todo/in_progress/done/abandoned) | sub-task lifecycle | LOW |

**Followup discovery (out of MVP scope, queued for M3+):** several
multi-CLI surfing harnesses surveyed during prior-art reading remain
candidates for the CLI-rotation work in M3 (deterministic-orchestrator,
hierarchical-multi-agent, tmux-multi-CLI, PTY-worktree, multi-tool
launcher patterns). To be re-evaluated when M3 lands.

---

## 14. Alternatives Considered

### 14.1 TypeScript for orchestrator
**Rejected.** mlx-server and mlx-lm are Python-native. Reflex training in M7 is Python (MLX/Unsloth). A TS orchestrator would force a Python subprocess shim for every model interaction and a Python dataset/training pipeline anyway — net result: polyglot toolchain at every pillar boundary, doubled CI matrix, doubled type system, doubled package management.

### 14.2 Python core + TypeScript surfaces (hybrid from day 1)
**Rejected for MVP, accepted for M4.** Cockpit (web/mobile UI) will naturally land in TS at M4. Doing it now adds a second toolchain to a project that has zero UI today. The hybrid is the right end state — but introduced when there's a real surface to write, not preemptively.

### 14.3 Use clippy directly as the local Gemma runtime
**Rejected.** Verified by explorer 3: clippy has **no HTTP API** — it serves the model only via Electron-IPC (`window.electronAi`, `src/renderer/clippyApi.tsx:59-67`). opencode cannot connect to it. clippy's contribution to the runtime layer is zero; only the GGUF catalog and disk layout patterns are useful. We write a thin Python supervisor around mlx-server.

### 14.4 Tmux as the sandbox backbone (amux/Codeman pattern)
**Rejected.** amux (Python+Bash) and Codeman (TS) both use tmux for session lifecycle. For SelfFork's two-mode requirement (Mac subprocess + server Docker), tmux adds a hard dependency without isolation value: subprocess gives us cwd+env scoping for free; Docker gives us container isolation. tmux on top of either is overhead. We keep the option open at the Sandbox-impl level (a future `TmuxSandbox` is a 1-class addition behind the same ABC).

### 14.5 oh-my-codex-style tmux pane keystroke pumping
**Rejected.** Verified: regex on terminal viewport for ready/active/trust prompts is fragile (`oh-my-codex/src/team/tmux-session.ts:1504-1700`). opencode supports a structured stream-json output mode; we use that. Keystroke pumping is only justifiable when the inner agent has no machine-readable output mode.

### 14.6 PraisonAI's process retry/validation loop
**Rejected.** Verified at prior art in the agentic-CLI orchestration space: it re-implements an agent loop. SelfFork's design delegates the loop to opencode. Owning two loops would create contention.

### 14.7 AutoAgent-style XML workflow synthesis
**Rejected.** Verified at prior art in the agentic-CLI orchestration space: a meta-agent designs workflows before running them. Swarm-bloat. opencode is the planner.

### 14.8 Single-file orchestrator (amux pattern)
**Rejected.** amux's `amux-server.py` is a 1MB+ single file. Verified at prior art in the agentic-CLI orchestration space — they explicitly enforce single-file discipline. SelfFork's pillar split (CLAUDE.md MANDATE 7) is the opposite philosophy and the right one for a system that grows into 4 pillars.

### 14.9 Skip stub pillars (orchestrator + shared only)
**Rejected** (per AskUserQuestion answer). Top-level reorg every milestone start is friction we can pay once today.

### 14.10 Drop plan-doc (raw stdout only)
**Rejected** (per AskUserQuestion answer). Plan-doc is the contract Mind/Reflex will read in M2/M7. Adding it post-hoc means rewriting opencode's invocation prompt; cheap to bake in now.

### 14.11 Subprocess-only MVP (defer Docker)
**Rejected** (per AskUserQuestion answer). Docker is the reason the Sandbox interface exists. Both modes ship together so the abstraction has two real implementations from day 1, not one impl + one fiction.

### 14.12 Direct cloud LLM API for the agent (skip local Gemma)
**Rejected.** Contradicts PRD §3.2 Tenet 4 (Local Sovereignty). The entire SelfFork story hinges on local model + local data + local sovereignty. A cloud-API path is what every other coding agent already does; it is not a SelfFork.

---

## 15. Out of Scope for MVP v0

Explicitly deferred to later milestones (per `docs/ROADMAP.md`):

| Capability | Milestone | Why deferred |
|---|---|---|
| Fine-tuning (Reflex pillar) | M7 | "Last mile" per ROADMAP §1.1; behavior emerges later. |
| Cockpit web UI | M4 | Backend-first per `feedback_backend_first.md`. |
| Mobile companion app | M4+ | Cockpit-derived. |
| Multi-CLI surfing (Gemini ↔ Claude ↔ OpenCode rotation) | M3 | One CLI works first. |
| Cron sleep on rate limit + Telegram payload | M3 | Surfing-dependent. |
| SSH deploy to PROD | M3 | Surfing-dependent. |
| Body pillar (vision, mobile/web/desktop control) | M5 | Separate pipeline. |
| Mind pillar (RAG, GraphRAG, memory tiers, historian) | M2 | Separate pipeline. |
| Hot-swappable adapters | M9 | Reflex-dependent. |
| Multi-project supervisor (>1 concurrent project) | M3 | Interface ready (`Supervisor` class), single-project today. |
| Persistent session continuity beyond audit log | M2 with Mind | Mind-dependent. |
| Verifier modes beyond noop+basic | M1+ | Codeman pattern referenced; full strict/moderate/lenient later. |
| Authentication / multi-tenancy | M4 | Surface-dependent. |

---

## 16. Definition of Done — MVP v0

Concrete, machine-verifiable checklist. Code is not "done" until every item passes.

### 16.1 Functional

- [ ] `selffork run <prd-path>` (default `--mode subprocess`) on macOS Apple Silicon produces a working project from a PRD that exercises ≥3 SubTasks.
- [ ] `selffork run <prd-path> --mode docker` on a Linux server (Ubuntu 22.04 reference) runs end-to-end, container is auto-removed on completion.
- [ ] mlx-server backend loads `gemma-3-e2b-it-q4_0`, exposes `/v1/chat/completions`, opencode connects via env-injected base URL.
- [ ] `<workspace>/.selffork/plan.json` is updated by opencode at least once during the session.
- [ ] `~/.selffork/audit/<session_id>.jsonl` exists, contains all expected categories in order, secrets are redacted.
- [ ] Session reaches `COMPLETED` on the happy path; reaches `FAILED` cleanly with a typed error and teardown completed on every failure mode tested.

### 16.2 Code quality

- [ ] `mypy --strict` passes on all 5 packages.
- [ ] `ruff check` and `ruff format --check` pass.
- [ ] `pytest` passes; coverage ≥80% on orchestrator, ≥60% on shared.
- [ ] No `print()` calls anywhere in `packages/`. No bare `Exception` raises. No untyped public functions.
- [ ] Every public class and function has a docstring (Google style).
- [ ] `pre-commit run --all-files` clean.

### 16.3 Architecture

- [ ] All 4 ABCs (`LLMRuntime`, `Sandbox`, `CLIAgent`, `PlanStore`) defined with full method signatures and docstrings.
- [ ] At least 1 implementation per ABC works; all other implementations stubbed with `NotImplementedError("Planned: M<x>. See ADR-001 §15.")`.
- [ ] Reflex / Body / Mind packages exist with `__init__.py`, `README.md`, and TODO docstrings; no implementation code yet.
- [ ] No cross-pillar imports outside `packages/shared` (verified by import-linter rule).
- [ ] State machine (Bölüm 6) implemented; every transition emits an audit event.

### 16.4 Tooling

- [ ] `pyproject.toml` workspace at repo root resolves all 5 packages via `uv sync`.
- [ ] `selffork.yaml` example with comments at repo root.
- [ ] CI green on macOS-14 and Ubuntu-22.04.
- [ ] E2E smoke (subprocess mode) runs on every PR.
- [ ] `infra/docker/opencode-runtime/Dockerfile` builds, image runs, opencode + mlx-server reachable.

### 16.5 Documentation

- [ ] README per package (orchestrator, shared, reflex, body, mind), each ~50–150 lines.
- [ ] Repo-root README updated with MVP v0 quickstart (≥3 commands to run).
- [ ] ADR-001 (this file) referenced from PRD and ROADMAP.
- [ ] `docs/decisions/` ADR template added for future ADRs.

---

## 17. Approval Gate

This ADR is **Accepted** when the following named decision-holder confirms:

> ☐ **the project owner** — primary decision-holder. Confirms scope, language, layout, interfaces, Done criteria.

After approval, implementation proceeds in the order:

1. Workspace bootstrap: `pyproject.toml`, `uv` workspace, `pre-commit`, CI skeleton.
2. `packages/shared`: config, logging, errors, audit, ports, ulid, shellquote.
3. `packages/orchestrator/runtime/`: ABC + `MlxServerRuntime` + 3 stubs.
4. `packages/orchestrator/sandbox/`: ABC + `SubprocessSandbox` + `DockerSandbox`.
5. `packages/orchestrator/cli_agent/`: ABC + `OpenCodeAgent` + 3 stubs + events model.
6. `packages/orchestrator/plan/`: model + ABC + `FilesystemPlanStore`.
7. `packages/orchestrator/lifecycle/`: state machine + Session class.
8. `packages/orchestrator/cli.py`: `selffork` Typer entrypoint.
9. `infra/docker/opencode-runtime/`: Dockerfile + entrypoint.
10. Reflex / Body / Mind skeletons.
11. E2E smoke test + GH Actions workflows.
12. READMEs + repo-root quickstart.

Each step is a separate commit (or small PR series), each independently green on CI. No "big bang" merge. No `--no-verify`. No bypass.

---

*End of ADR-001.*
