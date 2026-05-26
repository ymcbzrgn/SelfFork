"""Session — orchestrates one ``selffork run`` invocation end-to-end.

Drives the state machine from :class:`SessionState.IDLE` to
:class:`SessionState.TORN_DOWN`, wiring together the runtime, sandbox,
CLI agent, plan store, and audit logger. Every state transition emits a
``session.state`` audit event; every cross-component step emits its own
``runtime.*`` / ``sandbox.*`` / ``agent.*`` / ``plan.*`` event.

Teardown always runs (try/finally), even on exceptions — so the runtime
process and sandbox container never leak.

See: ``docs/decisions/ADR-001_MVP_v0.md`` §6.
"""

from __future__ import annotations

import contextlib
import json
import os
import time
from typing import Protocol

from selffork_body.sandbox.destructive_whitelist import DestructiveWhitelist
from selffork_body.sandbox.pending_confirmations import (
    PendingConfirmationStore,
)
from selffork_mind.memory.tiers import (
    EpisodicToolCall,
    EpisodicWriter,
)
from selffork_mind.rag.retriever import HybridRetriever
from selffork_mind.store.base import MindStore
from selffork_orchestrator.cli_agent.base import CLIAgent
from selffork_orchestrator.cli_agent.structured_tools import is_structured_question
from selffork_orchestrator.lifecycle.destructive_guard import (
    DestructiveActionBlockedError,
    check_destructive_action,
)
from selffork_orchestrator.lifecycle.states import (
    SessionState,
    is_legal_transition,
)
from selffork_orchestrator.lifecycle.stuck_detector import (
    RecoveryAction,
    StepObservation,
    StuckDetector,
    hash_observation,
    normalize_tool_key,
)
from selffork_orchestrator.limits.base import (
    AuthRequired,
    LimitDetector,
    NoLimit,
    RateLimited,
)
from selffork_orchestrator.plan.model import Plan
from selffork_orchestrator.plan.store_base import PlanStore
from selffork_orchestrator.runtime.base import ChatMessage, LLMRuntime
from selffork_orchestrator.sandbox.base import Sandbox
from selffork_orchestrator.spawn.sentinel import (
    SpawnRequest,
    extract_spawn_requests,
)
from selffork_orchestrator.theater.producer import (
    NullTheaterProducer,
    TheaterProducer,
)
from selffork_orchestrator.tools.base import (
    ToolCall,
    ToolContext,
    ToolRegistry,
    ToolResult,
)
from selffork_orchestrator.tools.parser import parse_tool_calls
from selffork_shared.audit import AuditLogger
from selffork_shared.config import LifecycleConfig
from selffork_shared.errors import SelfForkError
from selffork_shared.logging import bind_session_id, get_logger

__all__ = ["RateLimitHandler", "Session", "SpawnHandler"]

_log = get_logger(__name__)


class RateLimitHandler(Protocol):
    """Callback invoked when a CLI agent hits a subscription rate limit.

    The handler is responsible for persisting whatever record the
    ``selffork resume`` daemon needs to resurrect the session at
    ``verdict.reset_at``. The orchestrator does NOT manage that store
    directly — keeping persistence concerns at the CLI layer where the
    necessary metadata (config_path, prd_path, ...) lives.

    Implementations MUST be ``async`` and short — Session is mid-loop
    when this fires, and we want to tear down promptly.
    """

    async def __call__(
        self,
        *,
        session_id: str,
        verdict: RateLimited,
        last_round_text: str,
    ) -> None: ...


class SpawnHandler(Protocol):
    """Callback invoked when parent Jr emits one or more SPAWN sentinels.

    Synchronous-blocking semantics: implementations spawn N children,
    wait for ALL to finish, and return one aggregated user-role text
    that the parent's next round will see. The aggregator format is
    the implementation's call — typically a plain ``=== Child <i> ===``
    delimited transcript.

    The orchestrator does NOT manage child sandboxes / tmux panes / the
    shared MLX runtime — those concerns live at the cli.py boundary
    where the parent's runtime port + config path are already known.
    """

    async def __call__(
        self,
        *,
        parent_session_id: str,
        requests: list[SpawnRequest],
    ) -> str: ...


class Session:
    """End-to-end orchestration of one ``selffork run``.

    Construct with all five collaborators wired (runtime, sandbox, CLI
    agent, plan store, audit logger) plus the in-sandbox path the agent
    will see for the plan file. Call :meth:`run` once; the returned
    :class:`SessionState` is the terminal outcome (``COMPLETED`` or
    ``FAILED``) before teardown.
    """

    def __init__(
        self,
        *,
        session_id: str,
        prd_text: str,
        prd_path: str,
        plan_path_in_sandbox: str,
        runtime: LLMRuntime,
        sandbox: Sandbox,
        cli_agent: CLIAgent,
        plan_store: PlanStore,
        audit_logger: AuditLogger,
        lifecycle_config: LifecycleConfig,
        limit_detector: LimitDetector | None = None,
        rate_limit_handler: RateLimitHandler | None = None,
        spawn_handler: SpawnHandler | None = None,
        tool_registry: ToolRegistry | None = None,
        project_slug: str | None = None,
        project_store: object | None = None,
        episodic_writer: EpisodicWriter | None = None,
        mind_retriever: HybridRetriever | None = None,
        mind_store: MindStore | None = None,
        cli_agent_name: str | None = None,
        proactive_reader: object | None = None,
        launchd_scheduler: object | None = None,
        resume_store: object | None = None,
        telegram_bridge: object | None = None,
        cli_override_store: object | None = None,
        cli_runtime_store: object | None = None,
        theater_producer: TheaterProducer | None = None,
        destructive_whitelist: DestructiveWhitelist | None = None,
        pending_store: PendingConfirmationStore | None = None,
        stuck_detector: StuckDetector | None = None,
        structured_question_store: object | None = None,
    ) -> None:
        self._session_id = session_id
        self._prd_text = prd_text
        self._prd_path = prd_path
        self._plan_path_in_sandbox = plan_path_in_sandbox
        self._runtime = runtime
        self._sandbox = sandbox
        self._cli_agent = cli_agent
        self._plan_store = plan_store
        self._audit = audit_logger
        self._lifecycle_config = lifecycle_config
        self._limit_detector = limit_detector
        self._rate_limit_handler = rate_limit_handler
        self._spawn_handler = spawn_handler
        self._tool_registry = tool_registry
        self._project_slug = project_slug
        self._project_store = project_store
        self._episodic_writer = episodic_writer
        self._mind_retriever = mind_retriever
        self._mind_store = mind_store
        self._cli_agent_name = cli_agent_name
        # Jr autopilot subsystem dependencies. All optional — None when
        # the corresponding subsystem isn't wired (e.g. snappers off,
        # non-macOS host without launchd, Telegram bridge disabled).
        self._proactive_reader = proactive_reader
        self._launchd_scheduler = launchd_scheduler
        self._resume_store = resume_store
        self._telegram_bridge = telegram_bridge
        # S6 (ADR-006 §4.6) — Self-Jr-mutable CLI-router control stores.
        self._cli_override_store = cli_override_store
        self._cli_runtime_store = cli_runtime_store
        # S-Bridge CORE — pending structured-question store handed to
        # the ``AskUserQuestion`` tool. ``None`` ⇒ tool reports
        # ``status="unwired"`` and Self Jr proceeds without operator
        # input. Producer side awaits, consumer side (Telegram
        # ``/answer`` or REST POST) fires the asyncio.Event.
        self._structured_question_store = structured_question_store
        # Theater producer — best-effort Live Run surface (ADR-007 §4 S2).
        # Null Object default so the round loop never branches on None.
        self._theater: TheaterProducer = theater_producer or NullTheaterProducer()
        # Destructive guard — ADR-006 §4.5 + ADR-007 §4 S3. Both pieces
        # are optional: when either is None the warden hook becomes a
        # no-op (no whitelist loaded → orphan/test runs still execute).
        self._destructive_whitelist = destructive_whitelist
        self._pending_store = pending_store
        # S-Vision (ADR-010 §2.2) — deterministic agentic-loop stuck-detector.
        # ``None`` disables detection (existing tests / orphan runs); cli.py
        # injects a live detector so production runs are guarded.
        self._stuck_detector = stuck_detector
        self._state: SessionState = SessionState.IDLE
        self._failure_reason: str | None = None
        # Rounds the agent loop completed — read after :meth:`run` for the
        # ADR-006 §4.6 turn-to-complete affinity metric (S6).
        self._rounds_completed: int = 0

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def failure_reason(self) -> str | None:
        return self._failure_reason

    @property
    def rounds_completed(self) -> int:
        """Agent-loop rounds completed (S6 affinity turn-to-complete)."""
        return self._rounds_completed

    async def run(self) -> SessionState:
        """Drive the lifecycle and return the pre-teardown terminal state.

        On return, ``self.state`` is :class:`SessionState.TORN_DOWN`. The
        meaningful outcome is the value returned (``COMPLETED``,
        ``FAILED``, or ``PAUSED_RATE_LIMIT``).
        """
        bind_session_id(self._session_id)
        outcome: SessionState = SessionState.FAILED
        try:
            await self._prepare()
            await self._run_agent()
            # _run_agent may have transitioned to PAUSED_RATE_LIMIT mid-loop;
            # in that case skip verification — the session isn't done, it's
            # parked until ``selffork resume`` brings it back.
            if self._state != SessionState.PAUSED_RATE_LIMIT:
                await self._verify()
            outcome = self._state  # COMPLETED | FAILED | PAUSED_RATE_LIMIT
        except DestructiveActionBlockedError as exc:
            # S3 audit fix #12: preserve category + command context so
            # the audit / Live Run hero shows *why* the loop stopped,
            # not just "cancelled".
            entry = exc.entry
            reason = (
                f"destructive_{exc.reason}: "
                f"{entry.category_id if entry else '?'}/"
                f"{entry.command_summary if entry else '?'}"
            )
            self._fail(reason=reason)
            outcome = SessionState.FAILED
        except SelfForkError as exc:
            self._fail(reason=str(exc))
            outcome = SessionState.FAILED
        except BaseException as exc:
            # Unexpected non-SelfFork error — record and fail cleanly.
            _log.exception("session_unexpected_error")
            self._fail(reason=f"unexpected error: {type(exc).__name__}: {exc}")
            outcome = SessionState.FAILED
            raise
        finally:
            await self._theater.loop_ended()
            await self._teardown()
        return outcome

    # ── Phases ────────────────────────────────────────────────────────────

    async def _prepare(self) -> None:
        self._transition(SessionState.PREPARING)
        await self._runtime.start()
        self._audit.emit(
            "runtime.spawn",
            payload={
                "model": self._runtime.model_id,
                "base_url": self._runtime.base_url,
            },
        )

        await self._sandbox.spawn()
        self._audit.emit(
            "sandbox.spawn",
            payload={
                "workspace_path": self._sandbox.workspace_path,
                "host_workspace_path": self._sandbox.host_workspace_path,
            },
        )

        plan = Plan.new(session_id=self._session_id, prd_path=self._prd_path)
        await self._plan_store.save(plan)
        self._audit.emit(
            "plan.save",
            payload={"subtask_count": len(plan.subtasks), "initial": True},
        )

    async def _run_agent(self) -> None:
        """Round loop: SelfFork Jr ↔ CLI agent until session-end sentinel.

        Each iteration:
          1. Ask SelfFork Jr (LLMRuntime.chat) for the next message based on
             current history.
          2. Check if the reply contains the ``[SELFFORK:DONE]`` sentinel
             — if so, stop without invoking the CLI agent.
          3. Otherwise, run the CLI subprocess with that message, capture
             its stdout, and append both the SelfFork-Jr reply (assistant)
             and the captured CLI output (user) to the chat history.
          4. Repeat until SelfFork Jr emits ``[SELFFORK:DONE]``. If
             :attr:`LifecycleConfig.max_rounds` is set (None = unlimited),
             the loop also bails out after that many rounds.
        """
        self._transition(SessionState.RUNNING)
        await self._theater.loop_started()
        binary = self._cli_agent.resolve_binary()
        env = self._cli_agent.build_env(base_env=os.environ)
        # S6 (ADR-006 §4.6): let the agent prep the host workspace before the
        # round loop (gemini-cli writes its settings-file thinking config;
        # other agents no-op). Host path = the CLI's cwd on disk.
        self._cli_agent.prepare_workspace(self._sandbox.host_workspace_path)

        history: list[ChatMessage] = self._cli_agent.compose_initial_messages(
            prd=self._prd_text,
            plan_path=self._plan_path_in_sandbox,
            workspace=self._sandbox.workspace_path,
        )
        self._audit.emit(
            "agent.spawn",
            payload={
                "binary": binary,
                "selffork_jr_model": self._runtime.model_id,
                "initial_messages_count": len(history),
            },
        )

        is_first_round = True
        rounds_completed = 0
        # ``None`` ⇒ unlimited (production default). A positive int caps
        # the loop, used by tests / safety drills.
        # See ``LifecycleConfig.max_rounds`` for the rationale.
        max_rounds = self._lifecycle_config.max_rounds
        # ADR-010 §2.2 agentic-loop hard caps. ``action_count`` counts each
        # completed round (an "action"); the wall-clock guard is opt-in
        # (default off — ADR-011 §5 forbids killing a slow CPU generation).
        loop_started_at = time.monotonic()
        action_count = 0

        while max_rounds is None or rounds_completed < max_rounds:
            # Snapshot progress so the post-run affinity write (ADR-006
            # §4.6 turn-to-complete metric, S6) reflects completed rounds
            # on every exit path (DONE sentinel, error, max-rounds).
            self._rounds_completed = rounds_completed
            self._enforce_loop_caps(action_count, loop_started_at)
            # Greedy decoding for the small SelfFork Jr model. Stochastic
            # sampling on a 2B Q4 model produces wildly variable replies
            # — including pathological ones (immediate sentinel, empty
            # output). Deterministic for now; M7 fine-tune may revisit.
            yamac_reply = await self._runtime.chat(
                history,
                temperature=0.0,
                max_tokens=512,
            )
            self._audit.emit(
                "selffork_jr.reply",
                payload={
                    "round": rounds_completed,
                    "text": yamac_reply,
                    "chars": len(yamac_reply),
                },
            )
            await self._theater.thought(yamac_reply, turn=rounds_completed)

            if self._cli_agent.is_selffork_jr_done(yamac_reply):
                self._audit.emit(
                    "agent.done",
                    payload={
                        "reason": "selffork_jr_sentinel",
                        "rounds": rounds_completed,
                    },
                )
                return

            spawn_requests = extract_spawn_requests(yamac_reply)
            if spawn_requests:
                aggregated = await self._handle_spawn(
                    rounds_completed=rounds_completed,
                    requests=spawn_requests,
                )
                history.append({"role": "assistant", "content": yamac_reply})
                history.append({"role": "user", "content": aggregated})
                await self._record_episodic_round(
                    round_index=rounds_completed,
                    operator_message=yamac_reply,
                    cli_response=aggregated,
                    sentinels=["[SELFFORK:SPAWN:"],
                )
                rounds_completed += 1
                action_count += 1
                is_first_round = False
                self._observe_round(
                    tool_key="spawn",
                    observation_text=aggregated,
                    succeeded=True,
                    history=history,
                )
                continue

            # Tool calls (e.g. <selffork-tool-call> ... kanban_card_done ...)
            # are handled BEFORE the CLI exec because the typical Jr-with-
            # tools turn looks like "I'm marking card X done; now please
            # proceed". The tool result is appended to Jr's next user
            # message instead of dispatching to the CLI agent for a round.
            tool_outcome = await self._handle_tool_calls(
                rounds_completed=rounds_completed,
                reply=yamac_reply,
            )
            if tool_outcome is not None:
                rendered_text, raw_calls, raw_results = tool_outcome
                history.append({"role": "assistant", "content": yamac_reply})
                history.append({"role": "user", "content": rendered_text})
                await self._record_episodic_round(
                    round_index=rounds_completed,
                    operator_message=yamac_reply,
                    cli_response=rendered_text,
                    tool_calls=raw_calls,
                    tool_results=raw_results,
                )
                rounds_completed += 1
                action_count += 1
                is_first_round = False
                # Jr autopilot session-end propagation. ``mark_done`` returns
                # the literal DONE sentinel in its payload; the tool branch
                # otherwise consumes the reply and ``continue``s past the
                # text-based ``is_selffork_jr_done`` check above. Without
                # this hop, a session that ends via mark_done() runs until
                # max_rounds.
                if _has_mark_done_ok(raw_calls, raw_results):
                    self._audit.emit(
                        "agent.done",
                        payload={
                            "reason": "mark_done_tool",
                            "rounds": rounds_completed,
                        },
                    )
                    return
                self._observe_round(
                    tool_key=_tool_calls_key(raw_calls),
                    observation_text=rendered_text,
                    succeeded=all(r.status == "ok" for r in raw_results),
                    history=history,
                )
                continue

            cmd = [
                binary,
                *self._cli_agent.build_command(
                    message=yamac_reply,
                    is_first_round=is_first_round,
                ),
            ]
            is_first_round = False

            self._audit.emit(
                "agent.invoke",
                payload={
                    "round": rounds_completed,
                    "binary": binary,
                    "args_count": len(cmd) - 1,
                },
            )

            await self._theater.cli_output(yamac_reply, kind="jr-prompt")

            # Destructive guard — ADR-006 §4.5 / ADR-007 §4 S3. Pause the
            # round-loop until the operator approves or the per-category
            # window elapses (silence = cancel, fail-safe NO). Both
            # collaborators must be wired for the guard to engage;
            # orphan/test runs without a whitelist or store proceed
            # unchanged.
            if self._destructive_whitelist is not None and self._pending_store is not None:
                guard = await check_destructive_action(
                    cmd=cmd,
                    env=env,
                    workspace_slug=self._project_slug,
                    whitelist=self._destructive_whitelist,
                    store=self._pending_store,
                    audit=self._audit,
                )
                if not guard.allow:
                    raise DestructiveActionBlockedError(
                        reason=guard.reason,
                        entry=guard.entry,
                    )

            proc = await self._sandbox.exec(cmd, env=env)
            stdout_chunks: list[bytes] = []
            async for line in proc.stdout:
                stdout_chunks.append(line)
                await self._theater.cli_output(
                    line.decode("utf-8", errors="replace"), kind="stdout"
                )
            stderr_chunks: list[bytes] = []
            async for line in proc.stderr:
                stderr_chunks.append(line)
                await self._theater.cli_output(
                    line.decode("utf-8", errors="replace"), kind="stderr"
                )
            exit_code = await proc.wait()
            output_text = b"".join(stdout_chunks).decode("utf-8", errors="replace")
            stderr_text = b"".join(stderr_chunks).decode("utf-8", errors="replace")

            self._audit.emit(
                "agent.output",
                payload={
                    "round": rounds_completed,
                    "exit_code": exit_code,
                    "output_chars": len(output_text),
                    "stderr_chars": len(stderr_text),
                },
            )

            # Subscription quota / auth detection. Runs even on exit_code=0
            # because gemini hits 429 mid-stream without a non-zero exit
            # and opencode can hang/exit-zero on its own (see
            # opencode_detector.py docstring).
            if self._limit_detector is not None:
                paused = await self._handle_limit_verdict(
                    stdout=output_text,
                    stderr=stderr_text,
                    exit_code=exit_code,
                    last_round_text=yamac_reply,
                )
                if paused:
                    return

            if exit_code != 0:
                raise SelfForkError(
                    f"CLI agent exited non-zero ({exit_code}) on round "
                    f"{rounds_completed}; output: {output_text[:500]!r}",
                )

            history.append({"role": "assistant", "content": yamac_reply})
            history.append({"role": "user", "content": output_text})
            await self._record_episodic_round(
                round_index=rounds_completed,
                operator_message=yamac_reply,
                cli_response=output_text,
            )
            rounds_completed += 1
            action_count += 1
            # The cli-path action identity hashes Jr's PROMPT (greedy decoding
            # repeats it when stuck, so SAME_TOOL_REPEAT fires on a genuinely
            # stuck loop); the no-observable-change axis (``observation_text``)
            # is the backstop when the prompt varies but the output does not
            # (ADR-010 §2.2.4).
            self._observe_round(
                tool_key=(f"cli:{self._cli_agent_name or binary}|{hash_observation(yamac_reply)}"),
                observation_text=output_text,
                succeeded=exit_code == 0,
                history=history,
            )

        raise SelfForkError(
            f"max_rounds ({max_rounds}) reached without [SELFFORK:DONE] sentinel from SelfFork Jr",
        )

    def _enforce_loop_caps(self, action_count: int, started_at: float) -> None:
        """ADR-010 §2.2 hard safety caps. Raise :class:`SelfForkError` on breach.

        The action-count cap is an always-on backstop; the wall-clock cap is
        opt-in (``None`` disables it — ADR-011 §5 forbids killing a slow CPU
        generation, so a wall-clock guard must never be a silent default).
        """
        cap = self._lifecycle_config.hard_action_cap
        if cap is not None and action_count >= cap:
            self._audit.emit(
                "loop.cap_reached",
                level="WARNING",
                payload={"kind": "action_count", "count": action_count, "cap": cap},
            )
            raise SelfForkError(
                f"agentic loop hit the hard action cap ({cap}) without [SELFFORK:DONE]",
            )
        wall = self._lifecycle_config.wall_clock_cap_seconds
        if wall is not None:
            elapsed = time.monotonic() - started_at
            if elapsed > wall:
                self._audit.emit(
                    "loop.cap_reached",
                    level="WARNING",
                    payload={
                        "kind": "wall_clock",
                        "elapsed_seconds": round(elapsed, 1),
                        "cap_seconds": wall,
                    },
                )
                raise SelfForkError(
                    f"agentic loop exceeded the wall-clock cap ({wall}s) without [SELFFORK:DONE]",
                )

    def _observe_round(
        self,
        *,
        tool_key: str | None,
        observation_text: str,
        succeeded: bool,
        history: list[ChatMessage],
    ) -> None:
        """Feed one completed round to the stuck-detector (ADR-010 §2.2).

        No-op when no detector is wired. A soft NUDGE injects the corrective
        into Jr's next user message so it can self-correct; a hard ABORT raises
        :class:`SelfForkError` (the loop is genuinely stuck — fail, never spin).
        """
        if self._stuck_detector is None:
            return
        verdict = self._stuck_detector.record(
            StepObservation(
                tool_key=tool_key,
                observation_hash=hash_observation(observation_text),
                succeeded=succeeded,
            ),
        )
        if not verdict.tripped:
            return
        reason = verdict.reason.value if verdict.reason is not None else None
        if verdict.recovery is RecoveryAction.ABORT:
            self._audit.emit(
                "loop.stuck",
                level="WARNING",
                payload={"reason": reason, "detail": verdict.detail},
            )
            raise SelfForkError(
                f"agentic loop stuck ({reason}): {verdict.corrective_message}",
            )
        self._audit.emit(
            "loop.stuck_warning",
            payload={"reason": reason, "detail": verdict.detail},
        )
        # Fold the soft-nudge corrective into the round's existing user
        # message (the tool/cli/spawn result just appended above) instead of
        # a second consecutive ``user`` turn — Gemma's chat template requires
        # alternating roles, so a back-to-back user pair would break real
        # inference (the test fake tolerates it; the model would not).
        corrective = f"[orchestrator] {verdict.corrective_message}"
        if history and history[-1]["role"] == "user":
            merged = history[-1]["content"] + "\n\n" + corrective
            history[-1]["content"] = merged
        else:
            history.append({"role": "user", "content": corrective})

    async def _handle_tool_calls(
        self,
        *,
        rounds_completed: int,
        reply: str,
    ) -> tuple[str, list[ToolCall], list[ToolResult]] | None:
        """Parse Jr's reply for tool calls; invoke them; return aggregated text + raw calls/results.

        Returns ``None`` when no tool calls were found, signalling the
        run loop should fall through to its normal CLI-agent exec path.
        Returns ``(rendered_text, calls, results)`` when at least one call ran —
        ``rendered_text`` is the text appended to Jr's next user message; the
        raw lists are forwarded to the Mind T2 hook (when wired) so each
        tool call becomes a ``pattern`` Note alongside the round observation.
        """
        if self._tool_registry is None:
            return None
        calls = parse_tool_calls(reply)
        if not calls:
            return None
        ctx = ToolContext(
            session_id=self._session_id,
            project_slug=self._project_slug,
            project_store=self._project_store,
            mind_store=self._mind_store,
            mind_retriever=self._mind_retriever,
            episodic_writer=self._episodic_writer,
            cli_agent_name=self._cli_agent_name,
            proactive_reader=self._proactive_reader,
            launchd_scheduler=self._launchd_scheduler,
            resume_store=self._resume_store,
            cli_override_store=self._cli_override_store,
            cli_runtime_store=self._cli_runtime_store,
            audit_logger=self._audit,
            structured_question_store=self._structured_question_store,
        )
        results: list[ToolResult] = []
        for call in calls:
            self._audit.emit(
                # S8 — route AskUserQuestion-style structured calls to a
                # distinct category so the activity feed + S-Train can
                # surface them. ``call_id`` (session+round+order) pairs the
                # question with its answer event below.
                "tool.structured_question" if is_structured_question(call.tool) else "tool.call",
                payload={
                    "round": rounds_completed,
                    "tool": call.tool,
                    "args": call.args,
                    "order": call.order_in_reply,
                },
            )
            result = await self._tool_registry.invoke_async(call, ctx)
            # Order 4 / M-7 — ``payload_keys`` stays for backwards
            # compatibility with audit-derived consumers (UsageAggregator,
            # M3 audit-fix tooling). ``result_payload_preview`` is the
            # additive field the cockpit Chat tab inlines for tool calls
            # — redaction-safe, capped to 5 KB per result.
            self._audit.emit(
                # S8 — the answer to a structured question lands in the
                # paired category. ``order`` mirrors the question's
                # ``order`` so the activity feed groups the Q/A pair.
                "tool.structured_answer" if is_structured_question(result.tool) else "tool.result",
                payload={
                    "round": rounds_completed,
                    "tool": result.tool,
                    "status": result.status,
                    "error": result.error,
                    "order": call.order_in_reply,
                    "payload_keys": list(result.payload or {}),
                    "result_payload_preview": _redact_preview(result.payload),
                },
            )
            results.append(result)
        return _format_tool_results(results), calls, results

    async def _record_episodic_round(
        self,
        *,
        round_index: int,
        operator_message: str,
        cli_response: str,
        tool_calls: list[ToolCall] | None = None,
        tool_results: list[ToolResult] | None = None,
        sentinels: list[str] | None = None,
    ) -> None:
        """Mind T2 hook — capture this round as an Episodic note.

        No-op when ``episodic_writer`` is not wired. Failures are logged but
        never propagated: Mind capture is observability, not a critical path.
        """
        if self._episodic_writer is None:
            return
        episodic_calls = _convert_tool_calls(tool_calls or [], tool_results or [])
        try:
            await self._episodic_writer.write_round(
                session_id=self._session_id,
                project_slug=self._project_slug,
                cli_agent=self._cli_agent_name,
                round_index=round_index,
                operator_message=operator_message,
                cli_response=cli_response,
                tool_calls=episodic_calls,
                sentinels=sentinels,
            )
            self._audit.emit(
                "mind.note.write",
                payload={
                    "round": round_index,
                    "tier": "episodic",
                    "tool_calls": len(episodic_calls),
                },
            )
        except Exception as exc:
            _log.warning(
                "episodic_writer_failed",
                round_index=round_index,
                error=f"{type(exc).__name__}: {exc}",
            )

    async def _handle_spawn(
        self,
        *,
        rounds_completed: int,
        requests: list[SpawnRequest],
    ) -> str:
        """Delegate child-spawning to the configured handler.

        Without a handler we fail-fast: Jr signaled intent we can't honor.
        Continuing silently would silently drop work and confuse Jr.
        """
        if self._spawn_handler is None:
            raise SelfForkError(
                "SelfFork Jr emitted [SELFFORK:SPAWN: ...] but no "
                "spawn_handler is wired; configure one or stop emitting "
                "SPAWN tags.",
            )
        self._audit.emit(
            "agent.spawn_request",
            payload={
                "round": rounds_completed,
                "n_spawns": len(requests),
                "specs_preview": [r.spec[:120] for r in requests],
            },
        )
        aggregated = await self._spawn_handler(
            parent_session_id=self._session_id,
            requests=requests,
        )
        self._audit.emit(
            "agent.spawn_complete",
            payload={
                "round": rounds_completed,
                "aggregated_chars": len(aggregated),
            },
        )
        return aggregated

    async def _handle_limit_verdict(
        self,
        *,
        stdout: str,
        stderr: str,
        exit_code: int,
        last_round_text: str,
    ) -> bool:
        """Run the limit detector; return ``True`` when the loop must stop.

        ``True`` means we've transitioned to PAUSED_RATE_LIMIT and the
        run_loop should return; the outer ``run()`` flow then skips the
        verify step and goes straight to teardown. AuthRequired raises
        a fast SelfForkError so the user gets a clear "re-login" message.
        """
        assert self._limit_detector is not None  # noqa: S101
        verdict = self._limit_detector.detect(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
        )
        if isinstance(verdict, NoLimit):
            return False
        if isinstance(verdict, AuthRequired):
            self._audit.emit(
                "agent.auth_required",
                payload={"reason": verdict.reason},
            )
            raise SelfForkError(verdict.reason)
        # RateLimited
        assert isinstance(verdict, RateLimited)  # noqa: S101 — exhaustive
        self._audit.emit(
            "agent.rate_limited",
            payload={
                "reason": verdict.reason,
                "kind": verdict.kind,
                "resume_at_iso": verdict.reset_at.isoformat(),
            },
        )
        if self._rate_limit_handler is not None:
            await self._rate_limit_handler(
                session_id=self._session_id,
                verdict=verdict,
                last_round_text=last_round_text,
            )
        self._transition(SessionState.PAUSED_RATE_LIMIT, reason=verdict.reason)
        return True

    async def _verify(self) -> None:
        if self._lifecycle_config.skip_verify:
            self._transition(SessionState.COMPLETED)
            return
        self._transition(SessionState.VERIFYING)
        # MVP verifier: ``noop`` and ``lenient`` always pass through.
        # ``strict`` / ``moderate`` modes are reserved for M1+ (per ADR §15
        # and Codeman's orchestrator-verifier.ts:65-102 pattern reference).
        # Until then, every reachable verifier mode is a pass.
        self._transition(SessionState.COMPLETED)

    async def _teardown(self) -> None:
        # Always called via ``run()``'s finally block.
        # Drop the sandbox first (kills the agent), then the runtime.
        with contextlib.suppress(BaseException):
            await self._sandbox.teardown()
            self._audit.emit("sandbox.teardown")
        with contextlib.suppress(BaseException):
            await self._runtime.stop()
            self._audit.emit("runtime.stop")
        # Force-transition to TORN_DOWN — this is the one transition we
        # don't gate through ``is_legal_transition`` because teardown is
        # mandatory regardless of where we ended up.
        prev = self._state
        self._state = SessionState.TORN_DOWN
        self._audit.emit(
            "session.state",
            event="transition",
            payload={"from": prev.value, "to": SessionState.TORN_DOWN.value},
        )

    # ── Internal helpers ──────────────────────────────────────────────────

    def _transition(self, to_state: SessionState, reason: str | None = None) -> None:
        """Validate and apply a state transition; emit an audit event."""
        if not is_legal_transition(self._state, to_state):
            raise SelfForkError(
                f"illegal state transition: {self._state.value} -> {to_state.value}",
            )
        from_state = self._state
        self._state = to_state
        payload: dict[str, object] = {"from": from_state.value, "to": to_state.value}
        if reason is not None:
            payload["reason"] = reason
        self._audit.emit("session.state", event="transition", payload=payload)

    def _fail(self, reason: str) -> None:
        """Move to FAILED if the current state allows it."""
        self._failure_reason = reason
        if is_legal_transition(self._state, SessionState.FAILED):
            self._transition(SessionState.FAILED, reason=reason)
        # else: we're already in COMPLETED or TORN_DOWN — nothing to do.


def _tool_calls_key(calls: list[ToolCall]) -> str | None:
    """Combined normalized identity of a round's tool calls (or ``None``).

    A reply that re-issues the same tool call(s) collapses to the same key so
    the stuck-detector's same-tool / oscillation checks fire (ADR-010 §2.2).
    """
    if not calls:
        return None
    return "+".join(normalize_tool_key(call.tool, call.args) for call in calls)


def _convert_tool_calls(
    calls: list[ToolCall],
    results: list[ToolResult],
) -> list[EpisodicToolCall]:
    """Pair each :class:`ToolCall` with its :class:`ToolResult` for Mind T2.

    The orchestrator's typed ToolCall/ToolResult are pillar-internal; Mind
    consumes the slim :class:`EpisodicToolCall` snapshot. Order is taken
    from the ``calls`` list (tool registry guarantees a 1:1 result per call).
    """
    out: list[EpisodicToolCall] = []
    for call, result in zip(calls, results, strict=True):
        out.append(
            EpisodicToolCall(
                tool=call.tool,
                args=call.args,
                status=result.status,
                result_payload=result.payload,
                error=result.error,
            ),
        )
    return out


def _has_mark_done_ok(
    calls: list[ToolCall],
    results: list[ToolResult],
) -> bool:
    """True iff one of the parsed tool calls in this round was ``mark_done``
    AND it executed with status ``ok``. The tool branch otherwise short-
    circuits past the literal-sentinel check; this lets ``mark_done``
    actually end the session.
    """
    for call, result in zip(calls, results, strict=False):
        if call.tool == "mark_done" and result.status == "ok":
            return True
    return False


# M-7 (Order 4) — ``tool.result`` audit payload preview.

# Maximum size of ``result_payload_preview`` after JSON serialisation.
# Big enough for ``mind_recall`` hits + ``available_clis`` lists, small
# enough that an audit JSONL line stays under typical 64 KB log shipper
# limits even when several tool calls fire per round.
_RESULT_PREVIEW_MAX_CHARS = 5_000

# Substring patterns that mark a key whose value should be redacted.
# Conservative — false-positive redaction is fine; false-negative leak
# of a credential into the audit log is a P0. List is post-Order-4
# audit-driven (cookie / client_id / signature / pin / otp / nonce
# were missing on first pass — credential-bearing keys an HTTP / OAuth
# / 2FA tool result might carry).
_SECRET_KEY_PATTERNS: tuple[str, ...] = (
    "api_key",
    "apikey",
    "token",
    "password",
    "passwd",
    "secret",
    "credential",
    "auth",
    "authorization",
    "session_key",
    "private_key",
    "bearer",
    "cookie",
    "set-cookie",
    "client_id",
    "client-id",
    "signature",
    "signed",
    "pin",
    "otp",
    "nonce",
    "csrf",
    "xsrf",
    "x-api-key",
    "refresh",
    # M5 Body pillar — vision payload redaction (ADR-005 §M5-D3). Screenshot
    # binary must NEVER be inlined into audit JSONL; persistence is a disk
    # path reference. These keys catch accidental inline base64 / bytes.
    "screenshot_b64",
    "image_b64",
    "image_url",
    "after_screenshot_b64",
    "before_screenshot_b64",
)


# M5 Body pillar — image payload redaction layer (ADR-005 §M5-D3).
# Catches inline base64 / raw bytes that slip past dict-key matching above.
# Path strings (~/.selffork/.../*.png) pass through unchanged.
_IMAGE_BASE64_PREFIXES: tuple[str, ...] = (
    "iVBORw0KG",  # PNG magic bytes base64
    "/9j/",  # JPEG magic bytes base64
    "data:image/",  # data URL
)


def _redact_image_payload(value: bytes | str) -> bytes | str:
    """Replace inline image content with a length-tagged sentinel.

    ``bytes`` are always replaced (raw screenshot inline is policy violation).
    Strings starting with a known base64 image prefix are replaced; strings
    that look like disk paths (``~/.selffork/...png``) are kept intact since
    audit references are paths by design.
    """
    if isinstance(value, bytes):
        return f"<redacted_image:{len(value)}_bytes>"
    if isinstance(value, str) and value.startswith(_IMAGE_BASE64_PREFIXES):
        return f"<redacted_image_base64:{len(value)}_chars>"
    return value


def _redact_preview(payload: object) -> object:
    """Return a redacted, length-capped projection of a tool result payload.

    Order 4 / M-7. The cockpit Chat tab renders this field inline so
    operators can see what a tool returned without reopening the run.
    Four guarantees:

    1. Secret-looking keys are replaced with the literal ``"<redacted>"``
       at any depth (recursive).
    2. Custom objects are coerced through ``__repr__`` BEFORE serialisation
       so any secrets in their stringification go through the same
       key-pattern scan via the wrapping dict.
    3. The serialised JSON is truncated to ``_RESULT_PREVIEW_MAX_CHARS``;
       overflow is signalled with ``"<truncated:N>"`` (N = original size).
    4. Recursion is depth-capped at ``_REDACT_MAX_DEPTH`` so a pathological
       payload never crashes the audit emit (``RecursionError`` would
       fall outside the ``json.dumps`` try/except below).
    """
    redacted = _redact_recursive(payload, depth=0)
    try:
        wire = json.dumps(redacted, ensure_ascii=False, default=repr)
    except (TypeError, ValueError):
        # Last-resort fallback — should be unreachable thanks to ``default=repr``.
        wire = repr(redacted)
    if len(wire) <= _RESULT_PREVIEW_MAX_CHARS:
        return redacted
    return {
        "preview_truncated": True,
        "original_chars": len(wire),
        "head": wire[:_RESULT_PREVIEW_MAX_CHARS],
    }


# 16 deep is generous for tool output (mind_recall hits ~3 deep, quota
# snapshots ~4 deep). Anything deeper smells like accidental cycle or
# malicious payload — collapse to a marker.
_REDACT_MAX_DEPTH = 16


def _redact_recursive(value: object, *, depth: int) -> object:
    if depth >= _REDACT_MAX_DEPTH:
        return "<depth-capped>"
    if isinstance(value, dict):
        return {
            k: ("<redacted>" if _is_secret_key(str(k)) else _redact_recursive(v, depth=depth + 1))
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [_redact_recursive(v, depth=depth + 1) for v in value]
    if isinstance(value, bytes):
        # M5 Body pillar — raw bytes (screenshot binary) must never inline.
        return _redact_image_payload(value)
    if isinstance(value, str):
        # M5 Body pillar — catch inline base64 image strings that slipped
        # past key-pattern matching (e.g. tool result with ``image: <b64>``).
        return _redact_image_payload(value)
    if isinstance(value, int | float | bool | type(None)):
        return value
    # Custom object — coerce through ``__repr__`` and re-scan as a string.
    # This catches the case where ``Custom.__repr__`` includes credential
    # material (boto3 clients, requests Session, etc.). The wrapping dict
    # key check on the parent already redacts the value if the *key*
    # was secret-looking; here we additionally scrub the *content* of the
    # repr against the same pattern list.
    rendered = repr(value)
    return _scrub_string(rendered)


def _scrub_string(text: str) -> str:
    """Replace ``key='value'`` substrings whose key matches a secret pattern.

    Only kicks in for keys we already redact at the dict level — the same
    threat surface, just expressed through a custom object's ``__repr__``.
    """
    lowered = text.lower()
    if not any(pattern in lowered for pattern in _SECRET_KEY_PATTERNS):
        return text
    return "<redacted-repr>"


def _is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(pattern in lowered for pattern in _SECRET_KEY_PATTERNS)


def _format_tool_results(results: list[ToolResult]) -> str:
    """Render a list of tool results as a human-readable block.

    Format keeps Jr's next round-input small but unambiguous:

        === Tool results ===
        [ok] kanban_card_done(card-01HJ...) -> {"to_column": "done", ...}
        [invalid_args] kanban_card_move(card-???) -> error: card_id missing
        === /Tool results ===
        [Now decide the next step.]
    """
    lines: list[str] = ["=== Tool results ==="]
    for result in results:
        prefix = f"[{result.status}] {result.tool}"
        if result.status == "ok":
            lines.append(f"{prefix} -> {result.payload}")
        else:
            lines.append(f"{prefix} -> error: {result.error}")
    lines.append("=== /Tool results ===")
    lines.append("[Now decide the next step.]")
    return "\n".join(lines)
