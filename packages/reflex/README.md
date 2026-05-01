# selffork-reflex

**Status:** Skeleton — implementation lands in **M7 (LAST MILE)** per `docs/ROADMAP.md`.

This package exists from day 1 to lock the SelfFork monorepo shape (per [ADR-001 §4 and §14.9](../../docs/decisions/ADR-001_MVP_v0.md)). Importing it today returns a version string and an empty namespace.

## Sub-packages (planned)

| Sub-package | Purpose | Lands |
|---|---|---|
| `data/` | Normalize Claude Code + OpenCode + ChatGPT exports → session-aware chat | M7 |
| `training/` | MLX or Unsloth adapter training with user-only weighted loss | M7 |
| `eval/` | Held-out operator session behavior diff | M7 |
| `adapter/` | Adapter packaging, versioning, hot-swap | M7-M9 |

## Locked decisions

See [`docs/Operator_Locked_Decisions.md`](../../docs/Operator_Locked_Decisions.md) for the full set:

- Base: Gemma 4 E2B-it Q4_0
- Context: 128K
- Adapter, not full fine-tune
- Session-aware chat format
- user-only weighted loss (1.0 last / 0.3 prev / 0.0 agent+tool)
- Sources: Claude Code + OpenCode primary, ChatGPT/Claude ARGE secondary
