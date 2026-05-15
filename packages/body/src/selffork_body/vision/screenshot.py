"""Cross-platform screenshot capture (M5 — ADR-005 §M5-B).

Each driver supplies its native capture path; this module exposes the
:class:`ScreenshotCapture` Protocol + factory dispatch. Implementations are
side-effect-only adapters around platform tooling (``screencapture`` on
macOS, ``grim``/``scrot`` on Linux, ``xcrun simctl`` on iOS sim, ``adb`` on
Android, Playwright on web).

Returns raw PNG bytes. Persistence is the caller's responsibility (see
:class:`selffork_body.storage.ScreenshotStore`).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
import tempfile
from pathlib import Path
from typing import Literal, Protocol

__all__ = [
    "AndroidScreenshotCapture",
    "DriverKind",
    "IosSimulatorScreenshotCapture",
    "LinuxScreenshotCapture",
    "MacOSScreenshotCapture",
    "ScreenshotCapture",
    "get_screenshot_capture",
]


DriverKind = Literal["macos", "linux", "windows", "ios_sim", "android", "web"]


class ScreenshotCapture(Protocol):
    """Capture a screenshot, return PNG bytes.

    ``rect`` is ``(x, y, w, h)`` in screen coordinates; backends that don't
    support cropping ignore the parameter and return the full frame.
    """

    async def capture(self, rect: tuple[int, int, int, int] | None = None) -> bytes:
        ...


class _SubprocessCaptureBase:
    """Shared scaffolding for capture backends that shell out to a binary."""

    async def _run_to_tempfile(self, cmd: list[str]) -> bytes:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            path = Path(tmp.name)
        cmd_with_path = [*cmd, str(path)]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd_with_path,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(
                    f"capture command failed (rc={proc.returncode}): {stderr.decode(errors='replace')}"
                )
            return path.read_bytes()
        finally:
            with contextlib.suppress(FileNotFoundError):
                path.unlink()


class MacOSScreenshotCapture(_SubprocessCaptureBase):
    """``screencapture -x -t png [-R rect] <path>`` wrapper."""

    async def capture(self, rect: tuple[int, int, int, int] | None = None) -> bytes:
        cmd = ["screencapture", "-x", "-t", "png"]
        if rect is not None:
            cmd += ["-R", f"{rect[0]},{rect[1]},{rect[2]},{rect[3]}"]
        return await self._run_to_tempfile(cmd)


class LinuxScreenshotCapture(_SubprocessCaptureBase):
    """``grim`` (Wayland) → ``scrot`` (X11) fallback."""

    async def capture(self, rect: tuple[int, int, int, int] | None = None) -> bytes:
        wayland = bool(os.environ.get("WAYLAND_DISPLAY"))
        if wayland:
            cmd = ["grim"]
            if rect is not None:
                cmd += ["-g", f"{rect[0]},{rect[1]} {rect[2]}x{rect[3]}"]
            return await self._run_to_tempfile(cmd)
        # X11 fallback
        cmd = ["scrot"]
        if rect is not None:
            cmd += ["-a", f"{rect[0]},{rect[1]},{rect[2]},{rect[3]}"]
        return await self._run_to_tempfile(cmd)


class IosSimulatorScreenshotCapture(_SubprocessCaptureBase):
    """``xcrun simctl io booted screenshot`` wrapper."""

    async def capture(self, rect: tuple[int, int, int, int] | None = None) -> bytes:
        cmd = ["xcrun", "simctl", "io", "booted", "screenshot", "--type=png"]
        if rect is not None:
            # simctl doesn't support cropping; caller must crop downstream.
            pass
        return await self._run_to_tempfile(cmd)


class AndroidScreenshotCapture:
    """uiautomator2-backed capture (Python wrapper around ADB ``screencap``).

    Falls back to ``adb shell screencap -p`` subprocess when uiautomator2 is
    unavailable in the runtime environment.
    """

    def __init__(self, device_serial: str | None = None) -> None:
        self.device_serial = device_serial
        self._device = None

    def _get_device(self):  # type: ignore[no-untyped-def]
        if self._device is not None:
            return self._device
        try:  # pragma: no cover - import guard
            import uiautomator2 as u2

            self._device = u2.connect(self.device_serial)
            return self._device
        except ImportError:
            return None

    async def capture(self, rect: tuple[int, int, int, int] | None = None) -> bytes:
        device = self._get_device()
        if device is not None:
            return await asyncio.to_thread(device.screenshot, format="raw")
        # Fallback: adb shell screencap -p
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


def get_screenshot_capture(driver: DriverKind) -> ScreenshotCapture:
    """Factory dispatch by driver kind."""
    if driver == "macos":
        return MacOSScreenshotCapture()
    if driver == "linux":
        return LinuxScreenshotCapture()
    if driver == "ios_sim":
        return IosSimulatorScreenshotCapture()
    if driver == "android":
        return AndroidScreenshotCapture()
    if driver == "web":
        raise NotImplementedError(
            "web driver supplies its own Playwright-backed capture; use PlaywrightWebDriver.screenshot()"
        )
    if driver == "windows":
        raise NotImplementedError("Windows desktop driver lands in M6")
    raise ValueError(f"unknown driver kind: {driver!r}")


def detect_driver() -> DriverKind:
    """Best-effort driver detection from ``sys.platform``. Used for M5 dev smoke."""
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "win32":
        return "windows"
    return "linux"  # conservative default
