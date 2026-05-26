"""uiautomator2 + raw ADB fallback (M5 — ADR-005 §M5-C2, expanded S-ToolFleet Faz 1).

When the mobile-mcp server can't render a particular surface (canvas, game,
some webview pixel-perfect cases) the body driver falls back here for raw
screenshots and ADB shell access. uiautomator2 is the preferred path; pure
ADB subprocess works without the companion APK if uiautomator2 is missing.

S-ToolFleet Faz 1 expansion: every Android-only ADB / intent / dumpsys /
logcat / screenrecord / property / file-transfer operation lives here.
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
        self._screenrecord_proc: asyncio.subprocess.Process | None = None
        self._screenrecord_path: Path | None = None

    def _get_device(self) -> Any:
        if self._device is not None:
            return self._device
        try:
            import uiautomator2 as u2

            self._device = u2.connect(self.device_serial)
            return self._device
        except ImportError:
            return None

    def _adb_prefix(self) -> list[str]:
        cmd = ["adb"]
        if self.device_serial:
            cmd += ["-s", self.device_serial]
        return cmd

    async def _adb(self, *parts: str) -> str:
        cmd = [*self._adb_prefix(), *parts]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"adb {' '.join(parts)} failed (rc={proc.returncode}): "
                f"{stderr.decode(errors='replace')}"
            )
        return stdout.decode(errors="replace")

    async def screenshot(self) -> bytes:
        device = self._get_device()
        if device is not None:
            return await asyncio.to_thread(device.screenshot, format="raw")
        return await self._adb_screencap()

    async def _adb_screencap(self) -> bytes:
        cmd = [*self._adb_prefix(), "exec-out", "screencap", "-p"]
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
        return await self._adb("shell", command)

    async def install_apk(self, apk_path: Path) -> None:
        if not apk_path.exists():
            raise FileNotFoundError(apk_path)
        await self._adb("install", "-r", str(apk_path))

    async def install_multiple_apks(self, apk_paths: list[Path]) -> str:
        """Install a split-APK bundle via `adb install-multiple -r ...`."""
        for path in apk_paths:
            if not path.exists():
                raise FileNotFoundError(path)
        return await self._adb(
            "install-multiple", "-r", *(str(p) for p in apk_paths),
        )

    async def uninstall_app(self, package: str) -> None:
        await self._adb("uninstall", package)

    # ---- S-ToolFleet Faz 1 additions ---------------------------------

    async def list_devices(self) -> list[dict[str, str]]:
        """Parse ``adb devices -l`` into [{serial, state, model, transport_id}]."""
        proc = await asyncio.create_subprocess_exec(
            "adb", "devices", "-l",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return []
        text = stdout.decode(errors="replace")
        out: list[dict[str, str]] = []
        for line in text.splitlines():
            stripped = line.strip()
            if (
                not stripped
                or stripped.startswith("List of devices")
                or stripped.startswith("*")
            ):
                continue
            parts = stripped.split()
            if not parts:
                continue
            entry = {"serial": parts[0], "state": parts[1] if len(parts) > 1 else ""}
            for kv in parts[2:]:
                if ":" in kv:
                    k, v = kv.split(":", 1)
                    entry[k] = v
            out.append(entry)
        return out

    async def intent(
        self, action: str, *, extras: dict[str, str] | None = None,
        component: str | None = None, data: str | None = None,
    ) -> str:
        """Invoke ``adb shell am start -a <action> ...``."""
        parts = ["shell", "am", "start", "-a", action]
        if component is not None:
            parts += ["-n", component]
        if data is not None:
            parts += ["-d", data]
        for k, v in (extras or {}).items():
            parts += ["--es", k, v]
        return await self._adb(*parts)

    async def broadcast(
        self, action: str, *, extras: dict[str, str] | None = None,
    ) -> str:
        parts = ["shell", "am", "broadcast", "-a", action]
        for k, v in (extras or {}).items():
            parts += ["--es", k, v]
        return await self._adb(*parts)

    async def app_force_stop(self, package: str) -> str:
        return await self._adb("shell", "am", "force-stop", package)

    async def app_clear_data(self, package: str) -> str:
        return await self._adb("shell", "pm", "clear", package)

    async def list_packages(self) -> list[str]:
        text = await self._adb("shell", "pm", "list", "packages")
        return [
            line.removeprefix("package:").strip()
            for line in text.splitlines() if line.startswith("package:")
        ]

    async def deeplink(self, url: str) -> str:
        return await self._adb("shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url)

    async def dumpsys(self, service: str) -> str:
        return await self._adb("shell", "dumpsys", service)

    async def get_property(self, key: str) -> str:
        text = await self._adb("shell", "getprop", key)
        return text.strip()

    async def set_property(self, key: str, value: str) -> str:
        return await self._adb("shell", "setprop", key, value)

    async def logcat(
        self,
        *,
        tag_filter: str | None = None,
        max_lines: int = 200,
        clear: bool = False,
    ) -> str:
        if clear:
            await self._adb("logcat", "-c")
        cmd = [*self._adb_prefix(), "logcat", "-d", "-T", str(max_lines)]
        if tag_filter:
            cmd += [tag_filter, "*:S"]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode(errors="replace")

    async def push(self, local: Path, remote: str) -> str:
        return await self._adb("push", str(local), remote)

    async def pull(self, remote: str, local: Path) -> str:
        return await self._adb("pull", remote, str(local))

    async def get_battery(self) -> dict[str, str]:
        text = await self.dumpsys("battery")
        out: dict[str, str] = {}
        for line in text.splitlines():
            line = line.strip()
            if ":" in line:
                k, _, v = line.partition(":")
                out[k.strip()] = v.strip()
        return out

    async def reboot(self) -> None:
        await self._adb("reboot")

    async def set_geolocation(self, latitude: float, longitude: float) -> str:
        # Requires emulator console — many physical devices reject. Best-effort.
        return await self._adb("emu", "geo", "fix", str(longitude), str(latitude))

    async def screenrecord_start(self, output_path: Path) -> None:
        if self._screenrecord_proc is not None:
            raise RuntimeError("screenrecord already in progress")
        cmd = [
            *self._adb_prefix(),
            "shell", "screenrecord", "--bit-rate", "4000000",
            f"/sdcard/{output_path.name}",
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._screenrecord_proc = proc
        self._screenrecord_path = output_path

    async def screenrecord_stop(self) -> Path | None:
        if self._screenrecord_proc is None:
            return None
        proc = self._screenrecord_proc
        path = self._screenrecord_path
        self._screenrecord_proc = None
        self._screenrecord_path = None
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except TimeoutError:
            proc.kill()
            await proc.wait()
        # Pull to host
        if path is not None:
            await self._adb("pull", f"/sdcard/{path.name}", str(path))
            await self._adb("shell", "rm", f"/sdcard/{path.name}")
        return path
