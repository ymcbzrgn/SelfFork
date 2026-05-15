"""BodyWatchdog — global kill switch + duration / idle caps for body sessions.

Per ADR-005 §M5-D2:

* Process group SIGKILL (not "agent.stop()") to enforce.
* Max session duration cap (default 1800s).
* Idle timeout (default 120s — no action received in window → terminate).
* Operator hooks: Cockpit "Stop" button + Telegram ``/stop`` command both
  call :meth:`kill_session`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from selffork_body.sandbox.warden import PermissionWarden

__all__ = ["BodyWatchdog", "WatchedSession"]

_log = logging.getLogger(__name__)


@dataclass
class WatchedSession:
    session_id: str
    warden: PermissionWarden
    pid: int | None
    started_at: datetime
    last_activity: datetime
    max_duration_sec: int
    idle_timeout_sec: int
    killed: bool = False
    kill_reason: str | None = None


@dataclass
class BodyWatchdog:
    """Periodically scans active sessions and enforces caps.

    Caller wires this with the orchestrator's lifecycle: register on
    ``body.driver.start``, heartbeat on every ``body.action.invoke``,
    deregister on ``body.driver.stop``.
    """

    poll_interval_sec: float = 1.0
    default_max_duration_sec: int = 1800
    default_idle_timeout_sec: int = 120
    _sessions: dict[str, WatchedSession] = field(default_factory=dict)
    _task: asyncio.Task[None] | None = None
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event)

    def register(
        self,
        *,
        session_id: str,
        warden: PermissionWarden,
        pid: int | None = None,
        max_duration_sec: int | None = None,
        idle_timeout_sec: int | None = None,
    ) -> WatchedSession:
        now = datetime.now(UTC)
        session = WatchedSession(
            session_id=session_id,
            warden=warden,
            pid=pid,
            started_at=now,
            last_activity=now,
            max_duration_sec=max_duration_sec or self.default_max_duration_sec,
            idle_timeout_sec=idle_timeout_sec or self.default_idle_timeout_sec,
        )
        self._sessions[session_id] = session
        return session

    def heartbeat(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session and not session.killed:
            session.last_activity = datetime.now(UTC)

    def deregister(self, session_id: str) -> WatchedSession | None:
        return self._sessions.pop(session_id, None)

    def list_sessions(self) -> list[WatchedSession]:
        return list(self._sessions.values())

    def _send_kill(self, session: WatchedSession) -> None:
        """SIGKILL the process group (not the agent — the daemon itself)."""
        if session.pid is None:
            return
        try:
            os.killpg(os.getpgid(session.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError) as exc:  # pragma: no cover - OS-dependent
            _log.warning("watchdog_kill_failed pid=%s err=%s", session.pid, exc)

    def kill_session(self, session_id: str, reason: str) -> bool:
        session = self._sessions.get(session_id)
        if session is None or session.killed:
            return False
        session.killed = True
        session.kill_reason = reason
        session.warden.kill(reason)
        self._send_kill(session)
        return True

    def _check_session(self, session: WatchedSession, now: datetime) -> str | None:
        """Return kill reason if cap exceeded; else None."""
        if session.killed:
            return None
        if now - session.started_at > timedelta(seconds=session.max_duration_sec):
            return "max_duration_exceeded"
        if now - session.last_activity > timedelta(seconds=session.idle_timeout_sec):
            return "idle_timeout"
        return None

    async def _loop(self) -> None:
        while not self._stop_event.is_set():
            now = datetime.now(UTC)
            for session in list(self._sessions.values()):
                reason = self._check_session(session, now)
                if reason:
                    self.kill_session(session.session_id, reason)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval_sec)
            except TimeoutError:
                continue

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop(), name="BodyWatchdog")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            await self._task
            self._task = None
