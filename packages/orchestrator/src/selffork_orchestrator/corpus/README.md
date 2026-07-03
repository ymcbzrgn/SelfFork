# `corpus/` — Synthetic Tool-Mastery Corpus

This package builds the **synthetic fine-tune corpus that teaches the tiny (2B)
Reflex model to drive SelfFork's own 289-tool fleet + 10 LegalActions**. It is
the concrete, generation-side complement to the [S-Train](../../../../../docs/plans/S-Train_Plan.md)
reflex data-pipeline: where `packages/reflex/.../data/` *harvests* real operator
sessions, this package *authors* correct examples from scratch.

> **Why synthetic?** The operator has **never run SelfFork**, so there is **zero
> real usage data** to harvest. The stock model does general tool-calling but
> fails on SelfFork's specific surface (~20% success). This corpus closes that
> gap by construction. Full plan + roadmap:
> [`docs/plans/S-Train_Corpus_Authoring.md`](../../../../../docs/plans/S-Train_Corpus_Authoring.md).

## The one invariant (why this can't drift)

**Every sample — regardless of which model authored it — is validated against the
*real registry* before it can enter the corpus.** The runtime accepts a tool call
iff `spec.args_model.model_validate(args)` (pydantic) passes and the wire block
parses. `validator.py` runs that **exact** check. A malformed name, a wrong arg,
a non-schema key, a broken wire format → **rejected, never learned**.

This invariant is what makes a *mixed-model* authoring strategy safe: Fable,
Opus, Sonnet, even Haiku can all author, because none of them can smuggle an
invalid call past the gate. Reasoning quality (not format) is the only residual
risk, and that is covered by a human/Opus judgment scan per bank.

## Wire format & loss mask

Target text the model learns to emit (canonical, one line, `ensure_ascii=False`):

```
<selffork-tool-call>
{"tool": "<name>", "args": {...}}
</selffork-tool-call>
```

Each corpus **row** is a chat sample with the locked Yamaç-only weighted-loss
mask (identical to reflex T1/T5):

| message | weight |
|---|---|
| system prompt | `0.0` |
| context / prior tool results | `0.0` |
| prior operator turns (agentic prefix) | `0.3` |
| **the target reply under training** | **`1.0`** (last message) |

An **agentic trajectory** emits **one row per step** over a growing prefix, so a
multi-tool chain ("önce X → gör sonucu → sonra Y") teaches each decision in
context. See `builder.build_trajectories`.

## Three layers

| Layer | Module | ~Count | Teaches |
|---|---|---|---|
| **Mechanical backbone** | `mechanical.py` | 313 | Every tool's exact name / args / format (drill). 276/289 tools + enum sweeps. |
| **Single-call reasoning** | `authored/*.py` (non-trajectory) | 310 | Judgment: tool-vs-tool disambiguation, arg-value choice, intent-vs-literal-words. |
| **Agentic trajectories** | `authored/trajectories_*.py` | 351 | Multi-step chains, act→observe→act, error recovery, cross-domain handoffs, low-context survival. |

Total as of 2026-07-03 (commit `981a7fd`): **974 gated samples, 289/289 tools
covered, 0 rejected, reflex-T5 valid, 29 corpus tests green.**

## File map

```
corpus/
├── validator.py     THE GATE. validate_tool_call / validate_reply /
│                    validate_legal_action / default_registry (cached).
│                    strict_args=True flags any non-schema arg.
├── render.py        Canonical renderer. render_tool_call (tool-before-args,
│                    one-line JSON) / render_target (lean = block only;
│                    reasoning = short justification text + block).
├── spec_cards.py    extract_spec_cards() → SpecCard/ArgField for all 289 tools;
│                    synthesize_args(card) auto-fills valid args (276/289).
├── mechanical.py    mechanical_scenarios() → the 313-scenario drill backbone.
├── builder.py       ToolScenario / build_corpus / corpus_stats (single-call);
│                    AgenticStep / AgenticTrajectory / build_trajectories /
│                    trajectory_stats (chains). Renders + GATES every row.
├── assemble.py      FREEZE TOOL. assemble_corpus_rows() gathers mechanical +
│                    ALL_SCENARIOS + ALL_TRAJECTORIES → one gated + T5-validated
│                    JSONL. CLI: python -m selffork_orchestrator.corpus.assemble
│                    --out <path>.  DO NOT run until operator says "dondur".
└── authored/
    ├── __init__.py            Aggregates ALL_SCENARIOS + ALL_TRAJECTORIES.
    ├── kanban.py              single-call banks ↓
    ├── android_lifecycle.py
    ├── phones.py / phones_deep.py
    ├── browser.py / browser_workflow_deep.py
    ├── xr_native.py
    ├── workflow_control.py
    ├── complex_tools.py
    ├── memory_context.py      (+ mind_note_add/recall/compact/session_state)
    ├── trajectories_mobile.py     agentic trajectory banks ↓
    ├── trajectories_device.py
    ├── trajectories_workflow.py
    ├── trajectories_recovery.py
    └── trajectories_crossdomain.py
```

Tests: `packages/orchestrator/tests/corpus/{test_validator,test_builder,test_trajectory,test_assemble}.py`.

## Adding a bank (the authoring loop)

1. Create `authored/<domain>.py` exposing `SCENARIOS: list[ToolScenario]`
   (or `TRAJECTORIES: list[AgenticTrajectory]`). Give each a real situation
   (`context`), the correct call (`tool` + `args`), and — for judgment cases —
   a 1-2 sentence `reasoning` (why this tool, not the near-miss).
2. **Self-gate** while authoring:
   ```bash
   uv run --frozen python -c "from selffork_orchestrator.corpus.builder import build_corpus; from selffork_orchestrator.corpus.authored.<domain> import SCENARIOS; r=build_corpus(SCENARIOS); print(r.stats)"  # expect 0 rejected
   uv run --frozen ruff check <file> && uv run --frozen mypy <file>
   ```
3. Register the bank in `authored/__init__.py` (`ALL_SCENARIOS` / `ALL_TRAJECTORIES`).
4. Re-verify: `uv run --frozen pytest packages/orchestrator/tests/corpus/ -q`.
5. Reasoning/flow scan (human or Opus): confirm no example teaches a wrong
   heuristic. The gate guarantees *format*; only review guarantees *judgment*.

Always `uv run --frozen` (this dev box's env is frozen; see
[`selffork-weak-windows-machine`] note in project memory).

## Freeze (M7 hand-off)

When the operator says **"dondur"**, run the assembler to emit the training
JSONL, then M7's GPU worker consumes it:

```bash
uv run --frozen python -m selffork_orchestrator.corpus.assemble --out ~/.selffork/reflex/corpus/tool_mastery_corpus.jsonl
```

Until then the corpus keeps growing — variety and volume are the levers
(["ne kadar çok/çeşit o kadar iyi"]). GPU/QLoRA/adapter work stays **M7**, out of
scope here (same boundary as [ADR-012](../../../../../docs/decisions/ADR-012_S-Train_Corpus.md) §2).
