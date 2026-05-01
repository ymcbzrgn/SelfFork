"""Unit tests for :class:`Session` end-to-end orchestration (round-loop architecture).

Wires fakes for runtime, sandbox, and CLI agent so the test can drive a
full lifecycle without spawning real processes. Plan store and audit
logger use real implementations so we exercise the persistence path.

The new round-loop pattern (per ``project_selffork_jr_is_user_simulator.md``):
the runtime fake holds a queue of canned SelfFork-Jr replies, the CLI-agent
fake records every invocation, and the orchestrator stops when a reply
contains the ``[SELFFORK:DONE]`` sentinel.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping, Sequence
from itertools import pairwise
from pathlib import Path

import pytest

from selffork_orchestrator.cli_agent.base import CLIAgent
from selffork_orchestrator.cli_agent.opencode import DONE_SENTINEL
from selffork_orchestrator.lifecycle.session import Session
from selffork_orchestrator.lifecycle.states import SessionState
from selffork_orchestrator.plan.store_filesystem import FilesystemPlanStore
from selffork_orchestrator.runtime.base import ChatMessage, LLMRuntime
from selffork_orchestrator.sandbox.base import Sandbox, SandboxProcess
from selffork_shared.audit import AuditLogger
from selffork_shared.config import AuditConfig, LifecycleConfig, PlanConfig
from selffork_shared.errors import RuntimeStartError, SandboxSpawnError

# ── Fakes ─────────────────────────────────────────────────────────────────────


class _FakeRuntime(LLMRuntime):
    def __init__(
        self,
        *,
        fail_start: bool = False,
        replies: list[str] | None = None,
    ) -> None:
        self._started = False
        self._fail_start = fail_start
        self.start_count = 0
        self.stop_count = 0
        self.chat_calls: list[list[dict[str, str]]] = []
        # Queue of canned SelfFork-Jr replies. After the queue empties, the
        # default is ``[SELFFORK:DONE]`` so a misconfigured test ends fast
        # instead of hanging.
        self._replies = list(replies) if replies is not None else [DONE_SENTINEL]
        self._reply_idx = 0

    async def start(self) -> None:
        self.start_count += 1
        if self._fail_start:
            raise RuntimeStartError("fake start failure")
        self._started = True

    async def stop(self) -> None:
        self.stop_count += 1
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
        del max_tokens, temperature
        self.chat_calls.append([dict(m) for m in messages])
        if self._reply_idx >= len(self._replies):
            return DONE_SENTINEL
        reply = self._replies[self._reply_idx]
        self._reply_idx += 1
        return reply


class _FakeSandboxProcess(SandboxProcess):
    def __init__(self, lines: list[bytes], exit_code: int = 0) -> None:
        self._lines = lines
        self._exit_code = exit_code

    @property
    def pid(self) -> int:
        return 12345

    @property
    def stdout(self) -> AsyncIterator[bytes]:
        async def gen() -> AsyncIterator[bytes]:
            for line in self._lines:
                yield line

        return gen()

    @property
    def stderr(self) -> AsyncIterator[bytes]:
        async def gen() -> AsyncIterator[bytes]:
            for _ in ():  # empty async generator
                yield b""

        return gen()

    async def wait(self) -> int:
        return self._exit_code

    async def kill(self, grace_seconds: float = 1.0) -> None:
        del grace_seconds


class _FakeSandbox(Sandbox):
    def __init__(self, workspace_path: str, *, fail_spawn: bool = False) -> None:
        self._workspace = workspace_path
        self._fail_spawn = fail_spawn
        self._exec_lines: list[bytes] = []
        self._exec_exit_code = 0
        self.spawn_count = 0
        self.teardown_count = 0
        self.exec_calls: list[list[str]] = []

    def configure_exec(self, lines: list[bytes], exit_code: int = 0) -> None:
        self._exec_lines = lines
        self._exec_exit_code = exit_code

    @property
    def workspace_path(self) -> str:
        return self._workspace

    @property
    def host_workspace_path(self) -> str:
        return self._workspace

    async def spawn(self) -> None:
        self.spawn_count += 1
        if self._fail_spawn:
            raise SandboxSpawnError("fake spawn failure")

    async def exec(
        self,
        command: list[str],
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> SandboxProcess:
        del env, cwd
        self.exec_calls.append(command)
        return _FakeSandboxProcess(self._exec_lines, self._exec_exit_code)

    async def teardown(self) -> None:
        self.teardown_count += 1


class _FakeCLIAgent(CLIAgent):
    def __init__(self) -> None:
        self.compose_calls: list[dict[str, str]] = []
        self.command_calls: list[tuple[str, bool]] = []

    def resolve_binary(self) -> str:
        return "/fake/agent"

    def compose_initial_messages(
        self,
        *,
        prd: str,
        plan_path: str,
        workspace: str,
    ) -> list[ChatMessage]:
        self.compose_calls.append(
            {"prd": prd, "plan_path": plan_path, "workspace": workspace},
        )
        return [
            {"role": "system", "content": "fake-system-prompt"},
            {"role": "user", "content": f"prd-snippet:{prd[:30]}"},
        ]

    def build_command(self, *, message: str, is_first_round: bool) -> list[str]:
        self.command_calls.append((message, is_first_round))
        flag = "first" if is_first_round else "continue"
        return ["run", flag, message]

    def build_env(self, base_env: Mapping[str, str]) -> dict[str, str]:
        return dict(base_env)

    def is_selffork_jr_done(self, reply: str) -> bool:
        return DONE_SENTINEL in reply


# ── Helpers ───────────────────────────────────────────────────────────────────


def _build_session(
    tmp_path: Path,
    *,
    runtime: _FakeRuntime,
    sandbox: _FakeSandbox,
    agent: _FakeCLIAgent,
    skip_verify: bool = False,
    max_rounds: int | None = 20,
) -> tuple[Session, FilesystemPlanStore, AuditLogger]:
    workspace = Path(sandbox.host_workspace_path)
    workspace.mkdir(parents=True, exist_ok=True)

    plan_cfg = PlanConfig(backend="filesystem", plan_filename=".selffork/plan.json")
    plan_store = FilesystemPlanStore(plan_cfg, workspace_path=str(workspace))

    audit_cfg = AuditConfig(enabled=True, audit_dir=str(tmp_path / "audit"))
    audit = AuditLogger(audit_cfg, session_id="01HJTESTSESSIONABCDEFGHIJK")

    session = Session(
        session_id="01HJTESTSESSIONABCDEFGHIJK",
        prd_text="Build a hello-world API.",
        prd_path="/prd.md",
        plan_path_in_sandbox=f"{sandbox.workspace_path}/.selffork/plan.json",
        runtime=runtime,
        sandbox=sandbox,
        cli_agent=agent,
        plan_store=plan_store,
        audit_logger=audit,
        lifecycle_config=LifecycleConfig(skip_verify=skip_verify, max_rounds=max_rounds),
    )
    return session, plan_store, audit


def _read_audit(audit: AuditLogger) -> list[dict[str, object]]:
    assert audit.path is not None
    return [
        json.loads(line) for line in audit.path.read_text(encoding="utf-8").strip().splitlines()
    ]


def _categories(audit: AuditLogger) -> set[str]:
    return {str(rec["category"]) for rec in _read_audit(audit)}


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_immediate_done_no_cli_invocation(self, tmp_path: Path) -> None:
        # SelfFork Jr says done on round 0 — orchestrator never invokes CLI.
        runtime = _FakeRuntime(replies=[DONE_SENTINEL])
        sandbox = _FakeSandbox(workspace_path=str(tmp_path / "ws"))
        agent = _FakeCLIAgent()
        session, plan_store, audit = _build_session(
            tmp_path,
            runtime=runtime,
            sandbox=sandbox,
            agent=agent,
        )

        outcome = await session.run()

        assert outcome == SessionState.COMPLETED
        assert session.state == SessionState.TORN_DOWN
        assert runtime.chat_calls and len(runtime.chat_calls) == 1
        assert sandbox.exec_calls == []  # no CLI invocation
        assert agent.command_calls == []

        cats = _categories(audit)
        assert "selffork_jr.reply" in cats
        assert "agent.done" in cats
        assert "agent.invoke" not in cats  # never invoked
        # Plan was written even though the loop ended at round 0.
        plan = await plan_store.load()
        assert plan.session_id == "01HJTESTSESSIONABCDEFGHIJK"

    @pytest.mark.asyncio
    async def test_two_rounds_then_done(self, tmp_path: Path) -> None:
        runtime = _FakeRuntime(replies=["Adım 1: hello.py yaz", "Şimdi test ekle", DONE_SENTINEL])
        sandbox = _FakeSandbox(workspace_path=str(tmp_path / "ws"))
        sandbox.configure_exec(lines=[b"opencode output\n"], exit_code=0)
        agent = _FakeCLIAgent()
        session, _, audit = _build_session(
            tmp_path,
            runtime=runtime,
            sandbox=sandbox,
            agent=agent,
        )

        outcome = await session.run()

        assert outcome == SessionState.COMPLETED
        assert len(sandbox.exec_calls) == 2  # two CLI invocations
        # First round flagged is_first_round=True, second False.
        assert agent.command_calls[0] == ("Adım 1: hello.py yaz", True)
        assert agent.command_calls[1] == ("Şimdi test ekle", False)
        cats = _categories(audit)
        assert {"selffork_jr.reply", "agent.invoke", "agent.output", "agent.done"} <= cats

    @pytest.mark.asyncio
    async def test_skip_verify_goes_running_to_completed_directly(
        self,
        tmp_path: Path,
    ) -> None:
        runtime = _FakeRuntime(replies=[DONE_SENTINEL])
        sandbox = _FakeSandbox(workspace_path=str(tmp_path / "ws"))
        agent = _FakeCLIAgent()
        session, _, audit = _build_session(
            tmp_path,
            runtime=runtime,
            sandbox=sandbox,
            agent=agent,
            skip_verify=True,
        )

        outcome = await session.run()
        assert outcome == SessionState.COMPLETED

        states_to: list[str] = []
        for rec in _read_audit(audit):
            if rec["category"] != "session.state":
                continue
            payload = rec["payload"]
            assert isinstance(payload, dict)
            states_to.append(str(payload["to"]))
        # skip_verify=True: RUNNING → COMPLETED directly, no VERIFYING in between.
        assert ("running", "verifying") not in pairwise(states_to)
        assert "completed" in states_to


class TestFailures:
    @pytest.mark.asyncio
    async def test_runtime_start_failure_short_circuits_to_failed(
        self,
        tmp_path: Path,
    ) -> None:
        runtime = _FakeRuntime(fail_start=True)
        sandbox = _FakeSandbox(workspace_path=str(tmp_path / "ws"))
        agent = _FakeCLIAgent()
        session, _, _ = _build_session(
            tmp_path,
            runtime=runtime,
            sandbox=sandbox,
            agent=agent,
        )

        outcome = await session.run()
        assert outcome == SessionState.FAILED
        assert session.state == SessionState.TORN_DOWN
        assert session.failure_reason is not None
        assert "fake start" in session.failure_reason
        assert sandbox.spawn_count == 0
        assert sandbox.teardown_count == 1
        assert runtime.stop_count == 1

    @pytest.mark.asyncio
    async def test_sandbox_spawn_failure_short_circuits_to_failed(
        self,
        tmp_path: Path,
    ) -> None:
        runtime = _FakeRuntime()
        sandbox = _FakeSandbox(
            workspace_path=str(tmp_path / "ws"),
            fail_spawn=True,
        )
        agent = _FakeCLIAgent()
        session, _, _ = _build_session(
            tmp_path,
            runtime=runtime,
            sandbox=sandbox,
            agent=agent,
        )
        outcome = await session.run()
        assert outcome == SessionState.FAILED
        assert "fake spawn" in (session.failure_reason or "")

    @pytest.mark.asyncio
    async def test_cli_nonzero_exit_fails(self, tmp_path: Path) -> None:
        runtime = _FakeRuntime(replies=["Step 1", DONE_SENTINEL])
        sandbox = _FakeSandbox(workspace_path=str(tmp_path / "ws"))
        sandbox.configure_exec(lines=[b"crashed\n"], exit_code=42)
        agent = _FakeCLIAgent()
        session, _, _ = _build_session(
            tmp_path,
            runtime=runtime,
            sandbox=sandbox,
            agent=agent,
        )
        outcome = await session.run()
        assert outcome == SessionState.FAILED
        assert "exited non-zero" in (session.failure_reason or "")

    @pytest.mark.asyncio
    async def test_max_rounds_without_sentinel_fails(self, tmp_path: Path) -> None:
        # Runtime never says DONE — give a single non-DONE reply that
        # repeats forever (queue exhausts → default DONE kicks in, so
        # we use a very low max_rounds and a fixed reply queue).
        runtime = _FakeRuntime(replies=["keep going"] * 50)
        sandbox = _FakeSandbox(workspace_path=str(tmp_path / "ws"))
        sandbox.configure_exec(lines=[b"ok\n"], exit_code=0)
        agent = _FakeCLIAgent()
        session, _, _ = _build_session(
            tmp_path,
            runtime=runtime,
            sandbox=sandbox,
            agent=agent,
            max_rounds=3,
        )
        outcome = await session.run()
        assert outcome == SessionState.FAILED
        assert "max_rounds" in (session.failure_reason or "")

    @pytest.mark.asyncio
    async def test_max_rounds_none_runs_until_sentinel(self, tmp_path: Path) -> None:
        # ``max_rounds=None`` means unlimited — the loop must run past the
        # legacy default of 20 and only stop when SelfFork Jr emits the
        # sentinel. We feed 25 non-sentinel replies followed by DONE.
        runtime = _FakeRuntime(
            replies=["keep going"] * 25 + [f"all done {DONE_SENTINEL}"],
        )
        sandbox = _FakeSandbox(workspace_path=str(tmp_path / "ws"))
        sandbox.configure_exec(lines=[b"ok\n"], exit_code=0)
        agent = _FakeCLIAgent()
        session, _, _ = _build_session(
            tmp_path,
            runtime=runtime,
            sandbox=sandbox,
            agent=agent,
            max_rounds=None,
        )
        outcome = await session.run()
        assert outcome == SessionState.COMPLETED
        # 25 non-sentinel rounds executed, then sentinel on round 26.
        assert len(agent.command_calls) == 25


class TestTeardownAlwaysRuns:
    @pytest.mark.asyncio
    async def test_teardown_runs_even_on_runtime_failure(self, tmp_path: Path) -> None:
        runtime = _FakeRuntime(fail_start=True)
        sandbox = _FakeSandbox(workspace_path=str(tmp_path / "ws"))
        agent = _FakeCLIAgent()
        session, _, _ = _build_session(
            tmp_path,
            runtime=runtime,
            sandbox=sandbox,
            agent=agent,
        )
        await session.run()
        assert sandbox.teardown_count == 1
        assert runtime.stop_count == 1

    @pytest.mark.asyncio
    async def test_state_is_torn_down_after_run(self, tmp_path: Path) -> None:
        runtime = _FakeRuntime(replies=[DONE_SENTINEL])
        sandbox = _FakeSandbox(workspace_path=str(tmp_path / "ws"))
        agent = _FakeCLIAgent()
        session, _, _ = _build_session(
            tmp_path,
            runtime=runtime,
            sandbox=sandbox,
            agent=agent,
        )
        await session.run()
        assert session.state == SessionState.TORN_DOWN
