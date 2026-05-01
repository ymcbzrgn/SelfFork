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

from selffork_orchestrator.cli_agent.base import CLIAgent
from selffork_orchestrator.lifecycle.states import (
    SessionState,
    is_legal_transition,
)
from selffork_orchestrator.plan.model import Plan
from selffork_orchestrator.plan.store_base import PlanStore
from selffork_orchestrator.runtime.base import ChatMessage, LLMRuntime
from selffork_orchestrator.sandbox.base import Sandbox
from selffork_shared.audit import AuditLogger
from selffork_shared.config import LifecycleConfig
from selffork_shared.errors import SelfForkError
from selffork_shared.logging import bind_session_id, get_logger

__all__ = ["Session"]

_log = get_logger(__name__)


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
        meaningful outcome is the value returned (``COMPLETED`` or
        ``FAILED``).
        """
        bind_session_id(self._session_id)
        outcome: SessionState = SessionState.FAILED
        try:
            await self._prepare()
            await self._run_agent()
            await self._verify()
            outcome = self._state  # COMPLETED or FAILED
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
          4. Repeat until done or :attr:`LifecycleConfig.max_rounds`.
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
        max_rounds = self._lifecycle_config.max_rounds

        while rounds_completed < max_rounds:
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
            output_chunks: list[bytes] = []
            async for line in proc.stdout:
                output_chunks.append(line)
            exit_code = await proc.wait()
            output_text = b"".join(output_chunks).decode("utf-8", errors="replace")

            self._audit.emit(
                "agent.output",
                payload={
                    "round": rounds_completed,
                    "exit_code": exit_code,
                    "output_chars": len(output_text),
                },
            )

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
