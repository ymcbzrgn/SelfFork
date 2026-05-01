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
from selffork_orchestrator.lifecycle.session import (
    RateLimitHandler,
    Session,
    SpawnHandler,
)
from selffork_orchestrator.lifecycle.states import SessionState
from selffork_orchestrator.limits.base import (
    AuthRequired,
    LimitDetector,
    LimitVerdict,
    NoLimit,
    RateLimited,
)
from selffork_orchestrator.plan.store_filesystem import FilesystemPlanStore
from selffork_orchestrator.runtime.base import ChatMessage, LLMRuntime
from selffork_orchestrator.sandbox.base import Sandbox, SandboxProcess
from selffork_orchestrator.spawn.sentinel import SpawnRequest
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
    def __init__(
        self,
        lines: list[bytes],
        exit_code: int = 0,
        stderr_lines: list[bytes] | None = None,
    ) -> None:
        self._lines = lines
        self._stderr_lines = stderr_lines or []
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
        lines = self._stderr_lines

        async def gen() -> AsyncIterator[bytes]:
            for line in lines:
                yield line

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
        self._exec_stderr_lines: list[bytes] = []
        self._exec_exit_code = 0
        self.spawn_count = 0
        self.teardown_count = 0
        self.exec_calls: list[list[str]] = []

    def configure_exec(
        self,
        lines: list[bytes],
        exit_code: int = 0,
        stderr_lines: list[bytes] | None = None,
    ) -> None:
        self._exec_lines = lines
        self._exec_exit_code = exit_code
        self._exec_stderr_lines = stderr_lines or []

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
        return _FakeSandboxProcess(
            self._exec_lines,
            self._exec_exit_code,
            self._exec_stderr_lines,
        )

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
    limit_detector: LimitDetector | None = None,
    rate_limit_handler: RateLimitHandler | None = None,
    spawn_handler: SpawnHandler | None = None,
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
        limit_detector=limit_detector,
        rate_limit_handler=rate_limit_handler,
        spawn_handler=spawn_handler,
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


# ── Faz B: limit-detection integration ────────────────────────────────────────


class _ScriptedDetector(LimitDetector):
    """Test double that returns a queued verdict per call.

    Each ``detect()`` invocation pops the next verdict off the queue. If
    the queue empties, returns ``NoLimit`` so the loop keeps going (used
    to bound tests cleanly).
    """

    def __init__(self, verdicts: list[LimitVerdict]) -> None:
        self._verdicts = list(verdicts)
        self.calls: list[tuple[str, str, int]] = []

    def detect(self, *, stdout: str, stderr: str, exit_code: int) -> LimitVerdict:
        self.calls.append((stdout, stderr, exit_code))
        if not self._verdicts:
            return NoLimit()
        return self._verdicts.pop(0)


class TestLimitDetectorIntegration:
    @pytest.mark.asyncio
    async def test_rate_limited_pauses_and_persists(self, tmp_path: Path) -> None:
        from datetime import UTC, datetime, timedelta

        runtime = _FakeRuntime(replies=["instruction to opencode"] * 5)
        sandbox = _FakeSandbox(workspace_path=str(tmp_path / "ws"))
        sandbox.configure_exec(lines=[b"some opencode output\n"], exit_code=0)
        agent = _FakeCLIAgent()
        reset_at = datetime.now(UTC) + timedelta(hours=2)
        detector = _ScriptedDetector(
            [
                RateLimited(
                    reset_at=reset_at,
                    reason="synthetic quota in test",
                    kind="rpd",
                ),
            ],
        )
        captured: dict[str, object] = {}

        async def handler(*, session_id: str, verdict: RateLimited, last_round_text: str) -> None:
            captured["session_id"] = session_id
            captured["resume_at"] = verdict.reset_at
            captured["last_round_text"] = last_round_text

        session, _, audit = _build_session(
            tmp_path,
            runtime=runtime,
            sandbox=sandbox,
            agent=agent,
            limit_detector=detector,
            rate_limit_handler=handler,
        )
        outcome = await session.run()
        assert outcome == SessionState.PAUSED_RATE_LIMIT
        assert captured["session_id"] == "01HJTESTSESSIONABCDEFGHIJK"
        assert captured["resume_at"] == reset_at
        assert "instruction to opencode" in str(captured["last_round_text"])
        # Exactly one CLI call before the pause kicked in.
        assert len(agent.command_calls) == 1
        # Audit captured the pause as agent.rate_limited.
        assert "agent.rate_limited" in _categories(audit)

    @pytest.mark.asyncio
    async def test_auth_required_fails_session(self, tmp_path: Path) -> None:
        runtime = _FakeRuntime(replies=["a message"])
        sandbox = _FakeSandbox(workspace_path=str(tmp_path / "ws"))
        sandbox.configure_exec(lines=[b"some output\n"], exit_code=0)
        agent = _FakeCLIAgent()
        detector = _ScriptedDetector([AuthRequired(reason="test re-login")])
        session, _, audit = _build_session(
            tmp_path,
            runtime=runtime,
            sandbox=sandbox,
            agent=agent,
            limit_detector=detector,
        )
        outcome = await session.run()
        assert outcome == SessionState.FAILED
        assert "re-login" in (session.failure_reason or "")
        assert "agent.auth_required" in _categories(audit)

    @pytest.mark.asyncio
    async def test_no_limit_keeps_running(self, tmp_path: Path) -> None:
        # When the detector says NoLimit on every call, the loop should
        # behave exactly like the no-detector case — terminate via the
        # DONE sentinel after the work round. Two replies: first triggers
        # an exec (and a detector check), second carries the sentinel.
        runtime = _FakeRuntime(
            replies=["work instruction", f"all done {DONE_SENTINEL}"],
        )
        sandbox = _FakeSandbox(workspace_path=str(tmp_path / "ws"))
        sandbox.configure_exec(lines=[b"output\n"], exit_code=0)
        agent = _FakeCLIAgent()
        detector = _ScriptedDetector([NoLimit()])
        session, _, _ = _build_session(
            tmp_path,
            runtime=runtime,
            sandbox=sandbox,
            agent=agent,
            limit_detector=detector,
        )
        outcome = await session.run()
        assert outcome == SessionState.COMPLETED
        # Detector saw exactly the one exec'd round (the DONE round
        # short-circuits before exec, so no detect() call).
        assert len(detector.calls) == 1


# ── Faz A: SPAWN integration ──────────────────────────────────────────────────


class TestSpawnIntegration:
    @pytest.mark.asyncio
    async def test_spawn_aggregates_and_continues(self, tmp_path: Path) -> None:
        # Round 0: Jr emits two SPAWN tags. Round 1: handler-aggregated
        # output is fed back, Jr decides DONE.
        spawn_reply = (
            "Two parallel jobs:\n"
            "[SELFFORK:SPAWN: Build divide.py and test]\n"
            "[SELFFORK:SPAWN: Build subtract.py and test]\n"
        )
        runtime = _FakeRuntime(
            replies=[spawn_reply, f"Both done — finalizing. {DONE_SENTINEL}"],
        )
        sandbox = _FakeSandbox(workspace_path=str(tmp_path / "ws"))
        sandbox.configure_exec(lines=[b"output\n"], exit_code=0)
        agent = _FakeCLIAgent()

        captured_calls = 0
        captured_parent: str | None = None
        captured_specs: list[str] = []

        async def handler(*, parent_session_id: str, requests: list[SpawnRequest]) -> str:
            nonlocal captured_calls, captured_parent, captured_specs
            captured_calls += 1
            captured_parent = parent_session_id
            captured_specs = [r.spec for r in requests]
            return "AGGREGATED-CHILD-OUTPUT"

        session, _, audit = _build_session(
            tmp_path,
            runtime=runtime,
            sandbox=sandbox,
            agent=agent,
            spawn_handler=handler,
        )
        outcome = await session.run()
        assert outcome == SessionState.COMPLETED
        # Handler fired once (round 0 SPAWN), and not again on the DONE round.
        assert captured_calls == 1
        assert captured_parent == "01HJTESTSESSIONABCDEFGHIJK"
        assert captured_specs == [
            "Build divide.py and test",
            "Build subtract.py and test",
        ]
        # CLI agent NEVER ran for the SPAWN round (handler replaced exec).
        # Only the DONE round bypasses exec too, so command_calls should be empty.
        assert agent.command_calls == []
        # Audit recorded the spawn lifecycle.
        cats = _categories(audit)
        assert "agent.spawn_request" in cats
        assert "agent.spawn_complete" in cats

        # Aggregated text became the next user-role message in chat history.
        # Verify by looking at the second chat call's last user message.
        assert len(runtime.chat_calls) == 2
        last_messages = runtime.chat_calls[1]
        assert last_messages[-1]["role"] == "user"
        assert "AGGREGATED-CHILD-OUTPUT" in last_messages[-1]["content"]

    @pytest.mark.asyncio
    async def test_spawn_without_handler_fails(self, tmp_path: Path) -> None:
        # No spawn_handler wired: Jr's SPAWN must fail-fast, not silently
        # drop. Otherwise Jr believes children ran when they didn't.
        spawn_reply = "[SELFFORK:SPAWN: build foo.py]"
        runtime = _FakeRuntime(replies=[spawn_reply])
        sandbox = _FakeSandbox(workspace_path=str(tmp_path / "ws"))
        sandbox.configure_exec(lines=[b"output\n"], exit_code=0)
        agent = _FakeCLIAgent()
        session, _, _ = _build_session(
            tmp_path,
            runtime=runtime,
            sandbox=sandbox,
            agent=agent,
        )
        outcome = await session.run()
        assert outcome == SessionState.FAILED
        assert "spawn" in (session.failure_reason or "").lower()

    @pytest.mark.asyncio
    async def test_done_takes_priority_over_spawn(self, tmp_path: Path) -> None:
        # When a single Jr reply contains BOTH a SPAWN tag and the DONE
        # sentinel, the orchestrator finishes — it never invokes the
        # spawn handler. This is the documented Faz A safety rule.
        mixed = f"[SELFFORK:SPAWN: build leftover.py]\nAll done. {DONE_SENTINEL}"
        runtime = _FakeRuntime(replies=[mixed])
        sandbox = _FakeSandbox(workspace_path=str(tmp_path / "ws"))
        sandbox.configure_exec(lines=[b"x\n"], exit_code=0)
        agent = _FakeCLIAgent()

        async def handler_should_not_run(
            *, parent_session_id: str, requests: list[SpawnRequest]
        ) -> str:
            del parent_session_id, requests
            raise AssertionError("spawn handler called despite DONE in same reply")

        session, _, _ = _build_session(
            tmp_path,
            runtime=runtime,
            sandbox=sandbox,
            agent=agent,
            spawn_handler=handler_should_not_run,
        )
        outcome = await session.run()
        assert outcome == SessionState.COMPLETED


# ── Tool calls integration ───────────────────────────────────────────────────


class TestToolIntegration:
    @pytest.mark.asyncio
    async def test_kanban_card_done_call_persists_and_aggregates(
        self,
        tmp_path: Path,
    ) -> None:
        # Stage: project + a kanban card waiting in 'in_progress'.
        from selffork_orchestrator.projects.store import ProjectStore
        from selffork_orchestrator.tools import build_default_registry

        projects_root = tmp_path / "projects"
        store = ProjectStore(root=projects_root)
        store.create(name="ToolTest")
        seeded = store.add_card("tooltest", title="ship feature")
        store.move_card("tooltest", seeded.id, to_column="in_progress")

        # Round 0: Jr emits a tool call. Round 1: Jr emits DONE.
        tool_reply = (
            "Got it.\n"
            "<selffork-tool-call>\n"
            f'{{"tool": "kanban_card_done", "args": {{"card_id": "{seeded.id}"}}}}\n'
            "</selffork-tool-call>"
        )
        runtime = _FakeRuntime(replies=[tool_reply, f"all done {DONE_SENTINEL}"])
        sandbox = _FakeSandbox(workspace_path=str(tmp_path / "ws"))
        sandbox.configure_exec(lines=[b"output\n"], exit_code=0)
        agent = _FakeCLIAgent()

        session, _, audit = _build_session(
            tmp_path,
            runtime=runtime,
            sandbox=sandbox,
            agent=agent,
        )
        # Inject tool registry + project context onto the existing session
        # rather than threading even more args through _build_session.
        session._tool_registry = build_default_registry()
        session._project_slug = "tooltest"
        session._project_store = store

        outcome = await session.run()
        assert outcome == SessionState.COMPLETED

        # The card actually moved to 'done' on disk.
        board = store.load_board("tooltest")
        card = board.find(seeded.id)
        assert card is not None
        assert card.column == "done"
        assert card.completed_at is not None
        assert card.last_touched_by_session_id == "01HJTESTSESSIONABCDEFGHIJK"

        # CLI agent was NEVER invoked — the tool call short-circuits the
        # exec path on round 0, and round 1's DONE sentinel terminates.
        assert agent.command_calls == []

        # Audit recorded both tool.call + tool.result, in order.
        cats = _categories(audit)
        assert "tool.call" in cats
        assert "tool.result" in cats

    @pytest.mark.asyncio
    async def test_invalid_tool_call_returns_error_to_jr(
        self,
        tmp_path: Path,
    ) -> None:
        from selffork_orchestrator.projects.store import ProjectStore
        from selffork_orchestrator.tools import build_default_registry

        store = ProjectStore(root=tmp_path / "projects")
        store.create(name="X")

        # Jr emits a malformed-args call (missing card_id) on round 0,
        # then sees the error in user-role text and emits DONE on round 1.
        bad = '<selffork-tool-call>{"tool": "kanban_card_done", "args": {}}</selffork-tool-call>'
        runtime = _FakeRuntime(replies=[bad, f"oh well {DONE_SENTINEL}"])
        sandbox = _FakeSandbox(workspace_path=str(tmp_path / "ws"))
        sandbox.configure_exec(lines=[b"output\n"], exit_code=0)
        agent = _FakeCLIAgent()

        session, _, _ = _build_session(
            tmp_path,
            runtime=runtime,
            sandbox=sandbox,
            agent=agent,
        )
        session._tool_registry = build_default_registry()
        session._project_slug = "x"
        session._project_store = store

        outcome = await session.run()
        assert outcome == SessionState.COMPLETED

        # The error appeared in the second chat call's last user message
        # so Jr could react to it.
        assert len(runtime.chat_calls) == 2
        last = runtime.chat_calls[1][-1]
        assert last["role"] == "user"
        assert "invalid_args" in last["content"]


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
