# ADR-011 — Self Jr Slow-Inference Resilience (Streaming / Async / No-Hang)

**Status:** Accepted + Implemented (2026-05-26, "S-Stream" sprint — Faz 1-5)
**Supersedes:** none · **Augments:** ADR-001 (runtime), ADR-007 §4 S1 (Talk), ADR-008 (Heartbeat)
**Note:** ADR-010 is reserved for the S-Vision sprint (vision lock); this concern surfaced
during the S8 live bring-up and is numbered 011 to avoid disturbing that reservation.

## 1. Context — what the live test surfaced

Bringing the full stack up for S8 verification (operator request, 2026-05-25) exposed a
**system-level robustness gap**, independent of S8's feature scope (which is code-complete +
green). Self Jr's local model — the Gemma 4 E2B **VLM**, served by `mlx_vlm.server` — runs on
operator hardware, and the operator's target deployment is **CPU** where a single generation
can take **minutes to hours**. Two facts collided:

1. **Every Self-Jr inference call-site is synchronous-blocking with a fixed timeout.** A
   generation that takes hours blocks the HTTP request for hours → httpx/proxy/browser timeouts
   fire (the request *fails*), the Talk UI shows `Self Jr is thinking…` **forever** with no
   partial output, no progress, and no cancel. This is the failure the operator flagged
   verbatim: *"CPU'da çalıştırıcam, yanıt süresi saatler bile sürebilir — bu sıkıntılar ve daha
   kötüleri olmamalı."*

2. **A wrong-runtime hang is silent.** The Gemma 4 base is multimodal; `mlx_lm.server`
   (text-only) loads its weights but **hangs on inference** with no error (documented in
   `runtime/mlx_server.py:11`). The correct runtime is `mlx_vlm.server`. A mis-pointed endpoint
   therefore presents identically to a slow generation — an indefinite hang — so the system
   cannot today distinguish "slow but alive" from "wedged."

The slow surface is **only Self Jr's local model**. The CLI coders (claude-code / codex /
gemini-cli / opencode) run on their own cloud LLMs and stay fast ([[four-clis-dont-forget-opencode]]).
So resilience work is scoped precisely to Self Jr's inference seams.

## 2. The three inference call-sites (all blocking today)

| # | Call-site | Path | Current behaviour |
|---|---|---|---|
| 1 | **Talk** | `dashboard/talk_router._invoke_speaker` → `SpeakerClient.reply()` (`talk/speaker.py:36`, `"stream": False`) | one blocking httpx POST, fixed `_DEFAULT_TIMEOUT_SECONDS`; `POST /api/talk/send` holds the whole generation |
| 2 | **Heartbeat** | `heartbeat/deliberation.DeliberationLayer.select()` → same `Speaker` Protocol (`deliberation.py:130`) | blocking; a slow tick stalls the autonomy loop; falls back to `WAIT` only on error/parse-fail |
| 3 | **Round-loop** | `lifecycle/session` → `runtime/mlx_server.MlxServerRuntime.chat()` (`/v1/chat/completions`) | blocking POST, fixed chat timeout; the Jr-reply step of each round |

The `Speaker` Protocol is the clean seam for (1)+(2); `MlxServerRuntime.chat` for (3).

## 3. Decision

Make **all Self-Jr inference streaming, non-blocking, and un-timeout-able-to-failure**, with
live progress and operator/budget cancellation. Concretely:

1. **Streaming generation.** Add a streaming mode to the `Speaker` Protocol +
   `MlxServerRuntime.chat` using mlx's OpenAI `stream: true` (SSE). Tokens are consumed as
   produced. Even at hours-per-reply on CPU, tokens *trickle* — the operator always sees liveness.

2. **Non-blocking transport.** `POST /api/talk/send` no longer holds the full generation. The
   operator message persists immediately; Self Jr's reply **streams over the existing Talk
   WebSocket** (`openTalkStream`, S1) as `talk.token` frames, finalised by a `talk.message`
   frame. No HTTP request is held open for the generation lifetime.

3. **No premature timeout.** Replace the single fixed httpx timeout with a split policy:
   short **connect** timeout (detect a down endpoint fast) + **no/very-generous read** timeout
   guarded by an **idle-token watchdog** — if no token arrives for `stall_seconds` (configurable,
   default generous), the generation is declared stalled and cancelled with an honest error;
   otherwise it may run for hours. "Slow but alive" (tokens flowing) ≠ "wedged" (idle watchdog).

4. **Progress + cancel.** Talk UI renders the partial reply growing + a `generating… (N tokens ·
   M elapsed)` affordance + a **Stop** button (cancels the stream + the upstream generation).
   Heartbeat deliberation runs as a **cancellable task** with a per-tick budget so a slow model
   never wedges the autonomy loop (budget exceeded → honest `WAIT` + audit `deliberation_stalled`).

5. **Wrong-runtime detection.** On runtime spin-up, detect the `mlx_lm`-on-VLM hang class
   (unmatched-weights warning / no token within a bounded warmup probe) and surface a clear
   `runtime_misconfigured` error instead of an indefinite silent hang. Document the canonical
   spawn (`python -m mlx_vlm.server --model <id>`) as the only supported form.

## 4. Pillar impact (MANDATE 7)

- **Reflex:** the M7 fine-tune corpus should include the streaming wire shape; Self Jr's replies
  are consumed token-wise, not as one blob. No loss-strategy change (1.0/0.3/0.0 unchanged).
- **Body:** unaffected (Body drivers are separate from the language runtime).
- **Mind:** Talk messages still persist to the Talk store + audit on stream completion; partial
  streams that are cancelled persist what was produced + a `cancelled` marker (no fabricated reply).

## 5. Won't-have (explicit)

- **No short hard generation cap.** Capping at e.g. 60s would fail valid CPU generations — the
  exact thing the operator forbade. The idle-token watchdog replaces the wall-clock cap.
- **No fabricated/placeholder reply** on slowness (no-mock — [[no-mvp-full-quality-first-time]]).
- **No speculative multi-model fallback** (e.g. auto-swap to a tiny model) in this ADR — it is a
  separate vision decision; here we make the chosen model's slowness *survivable*, not hidden.

## 6. Implementation order (dedicated sprint — "S-Stream")

Each step ships production-quality (streaming + tests) on landing — no MVP staging:

1. `Speaker` streaming variant (SSE consume) + idle-token watchdog + split timeout; unit tests
   with a mock SSE transport (fast + stalled + cancelled cases).
2. Talk: WS `talk.token`/`talk.message` frames; `POST /api/talk/send` returns on enqueue;
   frontend partial-render + progress + Stop.
3. `MlxServerRuntime.chat` streaming + warmup wrong-runtime probe + `runtime_misconfigured`.
4. Heartbeat deliberation as a cancellable per-tick-budget task; `deliberation_stalled` audit.
5. Smoke + audit-god; CPU-slow simulation test (artificially throttled SSE) proving no hang,
   live progress, working cancel.

**Dependency / sequence:** independent of S-Vision's feature scope but should land **before
M7** so the fine-tune corpus + the round-loop both assume the streaming contract. Proposed slot:
alongside/after S-Vision, before S-ToolFleet (tool round-trips also benefit from streaming).

## 7. Status / approval

Proposed 2026-05-25 after the S8 live bring-up surfaced the blocking-inference hang on a
CPU-bound deployment. **Implemented 2026-05-26 in the "S-Stream" sprint** (operator directive:
do it this session). The S8 feature set is unaffected (code-complete + green); this ADR is
additive system-resilience.

## 8. Implementation record (S-Stream, 2026-05-26)

All five §6 steps shipped production-quality (streaming + tests, no MVP staging):

1. **Speaker streaming variant.** New `selffork_orchestrator.runtime.sse` module owns the shared
   OpenAI-SSE vocabulary (`TokenChunk` / `StreamDone` / `StreamEvent`) + the idle-token watchdog
   (`stalling_aiter`) + the consume loop (`stream_openai_sse`). `SpeakerClient.reply_stream`
   consumes it; `SpeakerClient.reply` is now a thin aggregator over the stream (back-compat
   preserved). Split timeout (`connect` short, `read=None`). New `SpeakerStalledError`
   distinguishes "wedged" from "slow but alive". 17 unit tests (mock SSE: fast / stalled /
   cancelled / heartbeat-lines / watchdog-disabled).
2. **Talk non-blocking transport.** `POST /api/talk/send` returns `speaker_status="streaming"`
   + a `generation_id` immediately (operator message persisted + broadcast); the reply streams
   over the Talk WS as `talk.token` frames, finalised by `talk.message` (success), `talk.error`
   (transport/stall — no fabricated reply), or `talk.cancelled` (operator Stop, partial persisted).
   New `_TalkBroadcaster` pub/sub (per-conversation, replay-buffer integrated, seq-deduped).
   New `POST /conversations/{cid}/cancel-generation/{gid}`. Frontend: growing reply bubble +
   `generating… (N tokens · Ms)` + Stop button + seq-dedup on reconnect. 23 router tests.
3. **MlxServerRuntime streaming + warmup probe.** `chat_stream` (shares `runtime.sse`); `chat`
   aggregates it (the round-loop now inherits the idle watchdog → no infinite hang).
   `warmup_probe()` detects the `mlx_lm`-on-VLM silent-hang class → `RuntimeMisconfiguredError`
   with the canonical-spawn fix; opt-in at spin-up via `SELFFORK_MLX_WARMUP`. 18 runtime tests.
4. **Heartbeat cancellable per-tick budget.** `DeliberationLayer` gained `tick_budget_seconds`
   (default 300s, env `SELFFORK_HEARTBEAT_DELIBERATION_BUDGET_SECONDS`); `select()` catches
   `SpeakerStalledError` (watchdog) + `TimeoutError` (budget) → honest stalled `WAIT`.
   `ActionDecision.stalled` + `AuditEntry.decision_stalled` surface "loop stayed alive through a
   slow tick" distinctly from unreachable/unparseable. Deliberation + audit tests.
5. **No-hang / liveness / cancel proof.** The CPU-slow simulation is covered by throttled-SSE
   tests across the seams: idle-watchdog-fires-when-stalled, slow-but-under-budget-completes,
   cancellation-propagates-without-hang (speaker), `_SlowSpeaker` mid-stream cancel +
   stalled-error (Talk router), idle-watchdog + warmup (mlx). Smoke: `M6_Smoke_Checklist § S-Stream`.

**Env knobs added:** `SELFFORK_MLX_WARMUP` (opt-in spin-up wrong-runtime probe),
`SELFFORK_HEARTBEAT_DELIBERATION_BUDGET_SECONDS` (per-tick budget override).

İlgili: [[s8-complete-2026-05-25]], [[four-clis-dont-forget-opencode]], ADR-001 (runtime),
ADR-007 §4 S1 (Talk loop), ADR-008 (Heartbeat deliberation), `runtime/mlx_server.py`,
`talk/speaker.py`, `heartbeat/deliberation.py`.
