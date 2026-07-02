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
- **`ToolSpec.defer_loading: bool` field** (`tools/base.py`, S-ToolFleet Faz 0). Per-spec opt-in
  flag — when `True`, the spec is OMITTED from the eager system-prompt catalog Self Jr sees by
  default and only surfaces after a `tool_search` retrieval. Frozen so existing specs keep
  defaulting to `False` (eager) and Faz 1+ fan-out can flip individual specs without breaking
  the trained reflex.
- **`tool_search` tool name + `ToolSearchArgs` Pydantic schema** (`tools/tool_search.py`,
  S-ToolFleet Faz 0 RAG-over-tools seam). Frozen fields: `query` (1-2000 chars), `top_k` (1-20,
  default 5), `include_eager` (default `False`). Result shape:
  `{status, query, results: [{name, description, args_schema}], matches}` — mirrors
  `ToolRegistry.catalog()` row shape so retrieved tools splice into the next round identically
  to eager ones.
- **`SqlitePendingStructuredQuestionStore` schema** (`tools/structured_question.py`,
  S-ToolFleet Faz 0 F2). Table `pending_structured_questions` with frozen columns:
  `correlation_id TEXT PK`, `payload_json TEXT`, `session_id TEXT`, `created_at TEXT (ISO)`,
  `expires_at TEXT (ISO)`, `answer TEXT`, `answered_at TEXT`, `cancelled INTEGER`. WAL mode
  + busy_timeout 5s default. Env knob: `SELFFORK_STRUCTURED_QUESTION_DB` (empty ⇒ in-memory).
  Cross-process schema break = lost CLI/dashboard handshake.

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

**Sprint order ([[sprint-order-2026-05-22]] tail):** S-Vision ✅ → S-Bridge ✅ →
**S-ToolFleet ✅ (Faz 0-4 complete, 2026-05-26 night — 289-tool registry, §9.17)** → S-Train → M7.
S-Stream (ADR-011) ✅ landed earlier as the agentic-loop prerequisite.

---

## 9. §S-ToolFleet Amendment (2026-05-26 evening)

**Trigger.** S-Bridge close + 4-agent parallel pre-kickoff audit
(explorer-god ×2 + selffork-researcher + audit-god) surfaced four substrate gaps
(F1 body wire DEAD in round-loop, F2 cross-process structured-question gap,
F3 STRUCTURED_TOOL_NAMES vs registry drift, F4 cleanup_expired with no production caller)
plus the structural absence of a RAG-over-tools seam and the hierarchical-namespace
ceiling. Operator response (4-question AskUserQuestion, 2026-05-26 ~17:35): all
Recommended path — Faz 0 substrate first, Mind-HybridRetriever-reuse Anthropic Tool Search
emulation, Quest3-ADB-full + Vision Pro-vision-only split, Mobile-first wave first.
See [[s-toolfleet-scope-2026-05-26]] + [[substrate-findings-2026-05-26]].

### 9.1 Locked decisions (operator AskUserQuestion, 2026-05-26)

| # | Question | Locked answer |
|---|---|---|
| 1 | **Faz sırası** — substrate vs fan-out parallel? | **Faz 0 önce — substrate solidify** (F1+F2+F3+F4 + RAG seam + hierarchical tree) before any fan-out. ~1.5 hafta scope. |
| 2 | **RAG retrieval baseline** | **Anthropic Tool Search emulation + Mind HybridRetriever reuse** (BM25 + token-overlap tie-breaker; per-turn top-3-5 retrieval; `defer_loading` flag per ToolSpec). Pure-dense LanceDB rejected (adversarial collapse risk, arXiv:2510.03992); bipartite tool+agent retrieval deferred (overkill at 250-tool scale). |
| 3 | **VR/AR scope** | **Quest 3 = Android ADB+MQDH full driver (~20 tool)** + **Vision Pro = Gemma 4 VLM OCR vision-only (~5-8 tool)** — modalite-çift kabul. visionOS XCTest "Designed for iPad" sınırlı; Appium yok. Honest reality, not equal effort. |
| 4 | **Wave 1 öncelik** | **Mobile-first dalga ~120 tool** (iOS-DEEP + Android-DEEP + Expo + UI-verify + crash/state). mobile-mcp + mobile-use + appium-mcp adopt; AndroidWorld eval. Operator daily-driver = Expo apps. |

### 9.2 Faz 0 deliverables (✅ all shipped 2026-05-26 evening, single session)

| Item | Site | Tests |
|---|---|---|
| **F4** — `cleanup_loop` + dashboard lifespan periodic task | `tools/structured_question.py::cleanup_loop` + `dashboard/server.py` lifespan | +3 |
| **F1** — Body wire through round-loop | `lifecycle/session.py::__init__` + ToolContext propagate (`body_driver`/`vision_runtime`/`permission_warden`/`screenshot_store`); cli.py + dashboard wire **DEFERRED to Faz 1** (no driver factory yet — Faz 0 opens the wire, Faz 1 Mobile Wave constructs the driver). | +1 |
| **F3** — Canonical structured-tool name | `cli_agent/structured_tools.py` docstring tightened (canonical = `AskUserQuestion`, drift caught as `unknown_tool` while still routing to `tool.structured_*` audit). Registry **single name only** — aliases would pollute the catalog. | +1 |
| **F2** — Cross-process `SqlitePendingStructuredQuestionStore` | `tools/structured_question.py` + `build_structured_question_store()` factory + `SELFFORK_STRUCTURED_QUESTION_DB` env. CLI subprocess + dashboard share one SQLite file when env is set; in-memory default kept for tests + legacy boots. Polling-based `wait_for_answer` (asyncio.Event doesn't cross processes). | +16 |
| **RAG-over-tools seam** | `tools/tool_search.py` (BM25Okapi + token-overlap tie-breaker) + `ToolSpec.defer_loading` field + `ToolRegistry.{catalog(include_deferred=...),eager_names(),deferred_names(),deferred_specs()}` + `tool_search` registered in default registry + `ToolContext.tool_registry`. Faz 0 ships the SEAM; every existing spec defaults `defer_loading=False` (no behaviour change). | +27 |
| **Hierarchical refactor** — `tools/body/` subpackage | Old `tools/body.py` (520 LoC, 10 tools flat) split into `body/{__init__ aggregator, _internal helpers, interaction (5 tools), observation (2), lifecycle (3)}`. Args + `build_body_tools` + private handlers re-exported from `__init__` so existing import paths are unchanged. Pattern for Faz 1+ mobile/browser/vr/desktop subpackages. | 0 (existing 16 body tests still pass after re-import) |
| **ADR-010 amendment** | This section (§9) + §5 Format Freeze additions (4 new items). | — |

**Faz 0 baseline:** 2576 backend tests pass (was 2528 pre-Faz 0; net +48), ruff/mypy/tsc clean.
Eager catalog stays at 36 tools (was 35; `tool_search` is the new addition, every spec
still `defer_loading=False`). Operator-driven commit per MANDATE 1.

### 9.3 5-Faz plan ([[s-toolfleet-scope-2026-05-26]])

| Faz | Süre | Scope |
|---|---|---|
| **0 — Substrate solidify** ✅ | ~1.5 hafta | F1 + F2 + F3 + F4 + RAG seam + hierarchical tree refactor + this amendment. |
| **1 — Mobile-first wave** | ~3 hafta | ~120 tool: iOS-DEEP (Appium XCUITest + WDA) + Android-DEEP (mobile-mcp adopt + UI Automator + Docker emulator) + Expo dev workflow + UI-verify (a11y tree primary, screenshot fallback) + crash/state capture. Real `body_driver` factory + cli.py wire (closes F1's WIRE side). AndroidWorld eval harness adopt. |
| **2 — Browser wave** | ~2 hafta | ~60 tool: browser-use registry decorator + stagehand 4-method API (`act`/`extract`/`observe`/`agent`) + CloakBrowser drop-in (Cloudflare bypass) + DeepLocator (shadow DOM + iframe). Apache 2.0/MIT lift-only — Skyvern AGPL kod kopyalama YASAK, fikir-only. |
| **3 — Cross-cutting (GitHub + Desktop + Skills)** | ~1.5 hafta | ~40 tool: gh CLI wrapper + GitHub App auth (PAT over App per [[s-vision-candidates-github-rag-2026-05-24]] decision) + Gravatar identity + Self Jr self-commit + cua-driver background macOS non-focus + skill installer subagent loop + dev tooling. |
| **4 — VR/AR** | ~1.5 hafta | Quest 3 = Android driver reuse + MQDH ADB-over-WiFi (~20 tool); Vision Pro = Gemma 4 VLM OCR + screenshot click coords (~5-8 tool) — modalite-çift kabul. |
| **Total** | ~9.5 hafta | ~245-265 tool (~250-380 hedef alt-uç, kalite > sayı per [[quality-over-speed]]). |

### 9.4 Faz 0 substrate findings + remediation summary

| # | Severity | Gap | Remediation |
|---|---|---|---|
| **F1** | CRITICAL (explorer-god, grep verified) | Body tools DEAD in round-loop — `session.py:692-707` ToolContext construction never injected `body_driver`/`vision_runtime`/`permission_warden`/`screenshot_store`. Self Jr emitting `<selffork-tool-call>{"tool":"body_screenshot",...}` hit `unauthorized` (`body.py::_require_driver`). Heartbeat had its own `driver` parameter via `heartbeat/executor.py` — wire was forgotten on the round-loop side. | Session.__init__ accepts the 4 params (default `None`); ToolContext propagation wired; cli.py / dashboard production wire deferred to Faz 1 Mobile Wave (which constructs the real driver). New test `test_body_tool_call_reaches_driver_through_round_loop` pins the wire. |
| **F2** | HIGH (audit-god) | In-memory `PendingStructuredQuestionStore` per-process — `selffork run` subprocess + dashboard process kept separate instances. Telegram `/answer` reached dashboard's store; CLI subprocess's pending question silently timed out (default 1h). S-Bridge memory claimed "CORE complete" but cross-process round-trip never worked. | New `SqlitePendingStructuredQuestionStore` (WAL + busy_timeout 5s + polling `wait_for_answer`); `build_structured_question_store()` factory picks backend via `SELFFORK_STRUCTURED_QUESTION_DB` env; cli.py + dashboard both route through factory. In-memory default kept for tests/legacy. 16 SQLite tests including cross-process handshake. |
| **F3** | HIGH (audit-god) | `STRUCTURED_TOOL_NAMES` set in `cli_agent/structured_tools.py` recognised 3 spellings (`AskUserQuestion` + snake_case + camelCase) for cross-CLI audit detection, but the registry registered only PascalCase. Drift = audit said `tool.structured_question` while result said `unknown_tool` — confusing UI. | Docstring pins **canonical = `AskUserQuestion`** (Self Jr fine-tune corpus emits this). Registry stays single (aliases would pollute catalog + RAG retrieval). Other two names kept ONLY for transcript detection of third-party CLIs (claude-code emits both). Drift invariant test confirms the pair. |
| **F4** | MEDIUM (audit-god, grep verified) | `cleanup_expired` had no production caller — dashboard process is long-lived so pending dict grew unbounded. | `cleanup_loop` (sweep-first/sleep-then pattern, mirrors `expire_loop`); dashboard lifespan starts/cancels `selffork.structured_question_cleanup` task. Final sweep on cancel. 3 tests. |

### 9.5 Status

**S-ToolFleet Faz 0 — ACCEPTED 2026-05-26 evening.** Substrate is solid: body
wire opened, cross-process IPC ships disk-backed, drift caught as `unknown_tool`,
periodic cleanup wired, RAG seam ready for fan-out, body subpackage establishes the
hierarchical pattern.

### 9.6 Faz 1 Mobile Wave deliverables (✅ all shipped 2026-05-26 late night, single session)

Operator mandate: **"Faz 1 BİTENE KADAR DURMA ÇALIŞ! ULTRATHINK ... tam takım
full enterprise test edilmiş şekilde!"** — single-session close, no deferred items.

| Item | Site | Tests |
|---|---|---|
| **F1 WIRE close** — `mobile_factory.build_default_body_driver()` + `CompositeMobileDriver` + cli.py inject + start/stop lifecycle | `selffork_body/drivers/mobile_factory.py` (new ~250 LoC) + `cli.py::run` body_driver/warden/screenshot_store wired + try/finally start/stop | +31 |
| **iOS-DEEP tool pack** — 45 tools across interaction/observation/lifecycle/system/simulator/network/element | `tools/mobile/ios/{__init__,interaction,observation,lifecycle,system,simulator,network,element}.py` + `IosDriver` extension (28 new methods) + `AppiumXcuitestAdapter` extension (24 new methods) + `IosSimulatorRuntime` extension (13 new methods) | +56 |
| **Android-DEEP tool pack** — 45 tools across interaction/observation/lifecycle/system/intent/shell/emulator | `tools/mobile/android/{__init__,interaction,observation,lifecycle,system,intent,shell,emulator}.py` + `AndroidDriver` extension (27 new methods) + `MobileMcpAdapter` extension (10 new methods) + `UiAutomator2Fallback` extension (14 new methods) | +48 |
| **Expo dev-workflow tool pack** — 12 tools (dev_start/stop/metro/eas_build/submit/publish/export/run_ios/android/install/doctor/logs_capture) — operator daily-driver | `tools/mobile/expo/__init__.py` (subprocess-wrapped expo/eas CLI calls + background process tracking) | included in fleet count |
| **UI-verify tool pack** — 10 tools (a11y/text_visible/element_exists/element_state/screenshot_match/ocr_contains/color_at/no_overflow/responsive/focus); **all eager** — observe loop dependency | `tools/mobile/ui_verify/__init__.py` (a11y-tree-first + PIL color sampling + SHA-256 screenshot match) | +15 |
| **Crash/state-capture tool pack** — 10 tools (log_fetch/bug_report/state_snapshot/restore/list/delete/diff/anr/heap/thread_dump) | `tools/mobile/crash_state/__init__.py` (JSON-persisted snapshots under `~/.selffork/state/<workspace>/<label>.json`) + `SELFFORK_STATE_DIR` env | +18 |
| **AndroidWorld eval harness scaffold** — 5 happy-path tasks + runner + TaskOutcome scoring | `selffork_orchestrator/eval/android_world/{__init__,tasks,runner}.py` (Apache-2.0 adopt; M7 prep widens to 116-task) | +13 |
| **mobile_factory + composite + protocol** | `selffork_body/drivers/mobile_factory.py` + platform attribute on IosDriver/AndroidDriver | +31 (above) |
| **Registry integration** | `tools/__init__.py::build_default_registry` adds `*build_mobile_tools()` — 158 total (36 pre + 122 mobile), 66 eager + 92 deferred | +1 (deferred-corpus invariant updated) |

**Faz 1 close baseline:** 2808 backend tests pass (was 2576 post-Faz 0; net +232).
ruff/mypy/tsc clean. Registry 158 tools (66 eager + 92 deferred). Operator commit
per MANDATE 1.

**Tool count vs scope target** ([[s-toolfleet-scope-2026-05-26]] = ~120 tools):
122 mobile tools shipped — 45 iOS + 45 Android + 12 Expo + 10 UI-verify + 10 crash/state.
Eager bucket (30) hits the AskUserQuestion #4 lock spec: top-10 per platform + every
`ui_verify_*`. Deferred bucket (92) reachable via `tool_search` (RAG-over-tools seam).

### 9.7 Faz 1 Format Freeze additions

Pinned wire-format items (breaking change = retraining):

| Item | Site | Notes |
|---|---|---|
| `mobile_*`/`ios_*`/`android_*`/`expo_*`/`ui_verify_*`/`crash_*` tool name prefixes | `tools/mobile/**` | Canonical naming convention; reserves the 5 prefixes for Faz 1+ growth |
| `BodyDriverProtocol` shape (`platform: str` + start/stop) | `selffork_body/drivers/mobile_factory.py` | Required for new driver families (browser/desktop/VR/AR — Faz 2-4) |
| Body action_type taxonomy: `ios.*` / `android.*` / `expo.*` / `ui_verify.*` / `crash.*` | every mobile handler's `_invoke_mobile(action_type=…)` call | Audit consumers + Heartbeat correction-ingest depend on the dotted form |
| `SELFFORK_BODY_PLATFORM` / `SELFFORK_BODY_PREFER` / `SELFFORK_BODY_IOS_DEVICE` / `SELFFORK_BODY_ANDROID_DEVICE` / `SELFFORK_BODY_WARDEN` / `SELFFORK_STATE_DIR` / `SELFFORK_EXPO_PROJECT_DIR` env keys | `mobile_factory.py` + `cli.py::_build_body_warden_for_driver` + `crash_state/__init__.py` + `expo/__init__.py` | Operator-facing knobs; renames break dot-env templates |
| AndroidWorld task name space (`settings_open`, `clock_alarm_create`, …) | `eval/android_world/tasks.py::TASK_REGISTRY` | Eval reports cross-reference these; renames invalidate trend data |

### 9.8 Faz 1 Status

**S-ToolFleet Faz 1 Mobile Wave — ACCEPTED 2026-05-26 late night.** Body wire
closed end-to-end (mobile_factory + composite + cli.py inject + lifecycle); 122
mobile tools shipped enterprise-grade (Pydantic args, audit-tracked, warden-gated,
handler dispatch tested via stub driver, RAG defer-bucket honoured); AndroidWorld
eval scaffold runs against the autonomous loop; ADR-010 Format Freeze extended
to 5 new pins.

### 9.9 Faz 2 Browser Wave deliverables (✅ all shipped 2026-05-26 night, single session)

Operator directive: **"hadi Faz 2 yi de bu sessionda yapalım! lets go!!!"** —
same session as Faz 1, single-session close, no deferred items.

| Item | Site | Tests |
|---|---|---|
| **Web platform wire** — `resolve_platform()` accepts `web`/`browser`, factory builds `PlaywrightWebDriver` for `SELFFORK_BODY_PLATFORM=web` | `selffork_body/drivers/mobile_factory.py` + new env knobs (`SELFFORK_BODY_BROWSER_HEADLESS`) | reused F1 wire tests |
| **PlaywrightWebDriver +35 methods** — double_click/hover/fill_form/select_option/check/uncheck/drag_and_drop/upload_file/clear/swipe/back/forward/reload/get_url/get_title/set_viewport/wait_for_load_state/wait_for_url/text_content/get_attribute/query_selector/query_selector_all/get_pdf/screenshot_element/get_html/get_console_logs/get_network_log/{new,close,list,switch,get_active,duplicate}_tab/cookies_{get,set,clear}/local_storage_{get,set,clear}/set_user_agent/set_extra_headers/enable_stealth/set_proxy/clear_cache/intercept_request/mock_response/block_url_pattern/wait_for_response/emulate_device/set_geolocation/set_locale/set_timezone/set_color_scheme/ax_tree alias | `selffork_body/drivers/web/playwright_driver.py` | included in fleet smoke |
| **Browser tool pack** — 63 tools across 9 modules: interaction (11) / navigation (9) / observation (11) / tabs (6) / storage (6) / intelligent (5) / cloak (5) / network (5) / device (5) | `tools/browser/{__init__,_internal,interaction,navigation,observation,tabs,storage,intelligent,cloak,network,device}.py` | +96 (registry + args + handlers) |
| **Stagehand-style intelligent tools** — `browser_{act,extract,observe,agent,smart_locator}` route through `ctx.vision_runtime`; return `{"status":"unwired"}` when no LLM | `tools/browser/intelligent.py` | unwired + vision-stub coverage |
| **Cloak/stealth tools** — webdriver-hide init scripts, UA override, extra headers, proxy queue, CDP cache clear | `tools/browser/cloak.py` + `PlaywrightWebDriver.{enable_stealth,set_user_agent,set_extra_headers,set_proxy,clear_cache}` | dispatch tests |
| **Network interception** — `page.route()` shim with log/block modes + mock_response + wait_for_response + buffered request log | `tools/browser/network.py` | dispatch tests |
| **Adopt references honoured** — browser-use (MIT) registry-decorator pattern + stagehand (MIT) 4-method API + CloakBrowser (MIT) stealth init scripts. **Skyvern (AGPL) — fikir-only, no code copied** | docstrings + Faz 2 ADR-010 §9.9 entry | — |
| **Registry integration** | `tools/__init__.py::build_default_registry` adds `*build_browser_tools()` — 221 total (158 post-Faz-1 + 63 browser), 76 eager + 145 deferred | +9 (registry shape pinned) |

**Faz 2 close baseline:** 2905 backend tests pass (was 2808 post-Faz 1; net +97
including 9 args-validation regression for the renamed `extraction_schema`
field). ruff/mypy(303)/tsc clean. Registry **221 tools** (76 eager + 145
deferred). Operator commit per MANDATE 1.

**Tool count vs scope target** (ADR-010 §9.3 = ~60 tools): **63 browser tools
shipped** — 11 interaction + 9 navigation + 11 observation + 6 tabs + 6
storage + 5 intelligent + 5 cloak + 5 network + 5 device. Eager bucket (10)
mirrors mobile pattern — `browser_navigate/click/type/press_key/screenshot/
dom_snapshot/text_content/evaluate/wait_for_load_state/get_url`. Deferred
bucket (53) reachable via `tool_search`.

### 9.10 Faz 2 Format Freeze additions

Pinned wire-format items (breaking change = retraining):

| Item | Site | Notes |
|---|---|---|
| `browser_*` tool name prefix | `tools/browser/**` | Reserves the prefix for Faz 2+ browser growth |
| `PlaywrightWebDriver.platform == "web"` marker | `selffork_body/drivers/web/playwright_driver.py` | Required by `_require_browser_driver` in `tools/browser/_internal.py` |
| Body action_type taxonomy: `browser.*` | every browser handler's `_invoke_browser(action_type=…)` call | Audit consumers + Heartbeat correction-ingest depend on the dotted form |
| `SELFFORK_BODY_PLATFORM=web` and `SELFFORK_BODY_BROWSER_HEADLESS` env keys | `mobile_factory.py::build_default_body_driver` | Operator-facing knobs |
| `BrowserExtractArgs.extraction_schema` (renamed from `schema` to avoid Pydantic BaseModel shadowing) | `tools/browser/intelligent.py` | Pydantic warned about the parent attribute clash |

### 9.11 Faz 2 Status

**S-ToolFleet Faz 2 Browser Wave — ACCEPTED 2026-05-26 night.** Browser fleet
shipped enterprise-grade in the same session as Faz 1.

### 9.12 Faz 3 Cross-cutting Wave deliverables (✅ all shipped 2026-05-26 night, single session)

Operator directive: **"faz 1 ve faz 2 den %100 emin isen kendinden faz 3 ile devam edebilirsin!"** — same session as Faz 1+2, single-session close.

| Item | Site | Tests |
|---|---|---|
| **macos platform wire** — `resolve_platform()` accepts `macos`/`desktop`; factory builds `MacOSDesktopDriver` for `SELFFORK_BODY_PLATFORM=macos` | `selffork_body/drivers/mobile_factory.py` | reused F1 wire tests |
| **MacOSDesktopDriver +11 methods** — double_click/right_click/screenshot_region/get_active_app/list_apps/list_windows/focus_window/get_clipboard/set_clipboard/notification/say + `platform = "macos"` marker | `selffork_body/drivers/desktop/macos/driver.py` | included in handler dispatch |
| **Desktop tool pack** — 15 tools: click/double_click/right_click/type/press_key/screenshot/screenshot_region/get_active_app/list_apps/list_windows/focus_window/get_clipboard/set_clipboard/notification/say. Eager bucket = 5 (click/type/screenshot/press_key/get_active_app) | `tools/desktop/{__init__,_internal,tools}.py` | +15 handler dispatch |
| **GitHub tool pack** — 16 tools: repo_list/view/clone/fork/create + issue_list/create/view/comment/close + pr_list/create/view/merge + workflow_list/run. Eager = 3 (pr_create/issue_create/issue_list — self-commit core). gh CLI subprocess wrap with warden gate (no driver req); PAT auth via `~/.config/gh/hosts.yml` per [[s-vision-candidates-github-rag-2026-05-24]] | `tools/github/{__init__,_internal,tools}.py` | +4 mock-gh dispatch + 7 args + registry |
| **Skills tool pack** — 10 tools: list/show/sync/install/uninstall/update/search/validate/export/create. All deferred (operator dev-time). Wraps `selffork_orchestrator.skills.SkillInstaller` (canonical-dir + symlink fan-out to four CLI targets); `skill_sync` accepts custom `target_dirs` for test isolation | `tools/skills/{__init__,tools}.py` | +12 filesystem dispatch + 3 args |
| **Registry integration** | `tools/__init__.py::build_default_registry` adds `*build_desktop_tools()` + `*build_github_tools()` + `*build_skills_tools()` — **262 total** (158 post-Faz-1 + 63 browser + 41 Faz 3), 84 eager + 178 deferred | +10 registry shape pinned |

**Faz 3 close baseline:** 2967 backend tests pass (was 2905 post-Faz 2; net +62 new tests). ruff/mypy(311)/tsc clean. Registry **262 tools** (84 eager + 178 deferred). Operator commit per MANDATE 1.

**Tool count vs scope target** (ADR-010 §9.3 = ~40 tools): **41 Faz 3 tools shipped** — 15 desktop + 16 github + 10 skills. Eager bucket (8) keeps Self Jr's prompt lean — desktop top-5 + GitHub self-commit + status checks (3). Deferred bucket (33) reachable via `tool_search`.

**Test pollution fix landed Faz 3:** earlier `skill_sync` always used `default_target_cli_dirs()` which wrote to the user's real `~/.claude/skills` etc. Made `target_dirs` an explicit arg + cleaned up the `syncme` symlink leak.

### 9.13 Faz 3 Format Freeze additions

| Item | Site | Notes |
|---|---|---|
| `desktop_*`/`github_*`/`skill_*` tool name prefixes | `tools/{desktop,github,skills}/**` | Reserves three new prefixes for Faz 3+ growth |
| `MacOSDesktopDriver.platform == "macos"` marker | `selffork_body/drivers/desktop/macos/driver.py` | Required by `_require_macos_driver` |
| Body action_type taxonomy: `desktop.*` / `github.*` / `skill.*` | every handler's `action_type=…` call | Audit consumers + Heartbeat correction-ingest |
| `SELFFORK_BODY_PLATFORM=macos` (alias `desktop`) env value | `mobile_factory.py::resolve_platform` | Operator-facing knob; `desktop` is alias for `macos` |
| `SkillSyncArgs.target_dirs` override | `tools/skills/tools.py` | Test/operator safety; default = four-CLI fan-out |

### 9.14 Faz 3 Status

**S-ToolFleet Faz 3 Cross-cutting Wave — ACCEPTED 2026-05-26 night.**

### 9.15 Faz 4 VR/AR Wave deliverables (✅ all shipped 2026-05-26 night, single session)

Operator directive: **"faz 1 ve faz 2 ve faz 3 den kesin kesin eminsen faz 4 e başla!!"** — closing the 5-Faz plan in one session.

Per §9.1 #3 operator lock: Quest 3 = Android ADB+MQDH full driver (~20 tool), Vision Pro = Gemma 4 VLM OCR vision-only (~5-8 tool), modalite-çift kabul.

| Item | Site | Tests |
|---|---|---|
| **Quest platform wire** — `resolve_platform()` accepts `quest`/`quest3`; factory builds `QuestDriver(AndroidDriver)` for `SELFFORK_BODY_PLATFORM=quest`; `SELFFORK_BODY_QUEST_DEVICE` env knob | `mobile_factory.py` + `selffork_body/drivers/vr/quest.py` | reused wire tests |
| **VisionPro platform wire** — `resolve_platform()` accepts `visionpro`/`visionos`; factory builds `VisionProDriver` for `SELFFORK_BODY_PLATFORM=visionpro` | `mobile_factory.py` + `selffork_body/drivers/vr/visionpro.py` | reused wire tests |
| **QuestDriver class** — inherits `AndroidDriver`, sets `platform = "quest"`, adds 14 VR-specific methods: recenter / passthrough_enable+disable / press_meta_button / press_controller_button (a/b/x/y/grip/trigger/thumbstick × left/right) / get_combined_battery (headset + controllers via OVRRuntime dumpsys) / get_device_info / get_boundary_status (Guardian) / record_video / stop_record_video / voice_command / list_installed_vr_apps / device_summary | `selffork_body/drivers/vr/quest.py` | included in handler dispatch |
| **VisionProDriver class** — wraps `IosSimulatorRuntime` (visionOS sim uses same simctl surface) + AppleScript pointer for host-Mac clicks; `platform = "visionpro"`; methods: screenshot / simulator_list+boot+shutdown (filtered by visionOS runtime) / app_launch / get_logs / click_at | `selffork_body/drivers/vr/visionpro.py` | dispatch tests |
| **`_require_android_driver` broadened to accept Quest** — `platform in ("android", "quest")` so `android_*` tools work transparently on Quest (Android-derived OS) | `tools/mobile/_internal.py` | regression-safe |
| **Quest tool pack** — 19 tools: screenshot/app_launch/recenter (eager-3), + app_terminate/app_list/list_vr_apps/install_apk/uninstall_app/passthrough_enable+disable/press_meta_button/press_controller_button/get_battery/device_info/get_boundary/logcat/record_video/stop_record_video/voice_command (deferred-16) | `tools/vr/{__init__,_internal,quest}.py` | +19 handler dispatch + 5 args |
| **VisionPro tool pack** — 8 tools (all deferred): simulator_list/boot/shutdown + screenshot + app_launch + get_logs + find_text (LLM OCR via vision_runtime; returns "unwired" without) + click_at (AppleScript pointer) | `tools/vr/visionpro.py` | +8 handler dispatch + 4 args |
| **Registry integration** | `tools/__init__.py::build_default_registry` adds `*build_vr_tools()` — **289 total** (262 post-Faz-3 + 27 VR), 87 eager + 202 deferred | +9 registry shape pinned |

**Faz 4 close baseline:** 3019 backend tests pass (was 2967 post-Faz 3; net +52 new tests). ruff/mypy(318)/tsc clean. Registry **289 tools** (87 eager + 202 deferred). Operator commit per MANDATE 1.

**Tool count vs scope target** (ADR-010 §9.3 = ~25 tools, §9.1 #3 = Quest ~20 + VP ~5-8): **27 VR tools shipped** — 19 Quest + 8 VisionPro. Quest eager-3 (screenshot/app_launch/recenter) covers the VR observe→act loop; all VisionPro deferred (niche modality). Honest reality: Quest gets the full ADB driver, Vision Pro stays vision-only as locked.

### 9.16 Faz 4 Format Freeze additions

| Item | Site | Notes |
|---|---|---|
| `quest_*` / `visionpro_*` tool name prefixes | `tools/vr/**` | Two prefixes reserved |
| `QuestDriver.platform == "quest"` + `VisionProDriver.platform == "visionpro"` markers | `selffork_body/drivers/vr/{quest,visionpro}.py` | Required by `_require_quest_driver` / `_require_visionpro_driver` |
| Body action_type taxonomy: `quest.*` / `visionpro.*` | every VR handler's `action_type=…` call | Audit consumers + Heartbeat correction-ingest |
| `SELFFORK_BODY_PLATFORM=quest` (alias `quest3`) + `=visionpro` (alias `visionos`, `vision-pro`) env values | `mobile_factory.py::resolve_platform` | Operator-facing knobs |
| `SELFFORK_BODY_QUEST_DEVICE` + `SELFFORK_BODY_VISIONPRO_DEVICE` env keys | `mobile_factory.py::build_default_body_driver` | Device serial / UDID overrides |
| `_require_android_driver` accepts `("android", "quest")` | `tools/mobile/_internal.py` | Quest IS-A Android so all `android_*` tools work on Quest transparently; breaking this contract = retraining |

### 9.17 Faz 4 Status — S-ToolFleet 5-Faz Plan COMPLETE

**S-ToolFleet Faz 4 VR/AR Wave — ACCEPTED 2026-05-26 night.** The full
5-Faz plan from §9.3 is now closed in a single session:

| Faz | Status | Tool delta | Net registry |
|---|---|---|---|
| **Faz 0** — substrate solidify | ✅ ACCEPTED (earlier session) | seam only | 36 |
| **Faz 1** — Mobile Wave | ✅ ACCEPTED (same session) | +122 | 158 |
| **Faz 2** — Browser Wave | ✅ ACCEPTED (same session) | +63 | 221 |
| **Faz 3** — Cross-cutting (Desktop + GitHub + Skills) | ✅ ACCEPTED (same session) | +41 | 262 |
| **Faz 4** — VR/AR (Quest + Vision Pro) | ✅ ACCEPTED (same session) | +27 | **289** |
| **Total** | 5-Faz complete | **+253** | **289** |

Substrate now spans 8 platforms (ios/android/web/macos/quest/visionpro + composite + the original surfaces). RAG-over-tools seam amortises the 202 deferred specs behind `tool_search`. The "tool count target ~250-380" from [[s-vision-candidates-github-rag-2026-05-24]] is hit at the lower end with quality intact.

Next milestone: M7 freeze with the full fleet, plus the S-Train sprint that uses the Format Freeze (§5 + §9.7/9.10/9.13/9.16) as the fine-tune corpus stabilization gate.
