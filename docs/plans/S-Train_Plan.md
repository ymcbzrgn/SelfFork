# S-Train — Fine-tune Corpus Sprint Plan

> **Status:** Active (opened 2026-07-02).
> **Reference ADR:** [`ADR-012`](../decisions/ADR-012_S-Train_Corpus.md).
> **Locked inputs:** [`Operator_Locked_Decisions.md`](../Operator_Locked_Decisions.md).

Executable counterpart to ADR-012. S-Train makes the fine-tune **corpus** real on
the frozen wire contracts. It does **not** ship the GPU training worker (M7).

## Work items

| # | Item | Site | Verify (offline) | Status |
|---|---|---|---|---|
| **T1** | Session-capture **normalizer** — raw session JSONL → session-aware chat sample with the Yamaç-only loss mask (0.0 agent/tool, 0.3 prior operator, 1.0 target) | `packages/reflex/src/selffork_reflex/data/` (reuse `selffork_shared.audit_reader` + `dashboard/audit_reader.py`) | `uv run --frozen pytest packages/reflex/tests/ -q` (synthetic session fixtures) | ⬜ next |
| **T2** | **Corpus assembler** — full-session-prefix samples, target = operator's next message, source precedence per Locked Decisions §4 | `packages/reflex/src/selffork_reflex/data/` | pytest on synthetic multi-session input | ⬜ |
| **T3** | **Correction-quality signal** — `corrections.jsonl` frequency modulates SM-2 quality on exported T4 items (ADR-010 deferred Order-6 piece) | `packages/mind/src/selffork_mind/bridge/exporter.py` + `ingest/heartbeat.py` | `pytest packages/mind/tests/test_bridge.py test_ingest_corrections.py` | 🟡 in progress (2026-07-02) |
| **T4** | **`selffork train --dataset auto`** actually assembles + writes a validated corpus artifact (no GPU) | `packages/orchestrator/.../cli.py` train cmd + `cli_mind.py` export path | `pytest packages/orchestrator/tests/test_cli_train.py` (typer CliRunner + tmp_path) | ⬜ |
| **T5** | **Corpus validator** — schema, loss-mask integrity, agentic-trace-length distribution (ADR-010 §2.3, 30+ tools/session), source attribution; CI-runnable, no model | `packages/reflex/src/selffork_reflex/data/` + a CI hook | `pytest` on valid + deliberately-corrupted corpora | ⬜ |
| **T6** | **AGENTS.md/CLAUDE.md publishing** (ADR-009 §9 / ADR-002 §13) so external CLIs discover Mind access | `packages/mind/src/selffork_mind/publishing/` | `pytest packages/mind/tests/test_publishing.py` | 🟡 in progress (2026-07-02) |

> T3 + T6 are being implemented as offline-verifiable pieces in the 2026-07-02
> autonomous batch; T1/T2/T4/T5 follow. T1 depends on `audit_reader` (tests added
> 2026-07-02) since the normalizer reuses its session-JSONL parsing.

## Scope guard

Anything touching GPU/QLoRA/MLX training, adapter packaging, hot-swap, or held-out
behavioral eval is **M7**, not S-Train. `packages/reflex/{training,adapter,eval}/`
stay skeletons.

## Test posture

Every item lands with >=1 happy-path + >=1 failure-path test, run with
`uv run --frozen pytest <files>` (always `--frozen`). No item requires the app,
a GPU, or `lancedb` (Windows dev box has no lancedb wheel) — corpus code is pure
data-pipeline. Frontend/dev-server are not involved.
