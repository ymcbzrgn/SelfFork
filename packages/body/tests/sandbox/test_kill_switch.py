"""BodyWatchdog — duration / idle caps + kill_session SIGKILL path."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from selffork_body.sandbox import BodyWatchdog, PermissionWarden, WardenMode


@pytest.fixture()
def watchdog() -> BodyWatchdog:
    return BodyWatchdog(
        poll_interval_sec=0.05,
        default_max_duration_sec=3600,
        default_idle_timeout_sec=60,
    )


def test_register_and_deregister(watchdog: BodyWatchdog) -> None:
    warden = PermissionWarden(mode=WardenMode.WORKSPACE_WRITE)
    watchdog.register(session_id="s-1", warden=warden)
    assert len(watchdog.list_sessions()) == 1
    watchdog.deregister("s-1")
    assert watchdog.list_sessions() == []


def test_heartbeat_updates_last_activity(watchdog: BodyWatchdog) -> None:
    warden = PermissionWarden(mode=WardenMode.WORKSPACE_WRITE)
    session = watchdog.register(session_id="s-1", warden=warden)
    initial = session.last_activity
    # Force a backdate then heartbeat.
    session.last_activity = initial - timedelta(seconds=10)
    watchdog.heartbeat("s-1")
    assert session.last_activity > initial - timedelta(seconds=10)


def test_check_session_max_duration(watchdog: BodyWatchdog) -> None:
    warden = PermissionWarden(mode=WardenMode.WORKSPACE_WRITE)
    session = watchdog.register(
        session_id="s-1", warden=warden, max_duration_sec=10
    )
    session.started_at = datetime.now(UTC) - timedelta(seconds=20)
    reason = watchdog._check_session(session, datetime.now(UTC))
    assert reason == "max_duration_exceeded"


def test_check_session_idle_timeout(watchdog: BodyWatchdog) -> None:
    warden = PermissionWarden(mode=WardenMode.WORKSPACE_WRITE)
    session = watchdog.register(
        session_id="s-1", warden=warden, idle_timeout_sec=5
    )
    session.last_activity = datetime.now(UTC) - timedelta(seconds=10)
    reason = watchdog._check_session(session, datetime.now(UTC))
    assert reason == "idle_timeout"


def test_kill_session_marks_killed_and_warden(watchdog: BodyWatchdog) -> None:
    warden = PermissionWarden(mode=WardenMode.WORKSPACE_WRITE)
    watchdog.register(session_id="s-1", warden=warden)
    assert watchdog.kill_session("s-1", "manual") is True
    sessions = watchdog.list_sessions()
    assert sessions[0].killed is True
    assert sessions[0].kill_reason == "manual"
    from selffork_body.sandbox import WardenState

    assert warden.state == WardenState.KILLED


def test_kill_unknown_session_returns_false(watchdog: BodyWatchdog) -> None:
    assert watchdog.kill_session("nope", "x") is False


async def test_loop_kills_idle_session() -> None:
    watchdog = BodyWatchdog(
        poll_interval_sec=0.02,
        default_max_duration_sec=3600,
        default_idle_timeout_sec=1,
    )
    warden = PermissionWarden(mode=WardenMode.WORKSPACE_WRITE)
    session = watchdog.register(session_id="s-1", warden=warden, idle_timeout_sec=1)
    # Backdate last_activity so the watchdog sees idle on first poll.
    session.last_activity = datetime.now(UTC) - timedelta(seconds=5)
    await watchdog.start()
    await asyncio.sleep(0.1)
    await watchdog.stop()
    assert session.killed is True
    assert session.kill_reason == "idle_timeout"


async def test_loop_skips_already_killed_sessions() -> None:
    watchdog = BodyWatchdog(poll_interval_sec=0.02)
    warden = PermissionWarden(mode=WardenMode.WORKSPACE_WRITE)
    watchdog.register(session_id="s-1", warden=warden)
    watchdog.kill_session("s-1", "first")
    await watchdog.start()
    await asyncio.sleep(0.05)
    await watchdog.stop()
    sessions = watchdog.list_sessions()
    # kill_reason stays "first" — second pass shouldn't overwrite.
    assert sessions[0].kill_reason == "first"
