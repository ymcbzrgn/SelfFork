# S-Train Smoke Checklist

> **Gate:** All items PASS → S-Train ACCEPTED → M7 (training worker) may open.
> Reference: [`ADR-012`](../decisions/ADR-012_S-Train_Corpus.md),
> [`S-Train_Plan.md`](./S-Train_Plan.md).

Every item is verified with `uv run --frozen pytest <files>` (no app, no GPU, no
`lancedb`).

## Corpus pipeline

- [ ] **T1 Normalizer:** a synthetic session JSONL → session-aware chat sample
      with the correct loss mask (agent/tool = 0.0, prior operator = 0.3, target
      = 1.0). Failure path: malformed session line skipped, not crashed.
- [ ] **T2 Assembler:** multi-session input → one sample per operator turn, full
      session prefix as context, target = that operator message. Source
      precedence (Claude Code/OpenCode primary) honored.
- [ ] **T3 Correction quality:** zero corrections → unchanged SM-2 quality
      (backward-compat); N corrections on a pattern → proportionally lower
      quality, clamped to floor.
- [ ] **T4 `selffork train --dataset auto`:** writes a schema-valid corpus
      artifact to a tmp path; prints count + path; no weights written.
- [ ] **T5 Validator:** accepts a valid corpus; **rejects** a deliberately
      corrupted one (bad loss mask / missing source / schema drift); flags
      agentic-trace-length distribution vs the ADR-010 §2.3 30+-tools target.

## Wire-contract integrity (Format Freeze)

- [ ] Corpus emits LegalAction Turkish strings + tool names / `action_type`
      verbatim (no renames vs ADR-010 §5).
- [ ] `Correction` fields consumed exactly: `audit_idempotency_key`,
      `correction_text`, `suggested_action`, `corrected_at`, `source`.
- [ ] System prompt string matches `Operator_Locked_Decisions.md` §2.

## Ecosystem

- [ ] **T6 Publishing:** BEGIN/END Mind-access block upserts idempotently into
      AGENTS.md/CLAUDE.md/GEMINI.md/AGENT.md (re-run is byte-identical).

## Scope guard (must remain TRUE)

- [ ] No GPU/QLoRA/MLX training code landed; `packages/reflex/{training,adapter,eval}/`
      are still skeletons. (That is M7, not S-Train.)
