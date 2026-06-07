"""iOS Simulator runtime via ``xcrun simctl`` (M5 — ADR-005 §M5-C3, expanded S-ToolFleet Faz 1).

M5 default = simulator-first. Real-device path is gated behind an Apple
Developer Program enrollment and lives in M6 (see ADR-005 §Sınırlamalar).

Capabilities exposed:

* ``boot``: bring up a specific or 'first available' simulator device.
* ``screenshot``: capture booted simulator's frame as PNG bytes.
* ``biometric_match`` / ``biometric_no_match``: simulate Face ID / Touch ID
  (only available on simulator; real device biometric automation is gated
  by the system).
* ``app_install`` / ``app_launch`` / ``shutdown``.

S-ToolFleet Faz 1 additions: list / erase / shutdown specific /
list_apps / get_logs / send_notification / record video /
status_bar override / appearance / open_url / set_clipboard /
get_clipboard / set_geolocation.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path
from typing import Any

__all__ = ["IosSimulatorError", "IosSimulatorRuntime"]

_log = logging.getLogger(__name__)


class IosSimulatorError(RuntimeError):
    pass


async def _run(cmd: list[str]) -> tuple[bytes, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise IosSimulatorError(
            f"command failed (rc={proc.returncode}): {' '.join(cmd)} :: {stderr.decode(errors='replace')}"
        )
    return stdout, stderr.decode(errors="replace")


class IosSimulatorRuntime:
    def __init__(self, *, device_id: str | None = None, ios_version: str = "17.2") -> None:
        self.device_id = device_id
        self.ios_version = ios_version
        self._booted_id: str | None = None
        # Track active recording task so record_stop has a handle.
        self._recording_proc: asyncio.subprocess.Process | None = None
        self._recording_path: Path | None = None

    @property
    def booted_id(self) -> str | None:
        return self._booted_id

    async def boot(self) -> str:
        target = self.device_id or "booted"
        if target == "booted":
            # If already booted, reuse; else pick the first Shutdown device.
            stdout, _ = await _run(["xcrun", "simctl", "list", "devices", "available"])
            text = stdout.decode()
            booted = self._first_with_state(text, "Booted")
            if booted is not None:
                self._booted_id = booted
                return booted
            shutdown = self._first_with_state(text, "Shutdown")
            if shutdown is None:
                raise IosSimulatorError("no available iOS simulator devices found")
            target = shutdown
        await _run(["xcrun", "simctl", "boot", target])
        await _run(["xcrun", "simctl", "bootstatus", target, "-b"])
        self._booted_id = target
        return target

    @staticmethod
    def _first_with_state(text: str, state: str) -> str | None:
        # Lines look like:  iPhone 17 Pro (12345-...-67890) (Shutdown)
        for line in text.splitlines():
            if f"({state})" in line and "(" in line and ")" in line:
                # Extract the UDID surrounded by the first set of parens
                first_open = line.find("(")
                first_close = line.find(")", first_open)
                if first_open == -1 or first_close == -1:
                    continue
                candidate = line[first_open + 1 : first_close].strip()
                # UDID is 36 chars — basic shape check (not strict UUID parse)
                if len(candidate) == 36 and candidate.count("-") == 4:
                    return candidate
        return None

    async def screenshot(self, *, output_path: Path | None = None) -> bytes:
        target = self._booted_id or "booted"
        if output_path is None:
            import tempfile

            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.close()
            output_path = Path(tmp.name)
        try:
            await _run(
                [
                    "xcrun",
                    "simctl",
                    "io",
                    target,
                    "screenshot",
                    "--type=png",
                    str(output_path),
                ]
            )
            return output_path.read_bytes()
        finally:
            with contextlib.suppress(FileNotFoundError):
                output_path.unlink()

    async def biometric_match(self) -> None:
        target = self._booted_id or "booted"
        await _run(["xcrun", "simctl", "ui", target, "biometric_match", "enrolled"])

    async def biometric_no_match(self) -> None:
        target = self._booted_id or "booted"
        await _run(["xcrun", "simctl", "ui", target, "biometric_no_match"])

    async def app_install(self, app_bundle: Path) -> None:
        target = self._booted_id or "booted"
        await _run(["xcrun", "simctl", "install", target, str(app_bundle)])

    async def app_launch(self, bundle_id: str) -> None:
        target = self._booted_id or "booted"
        await _run(["xcrun", "simctl", "launch", target, bundle_id])

    async def shutdown(self) -> None:
        if self._booted_id is None:
            return
        await _run(["xcrun", "simctl", "shutdown", self._booted_id])
        self._booted_id = None

    # ---- S-ToolFleet Faz 1 additions ----------------------------------

    async def list_devices(self) -> list[dict[str, str]]:
        """Return [{name, udid, state, runtime}] for every simulator."""
        import json

        stdout, _ = await _run(["xcrun", "simctl", "list", "devices", "--json"])
        data = json.loads(stdout)
        out: list[dict[str, str]] = []
        for runtime, items in data.get("devices", {}).items():
            for entry in items:
                out.append(
                    {
                        "name": entry.get("name", ""),
                        "udid": entry.get("udid", ""),
                        "state": entry.get("state", ""),
                        "runtime": runtime,
                    }
                )
        return out

    async def boot_specific(self, udid: str) -> str:
        await _run(["xcrun", "simctl", "boot", udid])
        await _run(["xcrun", "simctl", "bootstatus", udid, "-b"])
        self._booted_id = udid
        return udid

    async def shutdown_specific(self, udid: str) -> None:
        await _run(["xcrun", "simctl", "shutdown", udid])
        if self._booted_id == udid:
            self._booted_id = None

    async def erase_specific(self, udid: str) -> None:
        await _run(["xcrun", "simctl", "erase", udid])

    async def list_installed_apps(self, udid: str | None = None) -> dict[str, Any]:
        target = udid or self._booted_id or "booted"
        stdout, _ = await _run(["xcrun", "simctl", "listapps", target])
        return {"raw": stdout.decode(errors="replace")}

    async def app_terminate(self, bundle_id: str, udid: str | None = None) -> None:
        target = udid or self._booted_id or "booted"
        await _run(["xcrun", "simctl", "terminate", target, bundle_id])

    async def app_uninstall(self, bundle_id: str, udid: str | None = None) -> None:
        target = udid or self._booted_id or "booted"
        await _run(["xcrun", "simctl", "uninstall", target, bundle_id])

    async def open_url(self, url: str, udid: str | None = None) -> None:
        target = udid or self._booted_id or "booted"
        await _run(["xcrun", "simctl", "openurl", target, url])

    async def set_clipboard(self, text: str, udid: str | None = None) -> None:
        target = udid or self._booted_id or "booted"
        proc = await asyncio.create_subprocess_exec(
            "xcrun",
            "simctl",
            "pbcopy",
            target,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate(text.encode())
        if proc.returncode != 0:
            raise IosSimulatorError(
                f"pbcopy failed (rc={proc.returncode}): {stderr.decode(errors='replace')}"
            )

    async def get_clipboard(self, udid: str | None = None) -> str:
        target = udid or self._booted_id or "booted"
        stdout, _ = await _run(["xcrun", "simctl", "pbpaste", target])
        return stdout.decode(errors="replace")

    async def set_geolocation(
        self,
        latitude: float,
        longitude: float,
        udid: str | None = None,
    ) -> None:
        target = udid or self._booted_id or "booted"
        await _run(
            [
                "xcrun",
                "simctl",
                "location",
                target,
                "set",
                f"{latitude},{longitude}",
            ]
        )

    async def clear_geolocation(self, udid: str | None = None) -> None:
        target = udid or self._booted_id or "booted"
        await _run(["xcrun", "simctl", "location", target, "clear"])

    async def status_bar_override(
        self,
        time: str | None = None,
        battery_state: str | None = None,
        cellular_bars: int | None = None,
        wifi_bars: int | None = None,
        udid: str | None = None,
    ) -> None:
        target = udid or self._booted_id or "booted"
        cmd = ["xcrun", "simctl", "status_bar", target, "override"]
        if time is not None:
            cmd += ["--time", time]
        if battery_state is not None:
            cmd += ["--batteryState", battery_state]
        if cellular_bars is not None:
            cmd += ["--cellularBars", str(cellular_bars)]
        if wifi_bars is not None:
            cmd += ["--wifiBars", str(wifi_bars)]
        await _run(cmd)

    async def set_appearance(
        self,
        appearance: str,
        udid: str | None = None,
    ) -> None:
        if appearance not in ("light", "dark"):
            raise IosSimulatorError(
                f"appearance must be 'light' or 'dark', got {appearance!r}",
            )
        target = udid or self._booted_id or "booted"
        await _run(["xcrun", "simctl", "ui", target, "appearance", appearance])

    async def push_notification(
        self, payload_path: Path, bundle_id: str, udid: str | None = None
    ) -> None:
        target = udid or self._booted_id or "booted"
        await _run(
            [
                "xcrun",
                "simctl",
                "push",
                target,
                bundle_id,
                str(payload_path),
            ]
        )

    async def get_logs(
        self,
        *,
        predicate: str | None = None,
        last: str | None = None,
        udid: str | None = None,
    ) -> str:
        target = udid or self._booted_id or "booted"
        cmd = ["xcrun", "simctl", "spawn", target, "log", "show", "--style", "compact"]
        if last is not None:
            cmd += ["--last", last]
        if predicate is not None:
            cmd += ["--predicate", predicate]
        stdout, _ = await _run(cmd)
        return stdout.decode(errors="replace")

    async def record_video_start(self, output_path: Path) -> None:
        if self._recording_proc is not None:
            raise IosSimulatorError("recording already in progress")
        target = self._booted_id or "booted"
        # ``simctl io ... recordVideo`` runs until SIGINT; spawn in background.
        proc = await asyncio.create_subprocess_exec(
            "xcrun",
            "simctl",
            "io",
            target,
            "recordVideo",
            str(output_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._recording_proc = proc
        self._recording_path = output_path

    async def record_video_stop(self) -> Path | None:
        if self._recording_proc is None:
            return None
        proc = self._recording_proc
        path = self._recording_path
        self._recording_proc = None
        self._recording_path = None
        proc.terminate()
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        return path
