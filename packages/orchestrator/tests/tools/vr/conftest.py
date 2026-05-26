"""Shared stubs + fixtures for Faz 4 VR tests."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from selffork_body.sandbox import PermissionWarden, WardenMode
from selffork_orchestrator.tools.base import ToolContext


class _StubProjectStore:
    pass


@dataclass
class StubQuestDriver:
    """Duck-typed Quest driver stub (Android base + VR extensions)."""

    platform: str = "quest"
    calls: list[tuple[str, tuple, dict]] = field(default_factory=list)

    def _record(self, name: str, args: tuple, kwargs: dict) -> None:
        self.calls.append((name, args, dict(kwargs)))

    # ---- Inherited Android surface ------------------------------------

    async def start(self) -> None: self._record("start", (), {})
    async def stop(self) -> None: self._record("stop", (), {})

    async def app_launch(self, package):
        self._record("app_launch", (package,), {})

    async def app_terminate(self, package):
        self._record("app_terminate", (package,), {})

    async def list_apps(self):
        self._record("list_apps", (), {})
        return [{"package": "com.oculus.shellenv"}]

    async def install_app(self, apk_path):
        self._record("install_app", (apk_path,), {})

    async def uninstall_app(self, package):
        self._record("uninstall_app", (package,), {})

    async def screenshot(self, rect=None):
        self._record("screenshot", (), {"rect": rect})
        return b"\x89PNG\r\n\x1a\nQUEST"

    async def logcat(self, *, tag_filter=None, max_lines=200, clear=False):
        self._record("logcat", (), {
            "tag_filter": tag_filter, "max_lines": max_lines, "clear": clear,
        })
        return "QUEST_LOG\n"

    # ---- VR-specific extensions ---------------------------------------

    async def recenter(self):
        self._record("recenter", (), {})
        return "RECENTERED"

    async def passthrough_enable(self):
        self._record("passthrough_enable", (), {})
        return "ON"

    async def passthrough_disable(self):
        self._record("passthrough_disable", (), {})
        return "OFF"

    async def press_meta_button(self):
        self._record("press_meta_button", (), {})
        return ""

    async def press_controller_button(self, controller, button):
        self._record("press_controller_button", (controller, button), {})
        return ""

    async def get_combined_battery(self):
        self._record("get_combined_battery", (), {})
        return {"headset_level": "85", "controllers": {}, "raw": "..."}

    async def get_device_info(self):
        self._record("get_device_info", (), {})
        return {
            "ro.product.model": "Quest 3",
            "ro.product.manufacturer": "Oculus",
            "ro.oculus.os.version": "v62.0",
            "ro.build.version.release": "10",
            "ro.build.version.sdk": "29",
        }

    async def get_boundary_status(self):
        self._record("get_boundary_status", (), {})
        return {"guardian_active": "True", "raw": "..."}

    async def record_video(self, output_path, time_limit_sec=60):
        self._record("record_video", (output_path,), {"time_limit_sec": time_limit_sec})
        return ""

    async def stop_record_video(self):
        self._record("stop_record_video", (), {})
        return ""

    async def voice_command(self, text):
        self._record("voice_command", (text,), {})
        return ""

    async def list_installed_vr_apps(self):
        self._record("list_installed_vr_apps", (), {})
        return [{"package": "com.oculus.firstcontact", "is_vr_heuristic": "True"}]


@dataclass
class StubVisionProDriver:
    platform: str = "visionpro"
    calls: list[tuple[str, tuple, dict]] = field(default_factory=list)

    def _record(self, name: str, args: tuple, kwargs: dict) -> None:
        self.calls.append((name, args, dict(kwargs)))

    async def start(self) -> None: self._record("start", (), {})
    async def stop(self) -> None: self._record("stop", (), {})

    async def simulator_list(self):
        self._record("simulator_list", (), {})
        return [{
            "name": "Apple Vision Pro",
            "udid": "A" * 36,
            "state": "Shutdown",
            "runtime": "visionOS 1.0",
        }]

    async def simulator_boot(self, udid):
        self._record("simulator_boot", (udid,), {})
        return udid

    async def simulator_shutdown(self, udid):
        self._record("simulator_shutdown", (udid,), {})

    async def screenshot(self, rect=None):
        self._record("screenshot", (), {"rect": rect})
        return b"\x89PNG\r\n\x1a\nVPSIM"

    async def app_launch(self, bundle_id):
        self._record("app_launch", (bundle_id,), {})

    async def get_logs(self, *, predicate=None, last="1m", udid=None):
        self._record("get_logs", (), {"predicate": predicate, "last": last, "udid": udid})
        return "VP_LOG"

    async def click_at(self, x, y):
        self._record("click_at", (x, y), {})


def make_ctx(
    *, driver=None, vision_runtime=None, session_id="sess-test",
    project_slug=None,
) -> ToolContext:
    warden = PermissionWarden(mode=WardenMode.DANGER_FULL_ACCESS)
    return ToolContext(
        session_id=session_id,
        project_slug=project_slug,
        project_store=_StubProjectStore(),
        body_driver=driver,
        permission_warden=warden,
        vision_runtime=vision_runtime,
    )


@pytest.fixture
def stub_quest_driver() -> StubQuestDriver:
    return StubQuestDriver()


@pytest.fixture
def stub_visionpro_driver() -> StubVisionProDriver:
    return StubVisionProDriver()


@pytest.fixture
def ctx_quest(stub_quest_driver) -> ToolContext:
    return make_ctx(driver=stub_quest_driver)


@pytest.fixture
def ctx_visionpro(stub_visionpro_driver) -> ToolContext:
    return make_ctx(driver=stub_visionpro_driver)


@pytest.fixture
def ctx_no_driver() -> ToolContext:
    return make_ctx(driver=None)
