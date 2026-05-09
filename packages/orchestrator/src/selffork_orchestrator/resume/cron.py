"""macOS launchd scheduler for ScheduledResume wake-events.

Why launchd, not cron(8): macOS deprecated cron(8); launchd
``StartCalendarInterval`` jobs run when the laptop **comes out of sleep**,
while cron jobs miss them. SelfFork's quota-reset semantics need that:
a missed 5h reset means waiting another 5h.

We generate a per-session plist at
``~/Library/LaunchAgents/com.selffork.<session_id>.plist`` and load it
via ``launchctl load -w <path>``. When the resume completes (or the
operator cancels), :meth:`LaunchdScheduler.uninstall` calls
``launchctl unload`` and removes the plist file.

Linux/Windows scheduling is a follow-up patch within Order 3 (systemd
user timer for Linux; Windows is M5+ scope).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from selffork_orchestrator.resume.store import ScheduledResume

__all__ = [
    "LaunchdScheduler",
    "LaunchdSchedulerError",
    "default_launch_agents_dir",
    "is_macos",
]


def default_launch_agents_dir() -> Path:
    """``~/Library/LaunchAgents`` — the canonical user agent dir on macOS."""
    return Path.home() / "Library" / "LaunchAgents"


def is_macos() -> bool:
    """True when running on Darwin. Use for early-bail on Linux/Windows."""
    return sys.platform == "darwin"


class LaunchdSchedulerError(RuntimeError):
    """Raised when ``launchctl load/unload`` fails or no executable is set."""


@dataclass(frozen=True, slots=True)
class LaunchdScheduler:
    """Generate + manage launchd plists for ScheduledResume wake events.

    Args:
        launch_agents_dir: Override; defaults to ``~/Library/LaunchAgents``.
        selffork_executable: Absolute path to the ``selffork`` CLI.
            ``None`` resolves via ``shutil.which("selffork")`` at call time.
        label_prefix: launchd labels are reverse-DNS; default ``com.selffork``.
    """

    launch_agents_dir: Path | None = None
    selffork_executable: str | None = None
    label_prefix: str = "com.selffork"

    # ── Public path helpers ──────────────────────────────────────────────

    def label_for(self, session_id: str) -> str:
        """Sanitize ``session_id`` into a valid launchd label suffix."""
        sanitized = session_id.replace(".", "-").replace("/", "-")
        return f"{self.label_prefix}.{sanitized}"

    def plist_path(self, session_id: str) -> Path:
        """Filesystem path of the plist that would be installed for this session."""
        return self._dir() / f"{self.label_for(session_id)}.plist"

    # ── Render + install/uninstall ───────────────────────────────────────

    def render(self, record: ScheduledResume) -> str:
        """Return the plist XML for ``record``.

        ``StartCalendarInterval`` is interpreted in **system local time** by
        launchd; we convert ``record.resume_at`` (UTC, by ScheduledResume
        invariants) to local first.
        """
        executable = self._executable()
        label = self.label_for(record.session_id)
        local = record.resume_at.astimezone()
        return _PLIST_TEMPLATE.format(
            label=xml_escape(label),
            program=xml_escape(executable),
            session_id=xml_escape(record.session_id),
            minute=local.minute,
            hour=local.hour,
            day=local.day,
            month=local.month,
        )

    def install(self, record: ScheduledResume) -> Path:
        """Write the plist + ``launchctl load -w`` it.

        Returns:
            The plist filesystem path.

        Raises:
            LaunchdSchedulerError: when ``launchctl load`` exits non-zero or
                the selffork executable cannot be resolved.
        """
        path = self.plist_path(record.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render(record), encoding="utf-8")
        result = subprocess.run(  # noqa: S603 — args SelfFork-controlled
            ["launchctl", "load", "-w", str(path)],  # noqa: S607
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # Plist written but load failed; leave the plist so the operator
            # can inspect it. They can `launchctl load` manually after fix.
            raise LaunchdSchedulerError(
                f"launchctl load failed: {(result.stderr or result.stdout).strip()}",
            )
        return path

    def uninstall(self, session_id: str) -> bool:
        """``launchctl unload -w`` then delete the plist.

        Returns:
            True when a plist existed (and was removed); False when no plist
            was installed for ``session_id``.

        Unload errors are swallowed deliberately — even if launchctl complains
        (job already exited, plist not in launchd's table, etc.), removing
        the plist file is the goal of this call.
        """
        path = self.plist_path(session_id)
        if not path.exists():
            return False
        subprocess.run(  # noqa: S603 — args SelfFork-controlled
            ["launchctl", "unload", "-w", str(path)],  # noqa: S607
            check=False,
            capture_output=True,
            text=True,
        )
        path.unlink(missing_ok=True)
        return True

    # ── Internals ────────────────────────────────────────────────────────

    def _dir(self) -> Path:
        return self.launch_agents_dir or default_launch_agents_dir()

    def _executable(self) -> str:
        if self.selffork_executable:
            return self.selffork_executable
        found = shutil.which("selffork")
        if found is not None:
            return found
        raise LaunchdSchedulerError(
            "selffork executable not found on PATH; "
            "pass selffork_executable=... when constructing LaunchdScheduler.",
        )


_PLIST_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{program}</string>
    <string>resume</string>
    <string>now</string>
    <string>{session_id}</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Minute</key>
    <integer>{minute}</integer>
    <key>Hour</key>
    <integer>{hour}</integer>
    <key>Day</key>
    <integer>{day}</integer>
    <key>Month</key>
    <integer>{month}</integer>
  </dict>
  <key>RunAtLoad</key>
  <false/>
  <key>StandardOutPath</key>
  <string>/tmp/{label}.out</string>
  <key>StandardErrorPath</key>
  <string>/tmp/{label}.err</string>
</dict>
</plist>
"""
