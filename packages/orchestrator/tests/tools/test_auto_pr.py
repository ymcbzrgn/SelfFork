"""S-Vision Faz E — auto_pr_create tool tests."""

from __future__ import annotations

import subprocess
from typing import Any

import pytest
from pydantic import ValidationError

from selffork_orchestrator.tools import build_default_registry
from selffork_orchestrator.tools.auto_pr import (
    _auto_pr_create_handler,
    _AutoPRCreateArgs,
    build_auto_pr_tools,
)
from selffork_orchestrator.tools.base import ToolContext

# ── Helpers ──────────────────────────────────────────────────────────


def _ctx() -> ToolContext:
    return ToolContext(
        session_id="01HJTESTSESSIONABCDEFGHIJK",
        project_slug=None,
        project_store=object(),
    )


def _completed(
    *, returncode: int, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["gh"], returncode=returncode, stdout=stdout, stderr=stderr
    )


# ── Args validation ──────────────────────────────────────────────────


def test_args_reject_empty_title() -> None:
    with pytest.raises(ValidationError):
        _AutoPRCreateArgs(title="", body="ok")


def test_args_reject_empty_body() -> None:
    with pytest.raises(ValidationError):
        _AutoPRCreateArgs(title="ok", body="")


def test_args_defaults_base_main_no_head_not_draft() -> None:
    a = _AutoPRCreateArgs(title="Add login", body="body text")
    assert a.base == "main"
    assert a.head is None
    assert a.draft is False


def test_args_extra_field_silently_ignored() -> None:
    """ToolArgs base intentionally uses ``extra='ignore'`` (per its
    docstring) so old Jr training data with new field names still parses;
    extra keys are silently dropped, NOT rejected."""
    args = _AutoPRCreateArgs.model_validate(
        {"title": "t", "body": "b", "sneaky": "dropped"}
    )
    assert args.title == "t"
    assert not hasattr(args, "sneaky")


# ── Handler — gh missing ─────────────────────────────────────────────


def test_handler_missing_gh_binary_returns_structured_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "selffork_orchestrator.tools.auto_pr._gh_binary",
        lambda: None,
    )
    result = _auto_pr_create_handler(
        _ctx(),
        _AutoPRCreateArgs(title="t", body="b"),
    )
    assert result["status"] == "missing_binary"
    assert "gh CLI not found" in result["error"]


# ── Handler — gh success ─────────────────────────────────────────────


def test_handler_success_parses_url_and_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "selffork_orchestrator.tools.auto_pr._gh_binary",
        lambda: "/usr/local/bin/gh",
    )
    monkeypatch.setattr(
        "selffork_orchestrator.tools.auto_pr.subprocess.run",
        lambda *a, **kw: _completed(
            returncode=0,
            stdout="https://github.com/ymcbzrgn/SelfFork/pull/42\n",
        ),
    )
    result = _auto_pr_create_handler(
        _ctx(),
        _AutoPRCreateArgs(title="Add login", body="Login flow", draft=True),
    )
    assert result["status"] == "ok"
    assert result["url"] == "https://github.com/ymcbzrgn/SelfFork/pull/42"
    assert result["number"] == 42
    assert result["base"] == "main"
    assert result["draft"] is True


def test_handler_passes_args_to_gh_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = list(args[0])
        return _completed(
            returncode=0,
            stdout="https://github.com/x/y/pull/7",
        )

    monkeypatch.setattr(
        "selffork_orchestrator.tools.auto_pr._gh_binary",
        lambda: "/bin/gh",
    )
    monkeypatch.setattr(
        "selffork_orchestrator.tools.auto_pr.subprocess.run",
        fake_run,
    )
    _auto_pr_create_handler(
        _ctx(),
        _AutoPRCreateArgs(
            title="t",
            body="b",
            base="develop",
            head="feature/login",
            draft=True,
        ),
    )
    cmd = captured["cmd"]
    assert cmd[0] == "/bin/gh"
    assert cmd[1:3] == ["pr", "create"]
    assert "--title" in cmd
    assert "--body" in cmd
    assert "--base" in cmd and "develop" in cmd
    assert "--head" in cmd and "feature/login" in cmd
    assert "--draft" in cmd


def test_handler_omits_head_and_draft_when_not_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = list(args[0])
        return _completed(returncode=0, stdout="https://github.com/x/y/pull/1")

    monkeypatch.setattr(
        "selffork_orchestrator.tools.auto_pr._gh_binary", lambda: "/bin/gh"
    )
    monkeypatch.setattr(
        "selffork_orchestrator.tools.auto_pr.subprocess.run", fake_run
    )
    _auto_pr_create_handler(
        _ctx(),
        _AutoPRCreateArgs(title="t", body="b"),
    )
    assert "--head" not in captured["cmd"]
    assert "--draft" not in captured["cmd"]


# ── Handler — gh failures ────────────────────────────────────────────


def test_handler_gh_nonzero_returns_gh_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "selffork_orchestrator.tools.auto_pr._gh_binary", lambda: "/bin/gh"
    )
    monkeypatch.setattr(
        "selffork_orchestrator.tools.auto_pr.subprocess.run",
        lambda *a, **kw: _completed(
            returncode=1,
            stderr="Could not authenticate to github.com",
        ),
    )
    result = _auto_pr_create_handler(
        _ctx(),
        _AutoPRCreateArgs(title="t", body="b"),
    )
    assert result["status"] == "gh_error"
    assert result["exit_code"] == 1
    assert "Could not authenticate" in result["stderr"]


def test_handler_no_url_in_stdout_returns_no_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "selffork_orchestrator.tools.auto_pr._gh_binary", lambda: "/bin/gh"
    )
    monkeypatch.setattr(
        "selffork_orchestrator.tools.auto_pr.subprocess.run",
        lambda *a, **kw: _completed(
            returncode=0,
            stdout="OK but no URL emitted\n",
        ),
    )
    result = _auto_pr_create_handler(
        _ctx(),
        _AutoPRCreateArgs(title="t", body="b"),
    )
    assert result["status"] == "no_url"


def test_handler_subprocess_timeout_returns_structured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "selffork_orchestrator.tools.auto_pr._gh_binary", lambda: "/bin/gh"
    )

    def fake_run(*a: Any, **kw: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=["gh"], timeout=60)

    monkeypatch.setattr(
        "selffork_orchestrator.tools.auto_pr.subprocess.run", fake_run
    )
    result = _auto_pr_create_handler(
        _ctx(),
        _AutoPRCreateArgs(title="t", body="b"),
    )
    assert result["status"] == "timeout"
    assert result["timeout_seconds"] == 60


# ── Builder + registry ───────────────────────────────────────────────


def test_build_auto_pr_tools_returns_one_spec() -> None:
    specs = build_auto_pr_tools()
    assert len(specs) == 1
    assert specs[0].name == "auto_pr_create"


def test_default_registry_includes_auto_pr_create() -> None:
    registry = build_default_registry()
    assert "auto_pr_create" in registry.names()
