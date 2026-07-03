# S-Train — Synthetic Tool-Mastery Corpus: Authoring Roadmap & Playbook

> **Status:** Active (opened 2026-07-03).
> **Reference ADR:** [`ADR-012`](../decisions/ADR-012_S-Train_Corpus.md) (scope lock).
> **Code + architecture:** [`packages/orchestrator/.../corpus/README.md`](../../packages/orchestrator/src/selffork_orchestrator/corpus/README.md).
> **Locked inputs:** [`Operator_Locked_Decisions.md`](../Operator_Locked_Decisions.md).

This is the **generation-side** companion to [`S-Train_Plan.md`](./S-Train_Plan.md).
`S-Train_Plan.md`'s T1–T6 build the pipeline that *harvests real sessions*; this
document is the plan for *authoring the synthetic corpus* that will actually feed
M7 — because there is no real data to harvest yet.

---

## 1. Why this track exists

The operator has **never run SelfFork** → **zero real usage/audit data**. The
reflex T1/T2 real-session harvest is correct plumbing but currently has nothing
to eat. Meanwhile the tiny (2B) Reflex model must drive SelfFork's **289 tools +
10 LegalActions** near-perfectly; the stock model manages only ~20% on this
specific surface. So the corpus is **100% synthetic and teacher-authored**.

**Corpus purity is the lever.** A tiny model memorizes every error, so every
example must be near-100% correct. Two mechanisms guarantee that:

1. **The gate (format correctness, absolute).** Every sample passes the *real
   registry* validation — `spec.args_model.model_validate(args)` + wire-format
   parse + `strict_args` — exactly what the live runtime does. Invalid calls
   cannot enter. This is why *mixed-model* authoring is safe (see §5).
2. **The judgment scan (reasoning correctness, human/Opus).** The gate can't
   tell a *plausible-but-wrong* tool choice from a right one. So every authored
   bank gets an Opus (main-loop) judgment/flow re-scan before it lands.

Full architecture, wire format, and the loss mask live in the
[corpus README](../../packages/orchestrator/src/selffork_orchestrator/corpus/README.md).

---

## 2. Current state (2026-07-03, commit `981a7fd`)

**974 gated samples · 289/289 tools covered · 0 rejected · reflex-T5 valid · 29
corpus tests green.** All committed to `main` by the operator.

| Layer | Count | Where |
|---|---|---|
| Mechanical backbone (drill) | 313 | `mechanical.py` (276 tools + enum sweeps) |
| Single-call reasoning (judgment) | 310 | `authored/*.py` non-trajectory banks |
| Agentic trajectories (chains) | 351 | `authored/trajectories_*.py` |

Rounds 1–3 delivered: mobile/browser/xr/workflow single-call banks, memory/context
(low-context survival), device/workflow/recovery/cross-domain trajectory banks,
and Opus-authored deep banks (`phones_deep`, `browser_workflow_deep`).

---

## 3. The roadmap — 20 domains / 4 active phases

**Target: ~15k+ samples** (operator chose aggressive over the ADR-010 §2.3 /
ADR-012 §5 8–12k band). **Start style: mixed-parallel** — one Fable decision-bank
+ one non-Fable depth-bank at a time, main-loop Opus authoring/verifying alongside.

### Phase 4 — Decision Layer (Fable; highest-cost-if-wrong, currently thinnest)
The 2B's *top-level* choice — which LegalAction *before* any tool call — is barely
covered and most expensive to get wrong.

| # | Domain | Layer | Model | ~n | Status |
|---|---|---|---|---|---|
| D1 | **LegalAction decision** (10 labels: task_başlat / session_devam / cli_seç / kanban_task_öner / operatöre_sor / fikirleş / uzvunu_kullan / uzvunu_incele / bekle / kendini_durdur) | meta-decision | **Fable** | 180 | 🆕 |
| D2 | **Safety / refusal / escalation** (when to ask, when to stop, when to refuse) | meta-decision | **Fable** | 140 | 🆕 |
| D3 | Memory / context survival — deepen | meta | **Fable** | +150 | extend |
| D4 | Kanban + LegalAction trajectories | chain | Fable/Opus | 200 | extend |

### Phase 5 — Tool Depth (mixed Sonnet/Opus; XR-safety = Fable)
| # | Domain | Model | ~n |
|---|---|---|---|
| D5 | iOS deep (lifecycle/push/appearance/statusbar/record/biometric) | **Opus** | 180 |
| D6 | Android input / observe / gesture deep | **Sonnet** | 160 |
| D7 | Android system (shell/intent/dumpsys/property/file) deep | Sonnet/Opus | 160 |
| D8 | Browser interaction levels (click/act/agent/fill/select) | **Sonnet** | 160 |
| D9 | Browser net/state/emulate (mock/intercept/proxy/geo/locale) | **Opus** | 170 |
| D10 | Browser extract/capture/evaluate/smart_locator | **Sonnet** | 150 |
| D11 | XR deep + **Guardian safety** | Fable(safety)+Sonnet | 160 |
| D12 | Dev/build (expo/eas/skills/github) deep | **Opus** | 170 |
| D13 | UI-verify + crash/state (assert/color/snapshot/restore) | Sonnet | 140 |

### Phase 6 — Trajectory Expansion (Fable + Opus)
| # | Domain | Model | ~n |
|---|---|---|---|
| D14 | Device trajectories — new archetypes | **Opus** | 250 |
| D15 | Workflow trajectories — new archetypes | **Opus** | 250 |
| D16 | Recovery trajectories — branching / multi-failure | **Fable** | 250 |
| D17 | **Long-horizon / memory-woven** (compact mid-flow, recall back) | **Fable** | 200 | 🆕 |
| D18 | **Full heartbeat loop** (LegalAction → act → observe → LegalAction) | **Fable** | 250 | 🆕 |

### Phase 7 — Volume & Variety (cheap: Haiku/Sonnet, high throughput → ~10-11k)
Take already-gated correct calls and multiply the *operator phrasing / context*
around them — the tiny model generalizes across how the same intent is expressed.
Cheapest, highest-volume lever. **Orchestrate via the `Workflow` tool** (each
workflow agent is a leaf — respects the no-nested-subagents rule). Opus samples +
scans Haiku output for unnatural phrasing before it lands.

| # | Domain | Model | ~n |
|---|---|---|---|
| D19 | Operator-phrasing multiplication (same gated call, N phrasings/contexts) | **Haiku/Sonnet** | ~7000 |
| D20 | Context / state variation | **Haiku** | ~3000 |

### Phase 8 — Deferred
- **D21 Operator-voice track** — real external transcripts (Claude Code / OpenCode
  / ChatGPT readers). Needs real data that does not exist yet → after freeze.
- **Freeze ("dondur")** → run `corpus/assemble.py` → training JSONL → M7.

**Volume math:** 974 (now) + Phase 4 ~670 + Phase 5 ~1450 + Phase 6 ~1200 +
Phase 7 ~10000 ≈ **~14–15k**. Phase 7 is the dial for hitting 15k+.

---

## 4. Model policy (authoring)

Refines [`ultracode-model-policy`] for the corpus-authoring context (there the
axis is research/code/review; here it is *reasoning-author quality vs cost*):

- **Fable** → highest-cost-if-wrong *judgment*: LegalAction, safety/refusal,
  memory/context, complex + long-horizon trajectories. "Its reasoning is sharp";
  reserve it for the calls a keyword-matching 2B could never get right.
- **Opus 4.8** → complex tool depth + cross-domain trajectories + the **final
  verifier of every bank** (gate + T5 + judgment scan) + Fable-auth fallback.
- **Sonnet 5** → mid-complexity single-call depth + straightforward chains (the
  bulk of Phase 5). Good reasoning, faster/cheaper.
- **Haiku 4.5** → phrasing/context augmentation of *already-gated* calls
  (Phase 7). Cheap volume; the call is already valid, so risk is only phrasing
  quality → Opus-sampled.

**Invariant that makes this safe:** any author → `model_validate` + `strict_args`
+ T5 + Opus judgment scan. Format cannot drift; reasoning is reviewed.

---

## 5. The authoring loop (per bank)

1. Author `authored/<domain>.py` (`SCENARIOS` / `TRAJECTORIES`) — real `context`,
   correct `tool`+`args`, 1–2 sentence `reasoning` for judgment cases.
2. Self-gate: `build_corpus` / `build_trajectories` must report **0 rejected**;
   `ruff check` + `mypy` clean. (See corpus README for exact commands.)
3. Register in `authored/__init__.py`.
4. `uv run --frozen pytest packages/orchestrator/tests/corpus/ -q`.
5. Opus (main-loop) judgment/flow scan → then it counts as landed.
6. **Operator commits.** (Claude never commits — hard rule.)

**Mixed-parallel batch shape:** dispatch one background Fable agent (a decision
bank) while the main-loop Opus authors a depth bank directly; gate + verify both
when the Fable agent returns; register; repeat.

---

## 6. Hard-won lessons (do not relearn the hard way)

1. **Fable auth drops are intermittent**, not outages — agents in the same batch
   can independently succeed/fail with `"Not logged in · Please run /login"`. It
   self-heals; `/login` may not fix the Fable-model access immediately.
2. **A "failed" Fable agent often already wrote its file** before the auth error
   hit its final call. ALWAYS check the target file on disk + gate it before
   declaring loss → salvage it.
3. **Never `TaskStop` a background agent assuming auth failure** without checking
   its last checkpoint. Prematurely killing working agents caused real data loss
   once (one had to be Opus-re-authored, one was already written and salvaged).
   If a Fable agent dies, TAKE OVER: salvage its file if written, else author it
   yourself (Opus).
4. **Schema gotchas found while authoring** (the gate catches these — fix, don't
   fight): `browser_extract.extraction_schema` must be FLAT `{str: str}`, not a
   nested JSON-schema; simulator `udid` must be ≥10 chars; `strict_args=True`
   rejects extra args even when the runtime would tolerate them (intentional —
   canonical purity).
5. **One Fable agent per big coherent domain** (~4 per round, not dozens) —
   "don't split what one Fable can do." Spawned agents must not spawn their own
   sub-agents.

---

## 7. Continuing on the main machine

State is fully in git (`main` @ `981a7fd`+). The per-machine `~/.claude/.../memory/`
notes do **not** travel — this document is their durable, portable replacement.

**Protocol:**
- Work starts only on the operator's explicit **"devam"** (or "başla"). Do not
  auto-queue rounds.
- Freeze happens only on **"dondur"** → run the assembler (§ corpus README).

**First batch on "devam"** (mixed-parallel):

| Channel | Model | Domain | First slice |
|---|---|---|---|
| A (background agent) | **Fable** | D1 — LegalAction decision layer | ~50 scenarios |
| B (main loop) | **Opus 4.8** | D5 — iOS deep | ~50 scenarios |

Then gate + T5 + judgment-scan + register both; proceed to the next mixed batch
(e.g. Sonnet depth + Fable safety). Alternative openings are fine — e.g. lead
with D18 (full heartbeat loop) if trajectories are the priority.

**Environment reminder:** this is a weak Windows box — never run the app; use
`uv run --frozen` for targeted pytest/ruff/mypy only. The corpus code is pure
data-pipeline (no app, no GPU, no `lancedb`), so it runs fine offline. GPU/QLoRA
training is M7, out of scope.
