# ADR-010 — SelfFork Vision Lock (pre-M7 freeze)

**Status:** Draft (S-Vision sprint, opened 2026-05-26 — finalized + audit-god at S-Vision close)
**Augments:** ADR-006 (v3 pivot), ADR-008 (Heartbeat), ADR-011 (Inference Resilience — agentic-loop prereq)
**SSOT inputs:** `[[s-vision-decisions-2026-05-23]]` (16 locked decisions), `[[s-vision-candidates-github-rag-2026-05-24]]` (tool/loop/RAG blocks), `[[selffork-as-forge-scaling-judgment-2026-05-24]]` (thesis), `[[body-pillar-m7-fine-tune-expansion]]` (Body), `[[freeze-philosophy-broad-vision]]` (why freeze).

> This ADR is the **last exit gate before M7** ([[freeze-philosophy-broad-vision]]). M7 = de-facto
> freeze (model re-train + audit migration + format-incompat make rollback expensive), so the
> vision is drawn as **broad as it is consistent** here, then locked. Decisions below were taken
> via AskUserQuestion over 2026-05-23/24/26; this document is the durable record. The §Agentic
> Loop section (§2) is grounded in a MANDATE 9 corpus read of 5 production agentic rivals
> (2026-05-26) — citations inline.

---

## 0. Preamble — the forge thesis (vision frame)

SelfFork's product is **not "rent Yamaç"** — it is the **loom, not the cloth**
([[selffork-as-forge-scaling-judgment-2026-05-24]]): Apache-2.0, fork-friendly, anyone distills
their own reflex. The design bet is explicit and bounded: the **small model (Gemma 4 E2B Q4_0) is
NOT a genius** — it carries the **operator's decision reflex** (which CLI, "kolaya kaçma", what to
approve/reject, rhythm, taste); the **intelligence lives in the system** (powerful CLI agents write
code · Mind carries memory · Body is eyes+hands · Heartbeat turns the loop · Router picks the CLI).
Self Jr = **USER simulator** ([[yamac-jr-is-user-simulator]]), not a senior engineer. Every lock
below serves "operator-shaped reflex + smart system", i.e. **scaling judgment, not replacement**.

---

## 1. Vision-lock scope (MoSCoW)

The 16 decisions are recorded verbatim in `[[s-vision-decisions-2026-05-23]]`; the categorisation:

**MUST (full impl, pre-M7):**
- Body M7 expansion — browser-use (web) + mobile-use (Android+iOS) + **VR/AR (Quest 3 + Vision Pro, BOTH)** (§4).
- Voice modality — **Telegram voice-message only** (decided 2026-05-26, §3).
- Heartbeat `BODY_USE` + `BODY_REVIEW` LegalActions (8 → 10) — granular Body audit for distillation.
- Auto-PR creation — Self Jr opens a PR after S3 soft-confirm (`gh pr create` + warden hook).
- Operator-coaching feedback loop — audit `operator_corrected` flag + Telegram inline-edit → S-Train weighting.
- **24/7 Agentic Loop policy** (§2) — the top vision ([[selffork-247-agentic-loop-2026-05-25]]).

**SHOULD (vision-width, full impl):**
- Plugin/Skill marketplace — git repo + symlink fan-out (Hivemind H4 lift, NO marketplace server).

**POST-M7 (deferred, not rejected):**
- Mobile companion app (rides with Voice — native UI after freeze).
- Memory federation (multi-machine) — single-machine ships; federation post-freeze.

**WON'T (explicit reject — §6).**

---

## 2. §Agentic Loop — 24/7 autonomous operation policy (corpus-grounded)

**Goal** ([[selffork-247-agentic-loop-2026-05-25]]): Self Jr runs continuously like Claude Code —
take a goal, then `observe → think → act → observe …` with many tool-calls (10-50+) until the goal
is reached or a genuine check-in is needed. NOT one-tool-per-turn ping-pong. ADR-011 (streaming +
no-hang) is the **prerequisite** — a 24/7 loop on CPU cannot block on a wedged inference.

### 2.1 Corpus read (MANDATE 9, 2026-05-26)

Five production agentic rivals read via `explorer-god` (file:line evidence in agent reports):

| Rival | Loop shape | Stop | Stuck-detect | Tool scale | Verdict for Self Jr |
|---|---|---|---|---|---|
| **browser-use** | `while` + `step()` | done-tool + max-steps + force-done last step | **YES** — hash-window repeat + page-stagnation (but SOFT, ≥5, never blocks) | full-list + domain filter (no RAG, ~30 tools) | ADOPT loop spine + dual stuck axes; REJECT softness/high-threshold |
| **skyvern** | tail-recursion (planner/executor) | completion-verify LLM + step/retry caps | **NONE** (budget-only) | fixed DOM action enum | REJECT recursion (ADR-011 hang); ADOPT separate completion-verifier |
| **mobile-use** | LangGraph cyclic state-machine | subgoal-completion gate + recursion budget | prompt-only (none in code) | fixed 15-tool registry | ADOPT cyclic gate + cortex/executor brain-hands split; lift topology NOT LangGraph runtime |
| **Hexis** | **timer/queue split** (worker decides WHEN, consumer executes WHAT) | rest = no-tool-call (first-class) | NONE (prompt-only) | permission-filter + LLM picks | ADOPT worker/queue split (24/7 enabler) + cross-tick checkpoint→resume |
| **cua** | `while` + pluggable step | no-tool-call turn + cost budget | NONE (human/HITL) | fat computer-tool + action sub-types | ADOPT fat-tool dispatch + `on_run_continue` hook; REJECT cost-gate/never-confirm/human-rescue |

### 2.2 Locked loop policy

1. **Loop shape = explicit cancellable async while-loop** (NOT recursion — skyvern's tail-recursion
   is the exact synchronous-blocking hang ADR-011 forbids). The round-loop (`lifecycle/session.py`)
   is the INNER loop; the Heartbeat (ADR-008) is the OUTER 24/7 loop.
2. **Worker/queue split for the outer loop** (Hexis pattern): the Heartbeat timer decides *when* a
   tick fires; a consumer executes the (potentially CPU-hours) tick **out-of-band**, so a slow tick
   never blocks the next scheduling decision. Crash mid-tick loses nothing (stateless re-poll).
   *(S-ToolFleet/M7-adjacent infra task; ADR-011 per-tick budget already prevents wedge.)*
3. **Stop-conditions (aggressive + safety nets, [[s-vision-candidates-github-rag-2026-05-24]]):**
   stop on **goal-achieved** (`[SELFFORK:DONE]` sentinel — [[done-sentinel-protocol]]) | **destructive
   soft-confirm** (S3 warden, 4h Telegram) | **genuine ambiguity** (operator check-in) | **hard-limit
   (50 tool-calls OR 30 min wall-clock)** | **stuck-detector**.
4. **Stuck-detector = DETERMINISTIC + HARD (SelfFork-original — the universal corpus gap).** No rival
   has a code-level hard stuck-stop (browser-use is soft ≥5; skyvern/Hexis/mobile-use/cua have none).
   A 2B reflex model is more loop-prone, so build a hard stop firing on **same-tool-3x OR
   no-observable-change-3x** (two axes, per browser-use's split: action-repeat hash + observation
   fingerprint). Fires regardless of model output.
5. **Tool selection at scale (RAG-over-tools — no rival precedent).** All 5 rivals dump a full
   fixed list (~15-30 tools) to the model. SelfFork's S-ToolFleet target is ~250-380 tools — a
   full-list prompt is infeasible for a 2B model. Build **RAG-over-tool-descriptions + top-K context
   injection** (+ fat-tool/action-subtype grouping à la cua). This is genuinely new; locked as a
   S-ToolFleet requirement, not a lift.
6. **Cross-tick checkpoint → resume** (Hexis): on budget/stall exit mid-task, persist a
   `{step, progress, next_action}` resume token so the next tick continues — required for multi-hour
   24/7 tasks (autonomous mobile regression = the killer use case).
7. **Plan-then-execute = optional** (skyvern/mobile-use planner/executor split maps to
   Heartbeat→CLI-agent). Self Jr learns *when* to plan vs act ad-hoc from the S-Train corpus.

### 2.3 M7 corpus requirement (S-Train)

The fine-tune corpus MUST contain **long multi-tool agentic traces (30+ tools/session)** — current
Yamaç corpus is mostly 1-2-tool. Trace shape (browser-use + skyvern synthesis): per step
`{reasoning/intent → <selffork-tool-call> → result}`. **Loss buckets:** the reasoning/`next_goal`
narration is Yamaç-voiced → **1.0 (last) / 0.3 (prior)**; tool **results** are system feedback →
**0.0** ([[s-vision-candidates-github-rag-2026-05-24]] §M7 Loss). Mind ingest + Reflex loss-masking
both consume the trace, so thoughts must be split from tool-output in the record.

---

## 3. §Voice modality — Telegram voice-message only (decided 2026-05-26)

No separate STT/TTS backend. The operator sends a Telegram voice message; Self Jr transcribes
(Telegram's own STT or a minimal local fallback) and may reply with voice over the existing Telegram
bridge. Rationale: the mobile companion app is post-M7, the bridge is already Telegram (S3), and this
is the least-code path that still delivers "talk to Self Jr." A pluggable `VoiceBackend` protocol is
scaffolded in S-Vision (so local Whisper/Piper or cloud can be added later without a format break);
full conversational voice arrives with the post-M7 mobile companion. Rejected alternatives (this
session): Local-only, Hybrid, Cloud-only — deferred behind the protocol seam.

---

## 4. §Body M7 expansion (locked)

Per [[body-pillar-m7-fine-tune-expansion]] + [[mobile-primary-build-surface-2026-05-24]]: Self Jr
learns to use its "uzuv" during M7 fine-tune. Drivers: **browser-use** (web), **mobile-use**
(Android+iOS — THE primary surface, ~120 mobile tools, operator's 6+ Expo apps), **VR/AR (Quest 3
ADB + Vision Pro accessibility — BOTH, pre-M7 in S-ToolFleet)**, desktop (AppleScript+tmux ✅).
Heartbeat gains `BODY_USE` (write/click/screenshot) + `BODY_REVIEW` (read-only vision parse) as the
9th/10th LegalActions. Self Jr = "kendi ürettiğini test eden ajan": write → build → **observe** →
**interact** → decide. Closes the three-pillar bridge (Reflex calls Body; Mind records Body → T2).

---

## 5. §Format Freeze inventory (frozen at M7)

The wire formats below are **frozen** before M7 (post-freeze change = re-train + migration). Full
snapshot is locked at S-Vision close; inventory:

- `<selffork-tool-call>{...}</selffork-tool-call>` — Jr tool-call block ([[jr-tool-protocol]]).
- `<selffork-tool-response correlation_id="…">{...}</selffork-tool-response>` — S-Bridge inbound
  (interactive structured-tool round-trip — [[s-bridge-sprint-added-2026-05-25]]).
- `[SELFFORK:DONE]` — session-end sentinel ([[done-sentinel-protocol]]).
- `[SELFFORK:SPAWN: …]` — child-session spawn.
- `<private>…</private>` — claude-mem redaction tag.
- Audit `AuditCategory` closed Literal + heartbeat `AuditEntry` schema (incl. `decision_stalled`).

---

## 6. §Won't-have (explicit reject — so "why didn't we?" is answered)

From [[s-vision-decisions-2026-05-23]] + [[subscription-based-cli-no-cost-dashboard]]: multi-tenant
SaaS · cloud-bound runtime · closed-source runtime dep · LLM-driven memory editing · telemetry
default-on · Self Jr senior code review ([[jr-review-junior-level-only]]) · Self Jr deep code
generation (CLI-agent's job) · per-token cost dashboard · external integrations beyond Telegram
(Slack/Discord/Linear/Notion/Jira) · multi-persona Self Jr · federated cross-Self-Jr learning · IoT ·
replay-mode operator UI · cross-language explicit support (Self Jr is language-agnostic). Each is
vision-inconsistent (kişisel-asistan + self-host + reflex-not-knowledge), not a capability gap.

---

## 7. §Extension surfaces (scaffold day-1, [[no-mvp-full-quality-first-time]])

Plugin Protocol + Skill marketplace (symlink fan-out, canonical `~/.selffork/skills/`) · VoiceBackend
protocol (§3) · auto-PR adapter · operator-coaching audit flag. Pluggable interfaces ship even with
one implementation — no "add the abstraction later."

---

## 8. Status / next

**Draft.** S-Vision sprint implements §2 loop policy (+ S-Bridge for the structured-tool round-trip,
S-ToolFleet for the ~250-380 tools + RAG-over-tools), wires Voice scaffold, Body driver expansion,
auto-PR, coaching loop; then **audit-god** review (won't-have violations, extension type-safety,
vision-consistency) + **Format Freeze snapshot** before this ADR flips to Accepted. Sprint order
([[sprint-order-2026-05-22]] tail): S-Vision (this) → S-Bridge → S-ToolFleet → S-Train → M7; S-Stream
(ADR-011) ✅ landed as the agentic-loop prerequisite.
