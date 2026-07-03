# ADR-012 — S-Train: Fine-tune Corpus Assembly + Stabilization

## Status

- **Status:** Proposed (2026-07-02). Authored as the process gate for the
  project's declared next milestone (ADR-010 §9.17: "Next milestone: M7 freeze
  ... plus the S-Train sprint that uses the Format Freeze as the fine-tune corpus
  stabilization gate").
- **Type:** Architecture ADR — defines the scope + wire contracts of the S-Train
  sprint. No new pillar; it wires existing Mind/Orchestrator/Reflex surfaces into
  a corpus pipeline.
- **Builds on:**
  - [`ADR-002`](./ADR-002_Mind_Architecture.md) — T4 Procedural is the auto-built
    fine-tune corpus; Order 6 = Mind → Reflex bridge.
  - [`ADR-010`](./ADR-010_Vision_Lock.md) — §2.3 (agentic-trace corpus
    requirement), §5 + §9.7/9.10/9.13/9.16 (Format Freeze = the stabilization
    gate), §9.17 (S-Train named as next).
  - [`docs/Operator_Locked_Decisions.md`](../Operator_Locked_Decisions.md) —
    locked model/format/loss/sources.

## 1. Context

M6 Wave 2 + the seven follow-up sprints (S-Auto → S-ToolFleet) are code-complete;
the 289-tool fleet's wire surfaces are frozen (ADR-010 §5). The project's own
roadmap declares **S-Train → M7** as the remaining path. Yet S-Train had **zero
artifacts** — no ADR, no plan, and `selffork train` only prints a dry plan.

The Reflex pillar (`packages/reflex/`) is still a skeleton whose own docstrings
promise a data pipeline "per `docs/Operator_Locked_Decisions.md`" — a file that
did not exist until this ADR's companion commit created it. So the first job of
S-Train is to make the *corpus* real, on the frozen wire contracts, **without**
committing to GPU training work (that stays M7).

## 2. Decision — the scope split

S-Train owns **corpus assembly + stabilization only**:

**IN scope (S-Train):**
1. **Session-capture normalizer** (`packages/reflex/src/selffork_reflex/data/`) —
   turn raw session material into the locked session-aware chat format with the
   Yamaç-only weighted-loss mask (0.0 agent/tool, 0.3 prior operator, 1.0 target).
2. **Corpus assembler** — full-session-prefix samples, target = operator's next
   message, honoring the source precedence in
   [`Operator_Locked_Decisions.md`](../Operator_Locked_Decisions.md) §4.
3. **Correction-quality signal** — operator `corrections.jsonl` frequency
   modulates the SM-2 quality on exported T4 items (ADR-010's named deferred
   Order-6 piece), so over-corrected patterns surface for review instead of
   looking "perfect". *(Landed 2026-07-02 in `bridge/exporter.py`.)*
4. **`selffork train --dataset auto`** — actually assemble + write a corpus
   artifact (count, path, format-validation) instead of echoing a string. Still
   no weights, no GPU.
5. **Corpus validation gate** — a deterministic validator (schema, loss-mask
   integrity, agentic-trace-length distribution per ADR-010 §2.3, source
   attribution) that fails loudly, runnable in CI with no model.

**OUT of scope (stays M7 Reflex pillar proper):**
- The QLoRA/MLX/Unsloth training worker, GPU orchestration, adapter packaging,
  hot-swap, and held-out behavioral eval. `packages/reflex/{training,adapter,eval}/`
  stay skeletons until M7.

## 3. Frozen inputs (do not break)

- Model/format/loss/sources: [`Operator_Locked_Decisions.md`](../Operator_Locked_Decisions.md).
- `Correction` JSONL schema (ADR-010 §5): `audit_idempotency_key`,
  `correction_text`, `suggested_action`, `corrected_at`, `source`.
- LegalAction Turkish strings + the 289-tool names / `action_type` taxonomy
  (ADR-010 §5) — the corpus emits these literally; renames = retraining.
- System prompt string (Operator_Locked_Decisions §2).

## 4. Consequences

- Gives every S-Train code work-item an operator-approved scope boundary before
  implementation (the repo convention: an ADR/plan precedes a sprint).
- Fixes a 5-way dangling reference (`Operator_Locked_Decisions.md` was cited by
  ADR-001, both package READMEs, and `reflex/{__init__,data/__init__}.py` but
  never existed).
- Keeps the risky/expensive GPU work out of the no-local-run window; everything
  in §2 IN-scope is pure data-pipeline code, offline-testable.

## 5. Smoke gate

S-Train closes when `docs/plans/S-Train_Smoke_Checklist.md` passes: the
normalizer + assembler produce a schema-valid corpus from synthetic sessions
with a correct loss mask, `selffork train --dataset auto` writes a validated
artifact, and the validator rejects a deliberately-corrupted corpus. Then M7
(the training worker) may open.

## 6. Update (2026-07-03) — synthetic tool-mastery corpus

§2 items 1–5 all landed and were committed. In execution, one reality reshaped
the corpus source: the operator has **never run SelfFork**, so the T1/T2
real-session harvest has nothing to ingest yet. The corpus that will actually
feed M7 is therefore **teacher-authored and 100% synthetic**, generated under
`packages/orchestrator/src/selffork_orchestrator/corpus/` and validated against
the *real* 289-tool registry (`spec.args_model.model_validate` + strict-args +
the T5 loss-mask check) so no invalid call can enter.

This does **not** change this ADR's scope split — it is still corpus assembly
only; GPU/QLoRA/adapter/eval stay M7. It records where the corpus *content* comes
from while real data is absent. See:

- [`docs/plans/S-Train_Corpus_Authoring.md`](../plans/S-Train_Corpus_Authoring.md)
  — authoring roadmap (20 domains / 4 phases / ~15k target / mixed-model policy)
  + hard-won operational lessons.
- [`packages/orchestrator/.../corpus/README.md`](../../packages/orchestrator/src/selffork_orchestrator/corpus/README.md)
  — architecture, the validation gate, wire format, loss mask, file map.

The operator-voice track (real external transcripts, Operator_Locked_Decisions
§4 precedence) remains the *later* corpus, exactly as §2 intended.
