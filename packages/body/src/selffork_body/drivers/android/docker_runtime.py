"""docker-android (budtmo) emulator container management (M5 — ADR-005 §M5-C2).

Lifecycle wrapper around ``docker run`` for the ``budtmo/docker-android``
emulator image. Spawns a container, waits for the Android boot to complete
via ``adb shell getprop sys.boot_completed``, and exposes ADB-reachable
ports back to the caller.

Production scenarios that require parallel emulators (multiple sessions on a
single host) currently rely on the ``budtmo`` pro/sponsor image; M5 default
ships single-pane container per host.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

__all__ = ["AndroidRuntimeError", "DockerAndroidRuntime"]

_log = logging.getLogger(__name__)


class AndroidRuntimeError(RuntimeError):
    """Raised when the docker-android container fails to come up."""


@dataclass
class DockerAndroidRuntime:
    """``budtmo/docker-android`` container manager.

    Attributes:
        android_version: e.g. ``"13.0"`` → image tag ``emulator_13.0``.
        device_type: ``EMULATOR_DEVICE`` env (e.g. ``"Samsung Galaxy S10"``).
        adb_host_port / vnc_host_port / web_port: published port mappings
            (defaults match docker-android's documented expectations).
    """

    android_version: str = "13.0"
    device_type: str = "Samsung Galaxy S10"
    adb_host_port: int = 5555
    vnc_host_port: int = 5900
    web_port: int = 6080
    appium_port: int = 4723
    container_name: str | None = None
    _container_id: str | None = None
    _started: bool = False

    @property
    def started(self) -> bool:
        return self._started

    @property
    def container_id(self) -> str | None:
        return self._container_id

    def _image_tag(self) -> str:
        # Image: budtmo/docker-android:emulator_<major>_<minor>
        return f"budtmo/docker-android:emulator_{self.android_version.replace('.', '_')}"

    def _docker_run_command(self) -> list[str]:
        cmd = [
            "docker",
            "run",
            "--privileged",
            "-d",
            "-e",
            f"EMULATOR_DEVICE={self.device_type}",
            "-e",
            "WEB_VNC=true",
            "-p",
            f"{self.appium_port}:4723",
            "-p",
            f"{self.web_port}:6080",
            "-p",
            f"{self.adb_host_port}:5555",
        ]
        if self.container_name:
            cmd += ["--name", self.container_name]
        cmd.append(self._image_tag())
        return cmd

    async def start(self) -> str:
        if self._started:
            return self._container_id  # type: ignore[return-value]
        cmd = self._docker_run_command()
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise AndroidRuntimeError(
                f"docker run failed (rc={proc.returncode}): {stderr.decode(errors='replace')}"
            )
        self._container_id = stdout.decode().strip()
        self._started = True
        _log.info("docker_android_started container=%s", self._container_id)
        return self._container_id

    async def wait_for_boot(self, timeout_sec: int = 180, poll_interval_sec: float = 2.0) -> None:
        if not self._started:
            raise AndroidRuntimeError("container not started")
        deadline = asyncio.get_running_loop().time() + timeout_sec
        while asyncio.get_running_loop().time() < deadline:
            ok = await self._adb_get_boot_completed()
            if ok:
                return
            await asyncio.sleep(poll_interval_sec)
        raise AndroidRuntimeError(f"emulator did not finish booting within {timeout_sec}s")

    async def _adb_get_boot_completed(self) -> bool:
        # Inside the docker-android container the emulator always exposes itself
        # as ``emulator-5554`` regardless of host-side port mapping (the host
        # port mapping is to ADB's *5555* TCP socket, not the emulator
        # console). Use ``docker exec`` so we ask ADB from inside the
        # container; this also avoids polluting the host's adb server with
        # stray ``emulator-NNNN`` serials.
        if self._container_id is None:
            return False
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "exec",
            self._container_id,
            "adb",
            "-s",
            "emulator-5554",
            "shell",
            "getprop",
            "sys.boot_completed",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode().strip() == "1"

    async def stop(self) -> None:
        if not self._started or self._container_id is None:
            return
        for action in ("kill", "rm"):
            proc = await asyncio.create_subprocess_exec(
                "docker",
                action,
                self._container_id,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.communicate()
        self._started = False
        self._container_id = None
