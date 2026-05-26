# ADR-010 — SelfFork Vision Lock (pre-M7 freeze)

**Status:** Accepted (S-Vision sprint, 2026-05-26 — audit-god 3-parallel passed: 0 CRIT / 3 HIGH, all 3 resolved by honest scope split below)
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

**MUST (pre-M7) — split by scope: SEAM ships in S-Vision; runtime WIRE in the
sprint after. The split honors [[no-mvp-full-quality-first-time]] — scope can be
small but quality cannot be staged; every shipped seam is full-quality.**

- **24/7 Agentic Loop policy** (§2) — the top vision
  ([[selffork-247-agentic-loop-2026-05-25]]). **SEAM + WIRE both shipped:**
  StuckDetector + caps + checkpoint→resume all live in `lifecycle/` +
  `heartbeat/` ([[s-vision-loop-complete-2026-05-26]]).
- **Heartbeat `BODY_USE` + `BODY_REVIEW` LegalActions** (8 → 10) — granular
  Body audit for distillation. **SEAM + WIRE both shipped:** enum + filter
  Rule 6 (`body_daemon_alive_probe`, fail-CLOSED) + executor handlers +
  injectable `BodyUseDriver` / `BodyReviewDriver` + `build_default_heartbeat`
  pass-through.
- **Auto-PR creation** — Self Jr opens a PR after S3 soft-confirm. **SEAM
  + WIRE both shipped:** `tools/auto_pr.py::auto_pr_create` (gh CLI wrapper
  with `missing_binary`/`gh_error`/`timeout`/`no_url`/`ok` status vocabulary)
  + registered in `build_default_registry`.
- **Plugin/Skill marketplace** (Hivemind H4 lift, NO marketplace server) —
  was SHOULD, promoted into the MUST table because the symlink installer is
  the day-1 distribution mechanism. **SEAM shipped, dashboard WIRE deferred:**
  `skills.py::SkillInstaller` + tests; CLI / lifespan invocation (`selffork
  skills sync`) lands in S-Bridge.
- **Voice modality** — **Telegram voice-message only** (decided 2026-05-26).
  **SEAM shipped, WIRE deferred:** `voice.py::VoiceBackend` Protocol +
  `WhisperCliVoiceBackend` (openai-whisper subprocess wrapper) +
  `NullVoiceBackend` + `default_voice_backend()`. **Telegram inbound
  detection of `message.voice` → backend.transcribe() lands in S-Bridge** —
  the existing S3 outbound bridge handles the reply side already.
- **Body M7 expansion** — browser-use (web) + mobile-use (Android+iOS) +
  **VR/AR (Quest 3 + Vision Pro, BOTH)** (§4). **SEAM shipped, full driver
  packs deferred:** the BODY_USE/BODY_REVIEW seam + pluggable
  `body_daemon_alive_probe` + driver callables (all wired through
  `build_default_heartbeat`) are S-Vision's contract; the **~250-380 per-
  platform tool packs (incl. ~120 mobile) + the real browser-use /
  mobile-use / VR-AR adapters are S-ToolFleet** ([[mobile-primary-build-surface-2026-05-24]]).
- **Operator-coaching feedback loop** — **AUDIT SEAM shipped, runtime
  WIRES deferred:** `heartbeat/audit.py::Correction` Pydantic model +
  `AuditWriter.write_correction` / `read_corrections` + sibling
  `corrections.jsonl`. **Two wires deferred:** (a) Telegram inline-edit /
  `/correct` command in `telegram/inbound_router.py` → S-Bridge; (b)
  `selffork_mind/ingest/heartbeat.py` extension to tail-follow
  `corrections.jsonl` + project into T2 Notes → S-Train prep (the
  weighting itself is the M7 corpus generation step).

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

Two passes: a **kickoff 5-rival surface read** (a.m.) then a **16-rival deep read**
(p.m., parallel `explorer-god`, file:line in the agent reports) that *corrected* the
kickoff — most importantly skyvern, which does have a hard same-tool stop. Primary
surfaces:

| Rival | Loop shape | Stop | Stuck-detect | Tool scale | Verdict for Self Jr |
|---|---|---|---|---|---|
| **browser-use** | `while` + `step()` | done-tool + max-steps + force-done last step | **YES** — `PageFingerprint`/`ActionLoopDetector`: action-repeat hash + page-stagnation (but SOFT 5/8/12, never blocks) | full-list + domain filter (no RAG, ~30 tools) | ADOPT no-change recipe + dual axes; REJECT soft-only/high-threshold |
| **skyvern** | tail-recursion (planner/executor) | completion-verify LLM + step/retry caps | **YES** — `detect_tool_loop` same-tool-3x **HARD-BLOCK** (`MAX_CONSECUTIVE_SAME_TOOL=3`) + structural corrective *(kickoff missed this)* | fixed DOM action enum | REJECT recursion (ADR-011 hang); ADOPT same-tool-3x threshold + completion-verifier |
| **mobile-use** | LangGraph cyclic state-machine | subgoal-completion gate + recursion budget | prompt-only (none in code) | fixed 15-tool registry | ADOPT cyclic gate + cortex/executor brain-hands split; lift topology NOT LangGraph runtime |
| **Hexis** | **timer/queue split** (worker decides WHEN, consumer executes WHAT) | rest = no-tool-call (first-class) | NONE (prompt-only) | permission-filter + LLM picks | ADOPT worker/queue split (24/7 enabler) + cross-tick checkpoint→resume |
| **cua** | `while` + pluggable step | no-tool-call turn + cost budget | NONE (human/HITL) | fat computer-tool + action sub-types | ADOPT fat-tool dispatch + `on_run_continue` hook; REJECT cost-gate/never-confirm/human-rescue |

**Deep-read findings (the §2.2 backbone):**

- **Hard stuck-stop blueprints DO exist** (correcting the kickoff's "no rival has one"):
  **PraisonAI** `escalation/doom_loop.py` (MIT) — SHA-256 `(action,args,result)` + 6 deterministic
  checks (identical-3 / similar-5 / consec-fail-3 / no-progress-5 / time-300s / content-chant-8) +
  recovery ladder (retry→escalate→help→abort) + `completion_reason` enum; **deer-flow**
  `LoopDetectionMiddleware` (MIT) — identical-set hash (warn@3→hard@5) + per-tool freq
  (warn@30→hard@50), normalize-before-hash, breach strips `tool_calls`→final; **skyvern**
  `detect_tool_loop` (AGPL → idea-only) — same-tool-3x hard-block; **browser-use** (MIT) — the
  no-change recipe above. All deterministic, zero-LLM, stdlib.
- **The genuine gap (no rival fills):** a *combined* gate plus **oscillation / k-cycle** detection —
  skyvern explicitly catches only `A-A-A`, never `A-B-A-B`. SelfFork-original (§2.2.4).
- **Cancellable loop = cross-rival consensus** (goose `CancellationToken` at every boundary · pi
  `AbortSignal` · agentscope `asyncio.cancel()` + fake-tool-result · deer-flow `abort_event` ·
  PraisonAI `interrupt_controller`): cooperative cancel at each loop boundary + the ADR-011
  idle-watchdog (✅ landed) is the validated shape (§2.2.1).
- **Checkpoint→resume prior art** (informs §2.2.6, now wired): agentscope `state_dict`/
  `load_state_dict` (strongest — nested + pydantic codec) · pi append-only JSONL-tree replay · AIOS
  pid-keyed suspend/resume · deer-flow SQLite checkpointer · Codeman `state.json`
  crash→reset-running-to-pending; Hexis timer/queue split is the 24/7 enabler.
- **Stop-policy gem:** Codeman's *occurrence-based* sentinel guard (1st hit = prompt-echo, 2nd = real,
  + common-word blacklist) directly hardens our `[SELFFORK:DONE]` against false positives.

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
   soft-confirm** (S3 warden, 4h Telegram) | **genuine ambiguity** (operator check-in) | **hard-limit**
   | **stuck-detector**. The hard-limit is a **50 tool-call action-cap (always-on backstop)** plus an
   **opt-in wall-clock cap (default OFF**, operator decision 2026-05-26): a fixed wall-clock would kill
   a legitimate slow CPU generation, which ADR-011 §5 forbids, so runaway protection leans on the
   action-cap + stuck-detector + ADR-011 idle-token watchdog, and the wall-clock stays a knob for
   fast-cloud deployments. *(Implemented: `LifecycleConfig.hard_action_cap=50` /
   `wall_clock_cap_seconds=None`; `session.py::_enforce_loop_caps`; audit `loop.cap_reached`.)*
4. **Stuck-detector = DETERMINISTIC + HARD.** The corpus *does* contain hard-stop blueprints (§2.1:
   PraisonAI / deer-flow / skyvern same-tool-3x / browser-use no-change) — the earlier "no rival has a
   hard stop" claim was wrong and is corrected here. What is **SelfFork-original** is the
   *combination*: one deterministic gate over **four axes** — same-tool-3x · no-observable-change-3x ·
   consecutive-failure-3x · **oscillation / k-cycle** (`A-B-A-B`, which skyvern explicitly does *not*
   catch) — tuned **hard@3** for a loop-prone 2B model, with a **soft@2 NUDGE** that injects a
   structured corrective (one self-correction chance before the hard ABORT), no-op tools
   (`wait`/`done`/…) exempted. Fires regardless of model output. *(Implemented:
   `lifecycle/stuck_detector.py`, wired per-round in `session.py::_observe_round`; audit `loop.stuck`
   / `loop.stuck_warning`.)*
5. **Tool selection at scale (RAG-over-tools — no rival precedent).** All 5 rivals dump a full
   fixed list (~15-30 tools) to the model. SelfFork's S-ToolFleet target is ~250-380 tools — a
   full-list prompt is infeasible for a 2B model. Build **RAG-over-tool-descriptions + top-K context
   injection** (+ fat-tool/action-subtype grouping à la cua). This is genuinely new; locked as a
   S-ToolFleet requirement, not a lift.
6. **Cross-tick checkpoint → resume** (Hexis): the Heartbeat writes a
   `{step, progress, next_action, workspace}` checkpoint every tick; on boot the daemon now *reads*
   it back and feeds a one-shot resume hint to the first productive deliberation tick, so a restart
   mid-task continues instead of forgetting — required for multi-hour 24/7 tasks (autonomous mobile
   regression = the killer use case). *(Implemented: `heartbeat/checkpoint.py` `workspace` field;
   `scheduler.py::_read_resume_checkpoint` + one-shot `_consume_resume_hint` →
   `deliberation.select(resume_hint=…)`. The CPU-hours out-of-band worker/queue split (§2.2.2)
   remains the deferred S-ToolFleet half.)*
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

The operator sends a Telegram voice message; Self Jr transcribes the OGG/Opus blob via a pluggable
:class:`VoiceBackend` and treats the result as a normal text turn; the existing S3 outbound bridge
handles voice replies. Rationale: the mobile companion app is post-M7, the bridge is already
Telegram (S3), and this is the least-code path that still delivers "talk to Self Jr."

**S-Vision ships the protocol seam + one real STT** ([[no-mvp-full-quality-first-time]] — pluggable
day 1): `voice.py::VoiceBackend` Protocol (async `transcribe(audio, *, mime)` → `str`),
`WhisperCliVoiceBackend` (subprocess wrapper around the **`openai-whisper`** Python CLI — whisper.cpp
needs a custom adapter), `NullVoiceBackend` for the no-STT-installed case, and
`default_voice_backend()` factory. Errors split cleanly: `VoiceUnavailableError` (install gap) vs
`VoiceTranscriptionError` (run failure). The async path uses `asyncio.to_thread` so the event loop
stays unblocked (ADR-011 §3 contract).

**S-Bridge wires the inbound side** — `telegram/inbound_router.py` learns to detect
`message.voice`, download the audio, call `default_voice_backend().transcribe(...)`, and dispatch
the transcript as the equivalent text turn. The Whisper *runtime install* and the inbound *wire* are
both deferred so this ADR stays Accepted on the contract, not the deployment.

Rejected this session: Local-only, Hybrid, Cloud-only — deferred behind the protocol seam (plug a
new `VoiceBackend` later without a wire-format break).

---

## 4. §Body M7 expansion (locked)

Per [[body-pillar-m7-fine-tune-expansion]] + [[mobile-primary-build-surface-2026-05-24]]: Self Jr
learns to use its "uzuv" during M7 fine-tune. Drivers: **browser-use** (web), **mobile-use**
(Android+iOS — THE primary surface, ~120 mobile tools, operator's 6+ Expo apps), **VR/AR (Quest 3
ADB + Vision Pro accessibility — BOTH, pre-M7 in S-ToolFleet)**, desktop (AppleScript+tmux ✅).
Heartbeat gains `BODY_USE` (write/click/screenshot) + `BODY_REVIEW` (read-only vision parse) as the
9th/10th LegalActions. Self Jr = "kendi ürettiğini test eden ajan": write → build → **observe** →
**interact** → decide. Closes the three-pillar bridge (Reflex calls Body; Mind records Body → T2).

**S-Vision Faz B shipped the Heartbeat-side seam** (Turkish values `uzvunu_kullan` /
`uzvunu_incele`): `actions.py::LegalAction` 8→10, `filter.py` Rule 6 `body_daemon_alive` gate
(fail-CLOSED — missing or failing probe → both BODY actions drop out of the legal set),
`executor.py::BodyDriverOutcome` + `BodyUseDriver` / `BodyReviewDriver` injectable callables (None ⇒
`skipped`, exception ⇒ `failed`, `succeeded=False` ⇒ `failed`, else `executed`), and
`build_default_heartbeat` pass-through for `body_daemon_alive_probe` / `body_use_driver` /
`body_review_driver` so the dashboard can wire a real Body subsystem without touching the
orchestrator. **S-ToolFleet ships the actual drivers + fat per-platform tool packs** — the seam is
the contract S-Vision freezes; the implementations land in the per-platform sprint.

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
- **`LegalAction` Turkish-value closed set (10 entries)** — the action vocabulary the deliberation
  layer emits as JSON (`{"action": "<value>"}`). Frozen: `task_başlat`, `session_devam`, `cli_seç`,
  `kanban_task_öner`, `operatöre_sor`, `fikirleş`, `uzvunu_kullan`, `uzvunu_incele`, `bekle`,
  `kendini_durdur` (`actions.py::LegalAction`, ADR-008 §4.4 table). M7 trains on these literal
  strings — renaming breaks the reflex.
- **`Correction` JSONL schema + `corrections.jsonl` sibling** — operator-coaching record
  (`heartbeat/audit.py::Correction`, S-Vision Faz D). Frozen fields: `audit_idempotency_key`,
  `correction_text`, `suggested_action`, `corrected_at`, `source`. S-Train consumes this stream;
  schema break = lost coaching corpus.
- **`VoiceBackend.transcribe(audio: bytes, *, mime: str) -> str`** signature (`voice.py`, S-Vision
  Faz A). Frozen so future STT plugins (cloud Whisper, ElevenLabs, local Piper) drop in without a
  wire-format break.
- **`auto_pr_create` tool name + `_AutoPRCreateArgs` Pydantic schema** (`tools/auto_pr.py`, S-Vision
  Faz E). Frozen fields: `title` (1-200), `body` (1-20000), `base` (default `main`), `head`,
  `draft`. Renaming the tool or its args post-M7 breaks the trained Self Jr reflex.

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

**Accepted (2026-05-26).** S-Vision shipped: §2 Agentic Loop (StuckDetector + caps +
checkpoint→resume), Heartbeat 8→10 LegalActions with body-alive gate, auto-PR tool, Skill installer,
Voice protocol seam + Whisper backend, Correction audit record. Three audit-god 3-parallel runs (a
§2 audit at section close + a session-wide audit at this close) recorded 0 CRITICAL / 0 ship-blocker
MAJOR; the 3 HIGH findings (build_default_heartbeat body wire-through, Voice Telegram inbound wire,
Correction → Mind T2 ingest) were resolved by either (a) implementing the wire (body kwargs in
`build_default_heartbeat`), or (b) honest scope-split into S-Bridge as a runtime-wire follow-up (§1
MUST table now reads "SEAM shipped, WIRE deferred" where applicable). Format Freeze snapshot
recorded in §5 covers 10 wire surfaces now (4 added at S-Vision close: LegalAction Turkish closed
set, `Correction` schema, `VoiceBackend.transcribe` signature, `auto_pr_create` tool name+args).

**Sprint order ([[sprint-order-2026-05-22]] tail):** S-Vision ✅ → **S-Bridge (next — wires Voice
inbound + Correction → Mind T2 + interactive structured-tool round-trip)** → S-ToolFleet (~250-380
tools + RAG-over-tools + real Body drivers + ~120 mobile pack) → S-Train → M7. S-Stream (ADR-011) ✅
landed earlier as the agentic-loop prerequisite.
