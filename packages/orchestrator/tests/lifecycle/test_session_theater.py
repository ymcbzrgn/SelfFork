"""Session ↔ Live Run Theater wiring integration tests — S2.

Runs the real :meth:`Session._run_agent` round-loop with a recording
``TheaterProducer`` and asserts the producer is called at exactly the
right points: ``loop_started`` once, ``thought`` + ``cli_output`` per
round, ``loop_ended`` once (even on failure — it lives in ``run()``'s
``finally``).

This is the infra-free proof of the ADR-007 §4 S2 producer wiring: it
needs no model endpoint and no CLI binary. Inlines minimal fakes for
runtime / sandbox / CLI-agent, mirroring ``test_session_episodic.py``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from pathlib import Path

import pytest

from selffork_orchestrator.cli_agent.base import CLIAgent
from selffork_orchestrator.cli_agent.opencode import DONE_SENTINEL
from selffork_orchestrator.lifecycle.session import Session
from selffork_orchestrator.lifecycle.states import SessionState
from selffork_orchestrator.plan.store_filesystem import FilesystemPlanStore
from selffork_orchestrator.runtime.base import ChatMessage, LLMRuntime
from selffork_orchestrator.sandbox.base import Sandbox, SandboxProcess
from selffork_orchestrator.theater.models import CliOutputKind
from selffork_shared.audit import AuditLogger
from selffork_shared.config import AuditConfig, LifecycleConfig, PlanConfig

# ── Minimal fakes ─────────────────────────────────────────────────────────


class _FakeRuntime(LLMRuntime):
    def __init__(self, *, replies: list[str]) -> None:
        self._started = False
        self._replies = list(replies)
        self._idx = 0

    async def start(self) -> None:
        self._started = True

    async def stop(self) -> None:
        self._started = False

    @property
    def base_url(self) -> str:
        return "http://127.0.0.1:9999/v1"

    @property
    def model_id(self) -> str:
        return "fake-model"

    async def health(self) -> bool:
        return self._started

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        del messages, max_tokens, temperature
        if self._idx >= len(self._replies):
            return DONE_SENTINEL
        reply = self._replies[self._idx]
        self._idx += 1
        return reply


class _FakeSandboxProcess(SandboxProcess):
    def __init__(self, lines: list[bytes], exit_code: int = 0) -> None:
        self._lines = lines
        self._exit_code = exit_code

    @property
    def pid(self) -> int:
        return 42

    @property
    def stdout(self) -> AsyncIterator[bytes]:
        async def gen() -> AsyncIterator[bytes]:
            for line in self._lines:
                yield line

        return gen()

    @property
    def stderr(self) -> AsyncIterator[bytes]:
        async def gen() -> AsyncIterator[bytes]:
            for _ in ():  # empty generator (no stderr lines in these tests)
                yield b""

        return gen()

    async def wait(self) -> int:
        return self._exit_code

    async def kill(self, grace_seconds: float = 1.0) -> None:
        del grace_seconds


class _FakeSandbox(Sandbox):
    def __init__(self, workspace_path: str) -> None:
        self._workspace = workspace_path
        self._lines: list[bytes] = []
        self._exit_code = 0
        self.exec_calls: list[list[str]] = []

    def configure_exec(self, lines: list[bytes], exit_code: int = 0) -> None:
        self._lines = lines
        self._exit_code = exit_code

    @property
    def workspace_path(self) -> str:
        return self._workspace

    @property
    def host_workspace_path(self) -> str:
        return self._workspace

    async def spawn(self) -> None:
        return

    async def exec(
        self,
        command: list[str],
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> SandboxProcess:
        del env, cwd
        self.exec_calls.append(command)
        return _FakeSandboxProcess(self._lines, self._exit_code)

    async def teardown(self) -> None:
        return


class _FakeCLIAgent(CLIAgent):
    def __init__(self) -> None:
        return

    def resolve_binary(self) -> str:
        return "/fake/agent"

    def compose_initial_messages(
        self,
        *,
        prd: str,
        plan_path: str,
        workspace: str,
    ) -> list[ChatMessage]:
        del plan_path, workspace
        return [{"role": "user", "content": prd}]

    def build_command(self, *, message: str, is_first_round: bool) -> list[str]:
        del is_first_round
        return ["run", message]

    def build_env(self, base_env: Mapping[str, str]) -> dict[str, str]:
        return dict(base_env)

    def is_selffork_jr_done(self, reply: str) -> bool:
        return DONE_SENTINEL in reply


class _RecordingTheaterProducer:
    """A ``TheaterProducer`` that records every call — wiring assertions."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def loop_started(self) -> None:
        self.calls.append(("loop_started", {}))

    async def cli_output(self, text: str, *, kind: CliOutputKind = "stdout") -> None:
        payload: dict[str, object] = {"text": text, "kind": kind}
        self.calls.append(("cli_output", payload))

    async def thought(self, reply: str, *, turn: int) -> None:
        payload: dict[str, object] = {"reply": reply, "turn": turn}
        self.calls.append(("thought", payload))

    async def loop_ended(self) -> None:
        self.calls.append(("loop_ended", {}))


# ── helper ────────────────────────────────────────────────────────────────


def _build_session(
    tmp_path: Path,
    *,
    runtime: _FakeRuntime,
    sandbox: _FakeSandbox,
    agent: _FakeCLIAgent,
    theater_producer: _RecordingTheaterProducer | None,
) -> Session:
    workspace = Path(sandbox.host_workspace_path)
    workspace.mkdir(parents=True, exist_ok=True)
    plan_cfg = PlanConfig(backend="filesystem", plan_filename=".selffork/plan.json")
    plan_store = FilesystemPlanStore(plan_cfg, workspace_path=str(workspace))
    audit_cfg = AuditConfig(enabled=True, audit_dir=str(tmp_path / "audit"))
    audit = AuditLogger(audit_cfg, session_id="01HJTESTSESSIONABCDEFGHIJK")
    return Session(
        session_id="01HJTESTSESSIONABCDEFGHIJK",
        prd_text="prd",
        prd_path="/prd.md",
        plan_path_in_sandbox=f"{sandbox.workspace_path}/.selffork/plan.json",
        runtime=runtime,
        sandbox=sandbox,
        cli_agent=agent,
        plan_store=plan_store,
        audit_logger=audit,
        lifecycle_config=LifecycleConfig(skip_verify=True, max_rounds=20),
        project_slug="p1",
        theater_producer=theater_producer,
    )


# ── tests ─────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_round_loop_emits_theater_events_in_order(
    tmp_path: Path,
) -> None:
    runtime = _FakeRuntime(replies=["İlk adımı at", DONE_SENTINEL])
    sandbox = _FakeSandbox(workspace_path=str(tmp_path / "ws"))
    sandbox.configure_exec(lines=[b"cli wrote stuff\n"], exit_code=0)
    recorder = _RecordingTheaterProducer()
    session = _build_session(
        tmp_path,
        runtime=runtime,
        sandbox=sandbox,
        agent=_FakeCLIAgent(),
        theater_producer=recorder,
    )
    outcome = await session.run()
    assert outcome == SessionState.COMPLETED
    assert recorder.calls == [
        ("loop_started", {}),
        ("thought", {"reply": "İlk adımı at", "turn": 0}),
        ("cli_output", {"text": "İlk adımı at", "kind": "jr-prompt"}),
        ("cli_output", {"text": "cli wrote stuff\n", "kind": "stdout"}),
        ("thought", {"reply": DONE_SENTINEL, "turn": 1}),
        ("loop_ended", {}),
    ]


@pytest.mark.anyio
async def test_immediate_done_emits_minimal_events(
    tmp_path: Path,
) -> None:
    runtime = _FakeRuntime(replies=[DONE_SENTINEL])
    sandbox = _FakeSandbox(workspace_path=str(tmp_path / "ws"))
    recorder = _RecordingTheaterProducer()
    session = _build_session(
        tmp_path,
        runtime=runtime,
        sandbox=sandbox,
        agent=_FakeCLIAgent(),
        theater_producer=recorder,
    )
    outcome = await session.run()
    assert outcome == SessionState.COMPLETED
    # No CLI exec — Jr ended immediately. No cli_output events.
    assert recorder.calls == [
        ("loop_started", {}),
        ("thought", {"reply": DONE_SENTINEL, "turn": 0}),
        ("loop_ended", {}),
    ]


@pytest.mark.anyio
async def test_loop_ended_fires_even_on_failure(tmp_path: Path) -> None:
    runtime = _FakeRuntime(replies=["do it", DONE_SENTINEL])
    sandbox = _FakeSandbox(workspace_path=str(tmp_path / "ws"))
    sandbox.configure_exec(lines=[b"boom\n"], exit_code=1)  # CLI fails
    recorder = _RecordingTheaterProducer()
    session = _build_session(
        tmp_path,
        runtime=runtime,
        sandbox=sandbox,
        agent=_FakeCLIAgent(),
        theater_producer=recorder,
    )
    outcome = await session.run()
    assert outcome == SessionState.FAILED
    # loop_ended runs in run()'s finally — even when the loop raised.
    assert recorder.calls[0] == ("loop_started", {})
    assert recorder.calls[-1] == ("loop_ended", {})


@pytest.mark.anyio
async def test_session_without_theater_producer_runs(
    tmp_path: Path,
) -> None:
    runtime = _FakeRuntime(replies=["go", DONE_SENTINEL])
    sandbox = _FakeSandbox(workspace_path=str(tmp_path / "ws"))
    sandbox.configure_exec(lines=[b"ok\n"], exit_code=0)
    session = _build_session(
        tmp_path,
        runtime=runtime,
        sandbox=sandbox,
        agent=_FakeCLIAgent(),
        theater_producer=None,  # Null producer default — must not crash
    )
    outcome = await session.run()
    assert outcome == SessionState.COMPLETED
