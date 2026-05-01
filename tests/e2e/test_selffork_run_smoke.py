"""End-to-end smoke test for ``selffork run`` (round-loop architecture).

Drives the full CLI → Session → runtime/sandbox/cli_agent → plan-store /
audit chain without needing real mlx-lm or real opencode:

* The LLM runtime is stubbed via ``build_runtime`` monkeypatch — returns a
  fake that emits one SelfFork-Jr reply queue.
* ``opencode`` is replaced by a tiny shell script that prints a plain-text
  acknowledgement and exits 0 (round-loop architecture; no stream-json).
* The sandbox is real (subprocess mode). Plan-store + audit are real.

Maps to ADR-001 §16.1 done-criterion #1 in stub form.
"""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Sequence
from pathlib import Path

import pytest
from typer.testing import CliRunner

from selffork_orchestrator import cli as cli_module
from selffork_orchestrator.cli import app
from selffork_orchestrator.cli_agent.opencode import DONE_SENTINEL
from selffork_orchestrator.runtime.base import ChatMessage, LLMRuntime
from selffork_shared.config import RuntimeConfig

# Tiny fake-opencode: prints something plausible, exits 0. The orchestrator
# captures stdout and feeds it back to SelfFork Jr as the next user message.
_FAKE_OPENCODE_SCRIPT = """#!/usr/bin/env python3
import sys
print("opencode: pretending to do the work — wrote hello.py.")
sys.exit(0)
"""


class _NoOpRuntime(LLMRuntime):
    """Runtime fake — pretends to be healthy without spawning a process.

    Hands out canned SelfFork-Jr replies in order; the last one carries the
    DONE sentinel so the orchestrator stops cleanly.
    """

    def __init__(self, config: RuntimeConfig) -> None:
        self._config = config
        self._replies = [
            "Hadi başla, hello.py yaz lütfen.",
            f"Yazdın mı? Tamam, kontrol ettim, iyi gözüküyor.\n{DONE_SENTINEL}",
        ]
        self._idx = 0

    async def start(self) -> None:
        return

    async def stop(self) -> None:
        return

    @property
    def base_url(self) -> str:
        return "http://127.0.0.1:65535/v1"

    @property
    def model_id(self) -> str:
        return self._config.model_id

    async def health(self) -> bool:
        return True

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


def _write_fake_opencode(target_dir: Path) -> Path:
    binary = target_dir / "fake-opencode"
    binary.write_text(_FAKE_OPENCODE_SCRIPT, encoding="utf-8")
    binary.chmod(
        binary.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH,
    )
    return binary


def test_selffork_run_subprocess_smoke(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full round-loop ``selffork run`` against fake runtime + fake opencode."""
    monkeypatch.setattr(
        cli_module,
        "build_runtime",
        lambda cfg: _NoOpRuntime(cfg),
    )

    fake_bin = _write_fake_opencode(tmp_path)
    prd = tmp_path / "prd.md"
    prd.write_text(
        "# Hello world\n\nWrite a tiny hello.py that prints 'hello'.\n",
        encoding="utf-8",
    )

    workspace_root = tmp_path / "workspaces"
    audit_dir = tmp_path / "audit"
    log_dir = tmp_path / "logs"

    config_path = tmp_path / "selffork.yaml"
    config_path.write_text(
        f"""
sandbox:
  mode: subprocess
  workspace_root: {workspace_root}
  timeout_seconds: 30

cli_agent:
  agent: opencode
  binary_path: {fake_bin}

audit:
  enabled: true
  audit_dir: {audit_dir}
  redact_secrets: false

logging:
  level: WARNING
  json_output: true
  log_dir: {log_dir}

lifecycle:
  max_rounds: 5
""",
        encoding="utf-8",
    )

    for key in list(os.environ):
        if key.startswith("SELFFORK_"):
            monkeypatch.delenv(key, raising=False)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["run", str(prd), "--config", str(config_path)],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, f"selffork run failed: {result.output!r}"
    assert "completed successfully" in result.output

    workspaces = list(workspace_root.iterdir())
    assert len(workspaces) == 1, f"expected one session workspace, got {workspaces}"
    workspace = workspaces[0]
    plan_file = workspace / ".selffork" / "plan.json"
    assert plan_file.is_file()
    plan_data = json.loads(plan_file.read_text(encoding="utf-8"))
    assert plan_data["prd_path"] == str(prd)

    audit_files = list(audit_dir.iterdir())
    assert len(audit_files) == 1
    audit_records = [
        json.loads(line) for line in audit_files[0].read_text(encoding="utf-8").strip().splitlines()
    ]
    categories = {r["category"] for r in audit_records}
    # New round-loop categories.
    assert {
        "session.state",
        "runtime.spawn",
        "sandbox.spawn",
        "agent.spawn",
        "selffork_jr.reply",
        "agent.invoke",
        "agent.output",
        "agent.done",
        "sandbox.teardown",
        "runtime.stop",
    } <= categories

    states_to: list[str] = []
    for record in audit_records:
        if record["category"] != "session.state":
            continue
        payload = record["payload"]
        assert isinstance(payload, dict)
        states_to.append(str(payload["to"]))
    assert "completed" in states_to
    assert "torn_down" in states_to
    assert states_to[-1] == "torn_down"

    # The fake runtime emits one non-DONE reply followed by DONE → 1 CLI invocation.
    invoke_records = [r for r in audit_records if r["category"] == "agent.invoke"]
    assert len(invoke_records) == 1
