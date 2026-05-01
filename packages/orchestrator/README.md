# selffork-orchestrator

The Orchestrator pillar — MVP v0's home. Implements the four pluggable
contracts and the `selffork` CLI.

See [ADR-001](../../docs/decisions/ADR-001_MVP_v0.md) for the full architecture.

## Modules

| Module | Status | Purpose |
|---|---|---|
| `runtime/` | ✅ MVP | `LLMRuntime` ABC + `MlxServerRuntime` (default) + ollama / llama-cpp / vllm stubs |
| `sandbox/` | ✅ MVP | `Sandbox` + `SandboxProcess` ABCs + `SubprocessSandbox` (Mac dev) + `DockerSandbox` (server) |
| `cli_agent/` | ✅ MVP | `CLIAgent` ABC + `OpenCodeAgent` + claude-code / codex / gemini-cli stubs + typed `AgentEvent` union |
| `plan/` | ✅ MVP | `Plan` / `SubTask` Pydantic models + `PlanStore` ABC + `FilesystemPlanStore` (atomic JSON) + git stub |
| `lifecycle/` | ✅ MVP | `SessionState` enum + transition table + `Session` orchestrator |
| `cli.py` | ✅ MVP | `selffork run <prd>` Typer entrypoint |

## Lifecycle

```
IDLE → PREPARING → RUNNING → VERIFYING → COMPLETED  ┐
                          ↘             ↘           ├→ TORN_DOWN
                            FAILED ──────────────── ┘
```

Every state transition emits a `session.state` audit event; every
collaborator step emits its own `runtime.*` / `sandbox.*` / `agent.*` /
`plan.*` event. Teardown always runs (try/finally) — runtime processes
and sandbox containers never leak.

## Quick links

- Architecture: [`docs/decisions/ADR-001_MVP_v0.md`](../../docs/decisions/ADR-001_MVP_v0.md)
- Locked fine-tune decisions: [`docs/Operator_Locked_Decisions.md`](../../docs/Operator_Locked_Decisions.md)
- Bigger vision: [`docs/PRD.md`](../../docs/PRD.md), [`docs/ROADMAP.md`](../../docs/ROADMAP.md)
