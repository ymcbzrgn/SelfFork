"""Tests for :class:`LaunchdScheduler`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from selffork_orchestrator.resume.cron import (
    LaunchdScheduler,
    LaunchdSchedulerError,
    default_launch_agents_dir,
    is_macos,
)
from selffork_orchestrator.resume.store import ScheduledResume


def _record(session_id: str = "session-1") -> ScheduledResume:
    return ScheduledResume(
        session_id=session_id,
        scheduled_at=datetime.now(tz=UTC),
        resume_at=datetime.now(tz=UTC) + timedelta(hours=5),
        cli_agent="claude-code",
        config_path=None,
        prd_path="/run/prd.md",
        workspace_path="/run/work",
        reason="test rate-limit",
        kind="five_hour",
    )


def _ok_run(*_args: object, **_kwargs: object) -> SimpleNamespace:
    return SimpleNamespace(returncode=0, stderr="", stdout="")


def _fail_run(stderr: str = "boom") -> object:
    def _run(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=1, stderr=stderr, stdout="")

    return _run


# ── helpers ──────────────────────────────────────────────────────────────


def test_default_launch_agents_dir_under_home() -> None:
    assert default_launch_agents_dir() == Path.home() / "Library" / "LaunchAgents"


def test_is_macos_consistent() -> None:
    # Just verifies the helper returns a bool; the value depends on the host.
    assert isinstance(is_macos(), bool)


# ── label / path ─────────────────────────────────────────────────────────


def test_label_for_uses_default_prefix() -> None:
    sched = LaunchdScheduler()
    assert sched.label_for("abc-123") == "com.selffork.abc-123"


def test_label_for_sanitizes_dots_and_slashes() -> None:
    sched = LaunchdScheduler()
    assert sched.label_for("abc.def/ghi") == "com.selffork.abc-def-ghi"


def test_label_for_respects_custom_prefix() -> None:
    sched = LaunchdScheduler(label_prefix="dev.selffork")
    assert sched.label_for("xyz") == "dev.selffork.xyz"


def test_plist_path_uses_label_under_dir(tmp_path: Path) -> None:
    sched = LaunchdScheduler(launch_agents_dir=tmp_path)
    path = sched.plist_path("session-1")
    assert path.parent == tmp_path
    assert path.name == "com.selffork.session-1.plist"


# ── render ───────────────────────────────────────────────────────────────


def test_render_includes_session_id_and_executable(tmp_path: Path) -> None:
    sched = LaunchdScheduler(
        launch_agents_dir=tmp_path,
        selffork_executable="/usr/local/bin/selffork",
    )
    plist_xml = sched.render(_record("abc"))
    assert "<string>com.selffork.abc</string>" in plist_xml
    assert "<string>/usr/local/bin/selffork</string>" in plist_xml
    assert "<string>resume</string>" in plist_xml
    assert "<string>now</string>" in plist_xml
    assert "<string>abc</string>" in plist_xml
    assert "StartCalendarInterval" in plist_xml


def test_render_resolves_executable_via_path(tmp_path: Path) -> None:
    sched = LaunchdScheduler(launch_agents_dir=tmp_path)
    with patch(
        "selffork_orchestrator.resume.cron.shutil.which",
        return_value="/from/which/selffork",
    ):
        plist_xml = sched.render(_record("abc"))
    assert "<string>/from/which/selffork</string>" in plist_xml


def test_render_raises_when_executable_missing(tmp_path: Path) -> None:
    sched = LaunchdScheduler(launch_agents_dir=tmp_path)
    with (
        patch(
            "selffork_orchestrator.resume.cron.shutil.which",
            return_value=None,
        ),
        pytest.raises(LaunchdSchedulerError, match="selffork executable"),
    ):
        sched.render(_record("abc"))


# ── install / uninstall ──────────────────────────────────────────────────


def test_install_writes_plist_and_calls_launchctl(tmp_path: Path) -> None:
    sched = LaunchdScheduler(
        launch_agents_dir=tmp_path,
        selffork_executable="/usr/local/bin/selffork",
    )
    record = _record("abc")
    with patch(
        "selffork_orchestrator.resume.cron.subprocess.run",
        side_effect=_ok_run,
    ) as mock_run:
        path = sched.install(record)
    assert path.exists()
    assert "<string>com.selffork.abc</string>" in path.read_text(encoding="utf-8")
    mock_run.assert_called_once()
    args, _ = mock_run.call_args
    assert args[0][:3] == ["launchctl", "load", "-w"]


def test_install_raises_when_launchctl_fails(tmp_path: Path) -> None:
    sched = LaunchdScheduler(
        launch_agents_dir=tmp_path,
        selffork_executable="/usr/local/bin/selffork",
    )
    record = _record("abc")
    with (
        patch(
            "selffork_orchestrator.resume.cron.subprocess.run",
            side_effect=_fail_run("load failed: bad plist"),
        ),
        pytest.raises(LaunchdSchedulerError, match="load failed"),
    ):
        sched.install(record)
    # Plist file IS still on disk — keep it for operator inspection.
    assert sched.plist_path("abc").exists()


def test_uninstall_removes_existing_plist(tmp_path: Path) -> None:
    sched = LaunchdScheduler(
        launch_agents_dir=tmp_path,
        selffork_executable="/usr/local/bin/selffork",
    )
    path = sched.plist_path("abc")
    path.write_text("<plist/>", encoding="utf-8")
    with patch(
        "selffork_orchestrator.resume.cron.subprocess.run",
        side_effect=_ok_run,
    ) as mock_run:
        existed = sched.uninstall("abc")
    assert existed is True
    assert not path.exists()
    mock_run.assert_called_once()
    args, _ = mock_run.call_args
    assert args[0][:3] == ["launchctl", "unload", "-w"]


def test_uninstall_returns_false_when_plist_missing(tmp_path: Path) -> None:
    sched = LaunchdScheduler(launch_agents_dir=tmp_path)
    assert sched.uninstall("nonexistent") is False


def test_uninstall_swallows_launchctl_failure(tmp_path: Path) -> None:
    """launchctl unload errors should not block plist removal."""
    sched = LaunchdScheduler(
        launch_agents_dir=tmp_path,
        selffork_executable="/usr/local/bin/selffork",
    )
    path = sched.plist_path("abc")
    path.write_text("<plist/>", encoding="utf-8")
    with patch(
        "selffork_orchestrator.resume.cron.subprocess.run",
        side_effect=_fail_run("not loaded"),
    ):
        existed = sched.uninstall("abc")
    assert existed is True
    assert not path.exists()
