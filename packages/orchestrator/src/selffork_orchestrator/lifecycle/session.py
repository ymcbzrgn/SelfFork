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
import os
from typing import Protocol

from selffork_orchestrator.cli_agent.base import CLIAgent
from selffork_orchestrator.lifecycle.states import (
    SessionState,
    is_legal_transition,
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
from selffork_orchestrator.tools.base import (
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
        self._state: SessionState = SessionState.IDLE
        self._failure_reason: str | None = None

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def failure_reason(self) -> str | None:
        return self._failure_reason

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
        binary = self._cli_agent.resolve_binary()
        env = self._cli_agent.build_env(base_env=os.environ)

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

        while max_rounds is None or rounds_completed < max_rounds:
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
                rounds_completed += 1
                is_first_round = False
                continue

            # Tool calls (e.g. <selffork-tool-call> ... kanban_card_done ...)
            # are handled BEFORE the CLI exec because the typical Jr-with-
            # tools turn looks like "I'm marking card X done; now please
            # proceed". The tool result is appended to Jr's next user
            # message instead of dispatching to the CLI agent for a round.
            tool_results = self._handle_tool_calls(
                rounds_completed=rounds_completed,
                reply=yamac_reply,
            )
            if tool_results is not None:
                history.append({"role": "assistant", "content": yamac_reply})
                history.append({"role": "user", "content": tool_results})
                rounds_completed += 1
                is_first_round = False
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

            proc = await self._sandbox.exec(cmd, env=env)
            stdout_chunks: list[bytes] = []
            async for line in proc.stdout:
                stdout_chunks.append(line)
            stderr_chunks: list[bytes] = []
            async for line in proc.stderr:
                stderr_chunks.append(line)
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
            rounds_completed += 1

        raise SelfForkError(
            f"max_rounds ({max_rounds}) reached without [SELFFORK:DONE] sentinel from SelfFork Jr",
        )

    def _handle_tool_calls(
        self,
        *,
        rounds_completed: int,
        reply: str,
    ) -> str | None:
        """Parse Jr's reply for tool calls; invoke them; return aggregated text.

        Returns ``None`` when no tool calls were found, signalling the
        run loop should fall through to its normal CLI-agent exec path.
        Returns a non-empty string when at least one call ran — that
        string is the text appended to Jr's next user message so the
        LLM can react to the result on the next round.
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
        )
        results: list[ToolResult] = []
        for call in calls:
            self._audit.emit(
                "tool.call",
                payload={
                    "round": rounds_completed,
                    "tool": call.tool,
                    "args": call.args,
                    "order": call.order_in_reply,
                },
            )
            result = self._tool_registry.invoke(call, ctx)
            self._audit.emit(
                "tool.result",
                payload={
                    "round": rounds_completed,
                    "tool": result.tool,
                    "status": result.status,
                    "error": result.error,
                    "payload_keys": list(result.payload or {}),
                },
            )
            results.append(result)
        return _format_tool_results(results)

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
