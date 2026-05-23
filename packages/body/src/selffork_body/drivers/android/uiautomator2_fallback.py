"""uiautomator2 + raw ADB fallback (M5 — ADR-005 §M5-C2).

When the mobile-mcp server can't render a particular surface (canvas, game,
some webview pixel-perfect cases) the body driver falls back here for raw
screenshots and ADB shell access. uiautomator2 is the preferred path; pure
ADB subprocess works without the companion APK if uiautomator2 is missing.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

__all__ = ["UiAutomator2Fallback"]

_log = logging.getLogger(__name__)


class UiAutomator2Fallback:
    """Pixel-perfect screenshot + low-level ADB shell."""

    def __init__(self, device_serial: str | None = None) -> None:
        self.device_serial = device_serial
        # Lazy-imported uiautomator2 device handle. Typed ``Any`` so
        # mypy doesn't narrow ``None`` and flag the warm-cache branch
        # as unreachable.
        self._device: Any = None

    def _get_device(self) -> Any:
        if self._device is not None:
            return self._device
        try:
            import uiautomator2 as u2

            self._device = u2.connect(self.device_serial)
            return self._device
        except ImportError:
            return None

    async def screenshot(self) -> bytes:
        device = self._get_device()
        if device is not None:
            return await asyncio.to_thread(device.screenshot, format="raw")
        return await self._adb_screencap()

    async def _adb_screencap(self) -> bytes:
        cmd = ["adb"]
        if self.device_serial:
            cmd += ["-s", self.device_serial]
        cmd += ["exec-out", "screencap", "-p"]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"adb screencap failed (rc={proc.returncode}): {stderr.decode(errors='replace')}"
            )
        return stdout

    async def adb_shell(self, command: str) -> str:
        cmd = ["adb"]
        if self.device_serial:
            cmd += ["-s", self.device_serial]
        cmd += ["shell", command]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"adb shell failed (rc={proc.returncode}): {stderr.decode(errors='replace')}"
            )
        return stdout.decode()

    async def install_apk(self, apk_path: Path) -> None:
        if not apk_path.exists():
            raise FileNotFoundError(apk_path)
        cmd = ["adb"]
        if self.device_serial:
            cmd += ["-s", self.device_serial]
        cmd += ["install", "-r", str(apk_path)]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"adb install failed (rc={proc.returncode}): {stderr.decode(errors='replace')}"
            )
