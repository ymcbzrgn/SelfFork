# Operator Locked Decisions — Reflex fine-tune

> **Status:** Locked. This is the consolidated, English-language surface of the
> operator's locked fine-tune decisions. The historical source-of-truth (with
> the full deliberation, in Turkish) is
> [`docs/archive/Yamac_Jr_Nano_Kararlar.md`](archive/Yamac_Jr_Nano_Kararlar.md).
> Referenced by `packages/reflex/` (README + `data/`), `packages/orchestrator/README.md`,
> and [`ADR-001`](decisions/ADR-001_MVP_v0.md). Consumed by the S-Train sprint —
> see [`ADR-012`](decisions/ADR-012_S-Train_Corpus.md) and
> [`docs/plans/S-Train_Plan.md`](plans/S-Train_Plan.md).

These decisions are **frozen inputs** to the M7 Reflex fine-tune. Changing any
of them invalidates accumulated corpus assumptions, so treat them like the
ADR-010 Format Freeze: additive clarification is fine, a breaking change is a
retraining event.

## 1. Model + adapter

| Decision | Value |
|---|---|
| Base model | Gemma 4 E2B-it Q4_0 |
| Context window | 128K |
| Method | **Adapter (QLoRA), not full fine-tune** |
| Timing | Fine-tune is the **LAST mile** — deferred to M7. Stock Gemma carries M0-M6. |

## 2. Dataset format

- **Session-aware chat format.** Every training example is produced inside its
  own session context (not flattened turn pairs).
- **Context strategy:** full session prefix as context.
- **Target:** the operator's (Yamaç's) *actual next message* — only the
  operator's own messages are targets.
- **System prompt (canonical):**
  `You are Yamaç Jr. Nano. Your task is to predict how Yamaç would respond in this situation.`

## 3. Loss — Yamaç-only weighted loss (hybrid)

Per-token loss weights over the session-aware chat sample:

| Message kind | Weight |
|---|---|
| Agent / assistant / Claude Code / OpenCode messages | 0.0 |
| Tool result / terminal output / repo context | 0.0 |
| Previous Yamaç (operator) messages in the prefix | 0.3 |
| Final target Yamaç (operator) message | 1.0 |

The hybrid (0.3 on prior operator messages, not 0.0) was the locked compromise:
it teaches the operator's *voice* across the whole session without letting the
prefix dominate the single target message.

## 4. Data sources

- **Primary:** Claude Code session JSONL + OpenCode export.
- **Secondary:** ChatGPT export + Claude.ai ARGE history.
- **Auto-built corpus tier:** Mind **T4 Procedural** is the fine-tune corpus that
  auto-builds distilled patterns ([`ADR-002`](decisions/ADR-002_Mind_Architecture.md) §
  "T4 Procedural is the fine-tune corpus").
- **Agentic-trace requirement:** the corpus MUST contain long multi-tool agentic
  traces (30+ tools/session) so Self Jr learns *when* to plan vs act
  ([`ADR-010`](decisions/ADR-010_Vision_Lock.md) §2.3).
- **Coaching stream:** the operator's `corrections.jsonl`
  (`heartbeat/audit.py::Correction`, frozen fields `audit_idempotency_key`,
  `correction_text`, `suggested_action`, `corrected_at`, `source`) is a
  high-signal corpus input.

## 5. Volume + quality gate

- Target volume: **~8,000-12,000 reviewed and CoT-distilled samples** (PRD §
  "Behavioral fine-tuning") before an adapter is produced.
- Reviewed + distilled, not raw — quality before volume.

## 6. Scope boundary (what S-Train is NOT)

S-Train assembles + stabilizes the **corpus** on the ADR-010 Format Freeze. It
does **not** ship the GPU/QLoRA training worker — that is the M7 Reflex pillar
proper. See [`ADR-012`](decisions/ADR-012_S-Train_Corpus.md) for the exact split.
