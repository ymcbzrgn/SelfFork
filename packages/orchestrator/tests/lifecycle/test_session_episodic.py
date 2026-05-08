"""Session ↔ Mind T2 Episodic integration tests.

Wires a real :class:`DuckDBMindStore` + :class:`EpisodicWriter` into
``Session`` and verifies the round-loop hook fires for each path
(immediate-done, CLI exec, tool call). Audit log gains a
``mind.note.write`` entry per round.

Inlines minimal fakes for runtime/sandbox/CLI-agent rather than coupling
to ``test_session.py``'s private fakes — the integration concerns are
orthogonal to the round-loop validation those tests already cover.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping, Sequence
from pathlib import Path

import pytest

from selffork_mind.memory.tiers import EpisodicWriter
from selffork_mind.store import (
    DuckDBMindStore,
    RetrieveConfig,
    StoreScope,
)
from selffork_orchestrator.cli_agent.base import CLIAgent
from selffork_orchestrator.cli_agent.opencode import DONE_SENTINEL
from selffork_orchestrator.lifecycle.session import Session
from selffork_orchestrator.lifecycle.states import SessionState
from selffork_orchestrator.plan.store_filesystem import FilesystemPlanStore
from selffork_orchestrator.runtime.base import ChatMessage, LLMRuntime
from selffork_orchestrator.sandbox.base import Sandbox, SandboxProcess
from selffork_orchestrator.tools.base import (
    ToolArgs,
    ToolContext,
    ToolRegistry,
    ToolSpec,
)
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


# ── helpers ───────────────────────────────────────────────────────────────


async def _build_session_with_episodic(
    tmp_path: Path,
    *,
    runtime: _FakeRuntime,
    sandbox: _FakeSandbox,
    agent: _FakeCLIAgent,
    project_slug: str | None = "p1",
    cli_agent_name: str = "claude-code",
    tool_registry: ToolRegistry | None = None,
) -> tuple[Session, DuckDBMindStore, AuditLogger]:
    workspace = Path(sandbox.host_workspace_path)
    workspace.mkdir(parents=True, exist_ok=True)

    plan_cfg = PlanConfig(backend="filesystem", plan_filename=".selffork/plan.json")
    plan_store = FilesystemPlanStore(plan_cfg, workspace_path=str(workspace))
    audit_cfg = AuditConfig(enabled=True, audit_dir=str(tmp_path / "audit"))
    audit = AuditLogger(audit_cfg, session_id="01HJTESTSESSIONABCDEFGHIJK")

    mind_store = DuckDBMindStore(db_path=tmp_path / "mind.duckdb")
    await mind_store.setup()
    writer = EpisodicWriter(store=mind_store)

    session = Session(
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
        project_slug=project_slug,
        episodic_writer=writer,
        cli_agent_name=cli_agent_name,
        tool_registry=tool_registry,
    )
    return session, mind_store, audit


def _categories_in_audit(audit: AuditLogger) -> list[str]:
    assert audit.path is not None
    return [
        json.loads(line)["category"]
        for line in audit.path.read_text(encoding="utf-8").strip().splitlines()
    ]


# ── tests ─────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_immediate_done_does_not_write_episodic(tmp_path: Path) -> None:
    runtime = _FakeRuntime(replies=[DONE_SENTINEL])
    sandbox = _FakeSandbox(workspace_path=str(tmp_path / "ws"))
    agent = _FakeCLIAgent()
    session, mind_store, audit = await _build_session_with_episodic(
        tmp_path,
        runtime=runtime,
        sandbox=sandbox,
        agent=agent,
    )
    try:
        outcome = await session.run()
        assert outcome == SessionState.COMPLETED
        hits = await mind_store.retrieve(RetrieveConfig(tiers=("episodic",)))
        assert hits == []
        cats = _categories_in_audit(audit)
        assert "mind.note.write" not in cats
    finally:
        await mind_store.teardown()


@pytest.mark.anyio
async def test_cli_round_writes_episodic_observation(tmp_path: Path) -> None:
    runtime = _FakeRuntime(replies=["İlk adımı at", DONE_SENTINEL])
    sandbox = _FakeSandbox(workspace_path=str(tmp_path / "ws"))
    sandbox.configure_exec(lines=[b"cli wrote stuff\n"], exit_code=0)
    agent = _FakeCLIAgent()
    session, mind_store, audit = await _build_session_with_episodic(
        tmp_path,
        runtime=runtime,
        sandbox=sandbox,
        agent=agent,
    )
    try:
        outcome = await session.run()
        assert outcome == SessionState.COMPLETED
        hits = await mind_store.retrieve(
            RetrieveConfig(
                tiers=("episodic",),
                scope=StoreScope(project_slug="p1"),
            ),
        )
        assert len(hits) == 1
        note = hits[0].note
        assert note.kind == "observation"
        assert "İlk adımı at" in note.content
        assert "cli wrote stuff" in note.content
        assert note.session_id == "01HJTESTSESSIONABCDEFGHIJK"
        assert note.project_slug == "p1"
        tags = await mind_store.list_tags(note.id)
        as_pairs = {(t.key, t.value) for t in tags}
        assert ("project", "p1") in as_pairs
        assert ("cli", "claude-code") in as_pairs
        assert ("round", "0") in as_pairs
        cats = _categories_in_audit(audit)
        assert cats.count("mind.note.write") == 1
    finally:
        await mind_store.teardown()


class _DemoArgs(ToolArgs):
    name: str


def _demo_handler(_: ToolContext, args: _DemoArgs) -> dict[str, object]:
    return {"echo": args.name}


@pytest.mark.anyio
async def test_tool_round_writes_observation_plus_pattern(tmp_path: Path) -> None:
    tool_call_block = (
        "<selffork-tool-call>\n"
        '{"tool": "demo_tool", "args": {"name": "alice"}}\n'
        "</selffork-tool-call>"
    )
    runtime = _FakeRuntime(replies=[tool_call_block, DONE_SENTINEL])
    sandbox = _FakeSandbox(workspace_path=str(tmp_path / "ws"))
    agent = _FakeCLIAgent()
    registry = ToolRegistry(
        specs=[
            ToolSpec(
                name="demo_tool",
                description="echo back the args",
                args_model=_DemoArgs,
                handler=_demo_handler,
            ),
        ],
    )
    session, mind_store, audit = await _build_session_with_episodic(
        tmp_path,
        runtime=runtime,
        sandbox=sandbox,
        agent=agent,
        tool_registry=registry,
    )
    try:
        outcome = await session.run()
        assert outcome == SessionState.COMPLETED
        hits = await mind_store.retrieve(RetrieveConfig(tiers=("episodic",)))
        kinds = sorted(h.note.kind for h in hits)
        assert kinds == ["observation", "pattern"]
        pattern = next(h.note for h in hits if h.note.kind == "pattern")
        assert "demo_tool" in pattern.content
        assert "alice" in pattern.content
        assert sandbox.exec_calls == []
        cats = _categories_in_audit(audit)
        assert cats.count("mind.note.write") == 1
        assert "tool.call" in cats
        assert "tool.result" in cats
    finally:
        await mind_store.teardown()


@pytest.mark.anyio
async def test_orphan_session_no_project_slug_tag(tmp_path: Path) -> None:
    runtime = _FakeRuntime(replies=["devam", DONE_SENTINEL])
    sandbox = _FakeSandbox(workspace_path=str(tmp_path / "ws"))
    sandbox.configure_exec(lines=[b"ok\n"], exit_code=0)
    agent = _FakeCLIAgent()
    session, mind_store, _ = await _build_session_with_episodic(
        tmp_path,
        runtime=runtime,
        sandbox=sandbox,
        agent=agent,
        project_slug=None,
    )
    try:
        outcome = await session.run()
        assert outcome == SessionState.COMPLETED
        hits = await mind_store.retrieve(RetrieveConfig(tiers=("episodic",)))
        assert len(hits) == 1
        note = hits[0].note
        tags = await mind_store.list_tags(note.id)
        assert all(t.key != "project" for t in tags)
        assert any(t.key == "session" for t in tags)
    finally:
        await mind_store.teardown()


@pytest.mark.anyio
async def test_session_without_episodic_writer_no_op(tmp_path: Path) -> None:
    runtime = _FakeRuntime(replies=["go", DONE_SENTINEL])
    sandbox = _FakeSandbox(workspace_path=str(tmp_path / "ws"))
    sandbox.configure_exec(lines=[b"ok\n"], exit_code=0)
    agent = _FakeCLIAgent()

    workspace = Path(sandbox.host_workspace_path)
    workspace.mkdir(parents=True, exist_ok=True)
    plan_cfg = PlanConfig(backend="filesystem", plan_filename=".selffork/plan.json")
    plan_store = FilesystemPlanStore(plan_cfg, workspace_path=str(workspace))
    audit_cfg = AuditConfig(enabled=True, audit_dir=str(tmp_path / "audit"))
    audit = AuditLogger(audit_cfg, session_id="01HJTESTSESSIONABCDEFGHIJK")

    session = Session(
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
    )
    outcome = await session.run()
    assert outcome == SessionState.COMPLETED
    cats = _categories_in_audit(audit)
    assert "mind.note.write" not in cats
