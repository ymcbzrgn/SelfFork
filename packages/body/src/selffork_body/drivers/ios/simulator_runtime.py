"""iOS Simulator runtime via ``xcrun simctl`` (M5 — ADR-005 §M5-C3).

M5 default = simulator-first. Real-device path is gated behind an Apple
Developer Program enrollment and lives in M6 (see ADR-005 §Sınırlamalar).

Capabilities exposed:

* ``boot``: bring up a specific or 'first available' simulator device.
* ``screenshot``: capture booted simulator's frame as PNG bytes.
* ``biometric_match`` / ``biometric_no_match``: simulate Face ID / Touch ID
  (only available on simulator; real device biometric automation is gated
  by the system).
* ``app_install`` / ``app_launch`` / ``shutdown``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path

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
            await _run([
                "xcrun", "simctl", "io", target, "screenshot",
                "--type=png",
                str(output_path),
            ])
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
