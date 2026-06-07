"""body.* tools — Pydantic args + warden gate + driver dispatch + audit shape."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from selffork_body.sandbox import PermissionWarden, WardenMode
from selffork_orchestrator.tools import build_body_tools, build_default_registry
from selffork_orchestrator.tools.base import ToolContext


class _StubProjectStore:
    pass


@dataclass
class _StubDriver:
    """Minimal driver stub for tool dispatch tests."""

    last_call: tuple[str, tuple, dict] | None = None

    async def click(self, target, bbox=None, button="left"):
        self.last_call = ("click", (target,), {"bbox": bbox, "button": button})
        return {"ok": True}

    async def type_text(self, text, target=None):
        self.last_call = ("type", (text,), {"target": target})
        return {"ok": True}

    async def screenshot(self, rect=None):
        self.last_call = ("screenshot", (), {"rect": rect})
        return b"\x89PNG\r\n\x1a\n" + b"x" * 64

    async def scroll(self, direction, amount):
        self.last_call = ("scroll", (direction,), {"amount": amount})
        return {"ok": True}

    async def swipe(self, sx, sy, ex, ey, duration_ms):
        self.last_call = ("swipe", (sx, sy, ex, ey), {"duration_ms": duration_ms})
        return {"ok": True}

    async def app_launch(self, bundle_id):
        self.last_call = ("app_launch", (bundle_id,), {})
        return {"ok": True}

    async def press_key(self, key_combo):
        self.last_call = ("press_key", (key_combo,), {})
        return {"ok": True}

    async def storage_state_save(self, provider, project_slug):
        self.last_call = ("storage_state_save", (provider,), {"project_slug": project_slug})
        return f"/tmp/auth/{provider}.json"

    async def storage_state_load(self, provider, project_slug):
        self.last_call = ("storage_state_load", (provider,), {"project_slug": project_slug})
        return True

    async def ax_tree(self, bundle_id=None):
        self.last_call = ("ax_tree", (), {"bundle_id": bundle_id})
        return [{"role": "AXButton", "title": "OK"}]


def _ctx(*, driver=None, warden=None, audit_logger=None) -> ToolContext:
    # M5 audit-fix wave: _gate default-denies when warden=None to prevent
    # silent bypass in production. Tests that exercise the action surface
    # without an explicit warden should pass a permissive one
    # (``DANGER_FULL_ACCESS`` mode auto-allows T0-T2). Tests that exercise
    # the warden-missing path explicitly construct warden=None and assert
    # ``status="denied"`` with reason ``no_warden_wired``.
    if warden is None and driver is not None:
        warden = PermissionWarden(mode=WardenMode.DANGER_FULL_ACCESS)
    return ToolContext(
        session_id="sess-test",
        project_slug=None,
        project_store=_StubProjectStore(),
        body_driver=driver,
        permission_warden=warden,
        audit_logger=audit_logger,
    )


# ---------------------------------------------------------------------------
# Registry wiring
# ---------------------------------------------------------------------------


def test_body_tools_registered_in_default_registry() -> None:
    registry = build_default_registry()
    expected = {
        "body_click",
        "body_type",
        "body_screenshot",
        "body_scroll",
        "body_swipe",
        "body_app_launch",
        "body_press_key",
        "body_storage_state_save",
        "body_storage_state_load",
        "body_ax_tree",
    }
    actual = set(registry.names())
    assert expected.issubset(actual)


def test_body_tools_count() -> None:
    assert len(build_body_tools()) == 10


# ---------------------------------------------------------------------------
# Pydantic args validation
# ---------------------------------------------------------------------------


def test_click_args_default_button() -> None:
    from selffork_orchestrator.tools.body import BodyClickArgs

    args = BodyClickArgs(target="Submit")
    assert args.button == "left"
    assert args.bbox is None


def test_click_args_target_required() -> None:
    from pydantic import ValidationError

    from selffork_orchestrator.tools.body import BodyClickArgs

    with pytest.raises(ValidationError):
        BodyClickArgs(target="")


def test_swipe_args_validates_durations() -> None:
    from pydantic import ValidationError

    from selffork_orchestrator.tools.body import BodySwipeArgs

    with pytest.raises(ValidationError):
        BodySwipeArgs(start_x=0, start_y=0, end_x=10, end_y=10, duration_ms=10)
    with pytest.raises(ValidationError):
        BodySwipeArgs(start_x=0, start_y=0, end_x=10, end_y=10, duration_ms=10000)


# ---------------------------------------------------------------------------
# Handler — no driver in context → unauthorized
# ---------------------------------------------------------------------------


async def test_unauthorized_when_no_driver() -> None:
    from selffork_orchestrator.tools.body import BodyClickArgs, _body_click

    ctx = _ctx(driver=None)
    # raise_unauthorized() raises _UnauthorizedError, which extends RuntimeError.
    with pytest.raises(RuntimeError, match="body driver"):
        await _body_click(ctx, BodyClickArgs(target="Submit"))


async def test_denied_when_warden_not_wired() -> None:
    """M5 audit-fix wave: _gate default-denies on warden=None (no silent bypass)."""
    from selffork_orchestrator.tools.body import BodyClickArgs, _body_click

    driver = _StubDriver()
    ctx = ToolContext(
        session_id="sess-no-warden",
        project_slug=None,
        project_store=_StubProjectStore(),
        body_driver=driver,
        permission_warden=None,  # explicit — no warden wired
    )
    result = await _body_click(ctx, BodyClickArgs(target="Submit"))
    assert result["status"] == "denied"
    assert result["reason"] == "no_warden_wired"
    assert result["decided_by"] == "warden"
    # Driver MUST NOT have been touched.
    assert driver.last_call is None


async def test_screenshot_persists_via_screenshot_store() -> None:
    """ToolContext.screenshot_store wiring — body_screenshot returns ref_path."""
    import tempfile

    from selffork_body.storage import ScreenshotStore
    from selffork_orchestrator.tools.body import BodyScreenshotArgs, _body_screenshot

    driver = _StubDriver()
    with tempfile.TemporaryDirectory() as tmp:
        store = ScreenshotStore(root=__import__("pathlib").Path(tmp))
        ctx = ToolContext(
            session_id="sess-ss",
            project_slug=None,
            project_store=_StubProjectStore(),
            body_driver=driver,
            permission_warden=PermissionWarden(mode=WardenMode.DANGER_FULL_ACCESS),
            screenshot_store=store,
        )
        result = await _body_screenshot(ctx, BodyScreenshotArgs(rect=None))
        assert result["status"] == "ok"
        assert result["result"]["ref_path"] is not None
        assert result["result"]["ref_path"].endswith(".png")


async def test_audit_emit_called_for_body_action_lifecycle() -> None:
    """body.action.invoke + body.action.executed audit events fire on success."""
    from selffork_orchestrator.tools.body import BodyClickArgs, _body_click

    class _CaptureLogger:
        def __init__(self) -> None:
            self.events: list[tuple[str, dict]] = []

        def emit(self, category: str, *, payload: dict) -> None:
            self.events.append((category, payload))

    logger = _CaptureLogger()
    driver = _StubDriver()
    ctx = _ctx(driver=driver, audit_logger=logger)
    await _body_click(ctx, BodyClickArgs(target="Submit"))
    categories = [c for c, _ in logger.events]
    assert "body.permission.requested" in categories
    assert "body.action.invoke" in categories
    assert "body.action.executed" in categories


# ---------------------------------------------------------------------------
# Handler — warden allow path
# ---------------------------------------------------------------------------


async def test_click_executes_when_warden_allows() -> None:
    from selffork_orchestrator.tools.body import BodyClickArgs, _body_click

    driver = _StubDriver()
    warden = PermissionWarden(mode=WardenMode.WORKSPACE_WRITE)
    result = await _body_click(_ctx(driver=driver, warden=warden), BodyClickArgs(target="Submit"))
    assert result["status"] == "ok"
    assert driver.last_call is not None
    assert driver.last_call[0] == "click"
    assert "duration_ms" in result


async def test_click_denied_when_warden_blocks_domain() -> None:
    from selffork_orchestrator.tools.body import BodyClickArgs, _body_click

    driver = _StubDriver()
    warden = PermissionWarden(
        mode=WardenMode.WORKSPACE_WRITE,
        allowed_domains={"example.com"},
    )
    result = await _body_click(
        _ctx(driver=driver, warden=warden),
        BodyClickArgs(target="https://attacker.com/login"),
    )
    assert result["status"] == "denied"
    assert driver.last_call is None


async def test_screenshot_returns_bytes_size() -> None:
    from selffork_orchestrator.tools.body import BodyScreenshotArgs, _body_screenshot

    driver = _StubDriver()
    result = await _body_screenshot(_ctx(driver=driver), BodyScreenshotArgs(rect=None))
    assert result["status"] == "ok"
    assert result["result"]["bytes_size"] > 0
    # Path None when no screenshot_store wired.
    assert result["result"]["ref_path"] is None


async def test_swipe_passes_args_through() -> None:
    from selffork_orchestrator.tools.body import BodySwipeArgs, _body_swipe

    driver = _StubDriver()
    args = BodySwipeArgs(start_x=10, start_y=20, end_x=100, end_y=200, duration_ms=300)
    result = await _body_swipe(_ctx(driver=driver), args)
    assert result["status"] == "ok"
    assert driver.last_call == ("swipe", (10, 20, 100, 200), {"duration_ms": 300})


async def test_app_launch_audits_target_uri() -> None:
    from selffork_orchestrator.tools.body import BodyAppLaunchArgs, _body_app_launch

    driver = _StubDriver()
    result = await _body_app_launch(
        _ctx(driver=driver), BodyAppLaunchArgs(bundle_id="com.apple.finder")
    )
    assert result["status"] == "ok"
    assert driver.last_call == ("app_launch", ("com.apple.finder",), {})


async def test_storage_state_save_returns_path() -> None:
    from selffork_orchestrator.tools.body import (
        BodyStorageStateSaveArgs,
        _body_storage_state_save,
    )

    driver = _StubDriver()
    result = await _body_storage_state_save(
        _ctx(driver=driver), BodyStorageStateSaveArgs(provider="codex")
    )
    assert result["status"] == "ok"
    assert result["result"]["path"] == "/tmp/auth/codex.json"


async def test_handler_error_caught() -> None:
    from selffork_orchestrator.tools.body import BodyClickArgs, _body_click

    class _BoomDriver:
        async def click(self, *_args, **_kwargs):
            raise RuntimeError("driver boom")

    result = await _body_click(_ctx(driver=_BoomDriver()), BodyClickArgs(target="Submit"))
    assert result["status"] == "error"
    assert result["exception"] == "RuntimeError"
    assert "driver boom" in result["message"]
