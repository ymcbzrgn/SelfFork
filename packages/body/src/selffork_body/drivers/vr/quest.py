"""Quest 3 driver — Android-derived VR/AR (S-ToolFleet Faz 4).

Quest 3's runtime is Android Open Source Project based; ADB works either
over USB or WiFi (via MQDH — Meta Quest Developer Hub). The driver
inherits from :class:`AndroidDriver` so every ``android_*`` operation
(click/swipe/screenshot/install/etc.) works transparently. New
VR-specific methods cover recenter, passthrough, controller buttons,
combined battery, boundary status, device info, and a Meta button press.

Operator env: ``SELFFORK_BODY_QUEST_DEVICE`` = ADB device serial
(USB shows up as a serial; WiFi via ``adb tcpip 5555`` + ``adb connect
<headset-ip>:5555`` per Meta's developer docs).
"""

from __future__ import annotations

import json
from typing import Any, Literal

from selffork_body.drivers.android import AndroidDriver

__all__ = ["QuestDriver"]


_META_RECENTER_INTENT = "com.oculus.vrshell.intent.action.RECENTER"
_META_PASSTHROUGH_TOGGLE = "com.oculus.experience.PASSTHROUGH_TOGGLE"


class QuestDriver(AndroidDriver):
    """Meta Quest 3 driver — Android base + VR-specific extensions."""

    platform: str = "quest"

    def __init__(
        self,
        *,
        device_serial: str | None = None,
        runtime: Literal["docker", "physical"] = "physical",
    ) -> None:
        # Quest is never a docker-android target; force physical / WiFi-ADB.
        super().__init__(runtime=runtime, device_serial=device_serial)

    # ---- Quest-specific VR actions ----------------------------------

    async def recenter(self) -> str:
        """Recenter the headset view (Meta intent broadcast)."""
        return await self.fallback.intent(_META_RECENTER_INTENT)

    async def passthrough_enable(self) -> str:
        """Toggle Quest passthrough ON. Meta-specific intent."""
        return await self.fallback.broadcast(
            _META_PASSTHROUGH_TOGGLE,
            extras={"state": "on"},
        )

    async def passthrough_disable(self) -> str:
        return await self.fallback.broadcast(
            _META_PASSTHROUGH_TOGGLE,
            extras={"state": "off"},
        )

    async def press_meta_button(self) -> str:
        """Simulate the Meta/Oculus home button press."""
        return await self.fallback.adb_shell(
            "input keyevent KEYCODE_BUTTON_MODE",
        )

    async def press_controller_button(
        self,
        controller: Literal["left", "right"],
        button: Literal["a", "b", "x", "y", "grip", "trigger", "thumbstick"],
    ) -> str:
        """Press a controller button via Android input subsystem.

        Quest's input service maps controller buttons to standard Android
        gamepad keycodes; we route through ``input keyevent`` which is
        the supported public API on Quest's Android variant.
        """
        keycode_map = {
            "a": "KEYCODE_BUTTON_A",
            "b": "KEYCODE_BUTTON_B",
            "x": "KEYCODE_BUTTON_X",
            "y": "KEYCODE_BUTTON_Y",
            "grip": "KEYCODE_BUTTON_R2" if controller == "right" else "KEYCODE_BUTTON_L2",
            "trigger": "KEYCODE_BUTTON_R1" if controller == "right" else "KEYCODE_BUTTON_L1",
            "thumbstick": "KEYCODE_BUTTON_THUMBR"
            if controller == "right"
            else "KEYCODE_BUTTON_THUMBL",
        }
        keycode = keycode_map[button]
        return await self.fallback.adb_shell(f"input keyevent {keycode}")

    async def get_combined_battery(self) -> dict[str, Any]:
        """Headset + controller batteries via dumpsys."""
        headset = await self.fallback.dumpsys("battery")
        # Quest exposes controller batteries via the OVRRuntime service when
        # present; fall back to a single-headset reading otherwise.
        controllers: dict[str, str] = {}
        try:
            text = await self.fallback.dumpsys("OVRRuntime")
            for line in text.splitlines():
                line = line.strip()
                if "controller" in line.lower() and "battery" in line.lower():
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        controllers[parts[0].strip()] = parts[1].strip()
        except Exception:
            controllers = {}
        # Extract level from headset dumpsys
        level = "?"
        for line in headset.splitlines():
            if "level:" in line:
                level = line.split(":", 1)[1].strip()
                break
        return {"headset_level": level, "controllers": controllers, "raw": headset[:2048]}

    async def get_device_info(self) -> dict[str, str]:
        """Read model / OS / runtime version via getprop."""
        info: dict[str, str] = {}
        for key in (
            "ro.product.model",
            "ro.product.manufacturer",
            "ro.build.version.release",
            "ro.build.version.sdk",
            "ro.oculus.os.version",
        ):
            info[key] = await self.fallback.get_property(key)
        return info

    async def get_boundary_status(self) -> dict[str, str]:
        """Guardian / Roomscale boundary status via dumpsys."""
        text = ""
        try:
            text = await self.fallback.dumpsys("OVRGuardian")
        except Exception:
            text = ""
        active = "active" in text.lower() or "enabled" in text.lower()
        return {"raw": text[:4096], "guardian_active": str(active)}

    async def record_video(self, output_path: str, time_limit_sec: int = 60) -> str:
        """Start an on-device screenrecord; returns the device path."""
        # Quest screenrecord is the standard Android variant.
        device_path = f"/sdcard/{output_path.split('/')[-1]}"
        return await self.fallback.adb_shell(
            f"screenrecord --time-limit {time_limit_sec} {device_path}",
        )

    async def stop_record_video(self) -> str:
        """Send SIGINT to the active screenrecord process."""
        return await self.fallback.adb_shell(
            "killall -SIGINT screenrecord || true",
        )

    async def voice_command(self, text: str) -> str:
        """Inject a voice command via Android assistant action (best-effort)."""
        # Quest's voice service listens on a Meta intent; best-effort dispatch.
        # Operator must have voice enabled in headset settings.
        return await self.fallback.intent(
            "android.intent.action.VOICE_COMMAND",
            extras={"query": text},
        )

    async def list_installed_vr_apps(self) -> list[dict[str, str]]:
        """List installed apps with Meta/Quest VR manifest signature."""
        text = await self.fallback.adb_shell(
            "pm list packages -3",  # -3 = third-party only
        )
        out: list[dict[str, str]] = []
        for line in text.splitlines():
            if line.startswith("package:"):
                pkg = line.removeprefix("package:").strip()
                # VR-app heuristic: typical Quest apps contain "oculus", "meta", or "vr"
                is_vr = any(marker in pkg.lower() for marker in ("oculus", "meta", "vr", "quest"))
                out.append({"package": pkg, "is_vr_heuristic": str(is_vr)})
        return out

    async def device_summary(self) -> str:
        """One-shot summary of device + battery + runtime — useful for handoffs."""
        info = await self.get_device_info()
        battery = await self.get_combined_battery()
        return json.dumps(
            {
                "info": info,
                "headset_level": battery["headset_level"],
                "controllers": battery["controllers"],
            },
            indent=2,
        )
