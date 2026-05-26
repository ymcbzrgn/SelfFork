"""Mobile body driver factory (S-ToolFleet Faz 1 §A — F1 WIRE close).

Builds the concrete body driver injected into ``Session`` (and thus
``ToolContext``) so that ``body_*`` and ``ios_*``/``android_*`` tools
can reach a real device through the Self Jr round-loop.

Resolution order:

1. Explicit ``platform`` argument.
2. ``SELFFORK_BODY_PLATFORM`` env (``ios|android|both|none|auto``).
3. Default ``none`` (no driver). Set explicitly to opt in — keeps
   existing tests and orphan runs untouched.

When ``platform="both"`` the factory returns a
:class:`CompositeMobileDriver` that routes ``body_*`` calls to the
preferred platform (default iOS) while exposing ``.ios`` and ``.android``
attributes for the platform-specific tool packs.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Literal, Protocol, runtime_checkable

from selffork_body.drivers.android import AndroidDriver
from selffork_body.drivers.ios import IosDriver

_LOG = logging.getLogger(__name__)

__all__ = [
    "BodyDriverProtocol",
    "CompositeMobileDriver",
    "build_default_body_driver",
    "resolve_platform",
]


@runtime_checkable
class BodyDriverProtocol(Protocol):
    """Duck-typed protocol every body driver satisfies.

    Tools never type-check against the protocol (they call methods on a
    plain ``object``-typed attribute); the protocol exists for static
    documentation + ``isinstance`` checks at the factory boundary.
    """

    platform: str

    async def start(self) -> None: ...

    async def stop(self) -> None: ...


def resolve_platform(
    value: str | None = None,
) -> Literal["ios", "android", "both", "web", "macos", "quest", "visionpro", "none"]:
    """Resolve the active body platform from arg → env → default.

    ``auto`` maps to ``ios`` on macOS, ``android`` on Linux, ``none``
    elsewhere. Unrecognised values collapse to ``none`` rather than
    raising so a misconfigured env can't crash session startup.

    S-ToolFleet Faz 2: ``web`` accepted — Playwright browser body driver.
    S-ToolFleet Faz 3: ``macos`` accepted — cua-style background desktop driver.
    S-ToolFleet Faz 4: ``quest`` (Quest 3 Android-derived VR) +
    ``visionpro`` (visionOS simulator vision-only) accepted.
    """

    raw: str = (value or os.environ.get("SELFFORK_BODY_PLATFORM") or "none").lower().strip()
    if raw == "ios":
        return "ios"
    if raw == "android":
        return "android"
    if raw == "both":
        return "both"
    if raw in ("web", "browser"):
        return "web"
    if raw in ("macos", "desktop"):
        return "macos"
    if raw in ("quest", "quest3"):
        return "quest"
    if raw in ("visionpro", "vision-pro", "visionos"):
        return "visionpro"
    if raw == "auto":
        if sys.platform == "darwin":
            return "ios"
        if sys.platform.startswith("linux"):  # type: ignore[unreachable]
            return "android"
        return "none"
    # unknown env value (including "none" and any garbage) collapses to disabled
    return "none"


def _resolve_prefer() -> Literal["ios", "android"]:
    raw = (os.environ.get("SELFFORK_BODY_PREFER") or "ios").lower().strip()
    if raw == "android":
        return "android"
    return "ios"


class CompositeMobileDriver:
    """Routes body_* calls to first-available platform; exposes .ios + .android.

    For tools like ``body_click`` that take a single target + bbox the
    composite forwards to the preferred platform's driver. Platform-
    specific tools (``ios_*`` / ``android_*``) reach through
    ``.ios`` / ``.android`` directly and bypass the dispatch.
    """

    platform: str = "composite"

    def __init__(
        self,
        *,
        ios: IosDriver | None = None,
        android: AndroidDriver | None = None,
        prefer: Literal["ios", "android"] = "ios",
    ) -> None:
        if ios is None and android is None:
            raise ValueError(
                "CompositeMobileDriver requires at least one of ios=/android=",
            )
        self.ios = ios
        self.android = android
        self._prefer: Literal["ios", "android"] = prefer

    @property
    def _primary(self) -> Any:
        if self._prefer == "ios" and self.ios is not None:
            return self.ios
        if self._prefer == "android" and self.android is not None:
            return self.android
        return self.ios or self.android

    async def start(self) -> None:
        if self.ios is not None:
            await self.ios.start()
        if self.android is not None:
            await self.android.start()

    async def stop(self) -> None:
        # Stop both in parallel-ish order; swallow per-platform errors so
        # one stuck simulator can't block the other's teardown.
        for drv in (self.ios, self.android):
            if drv is None:
                continue
            try:
                await drv.stop()
            except Exception as exc:  # composite teardown best-effort
                _LOG.debug("composite_stop_swallowed: %s", exc)
                continue

    async def click(
        self,
        target: str,
        bbox: tuple[int, int, int, int] | None = None,
        button: str = "left",
    ) -> None:
        await self._primary.click(target, bbox=bbox, button=button)

    async def type_text(self, text: str, target: str | None = None) -> None:
        await self._primary.type_text(text, target=target)

    async def screenshot(
        self, rect: tuple[int, int, int, int] | None = None,
    ) -> bytes:
        return await self._primary.screenshot(rect)  # type: ignore[no-any-return]

    async def scroll(self, direction: str = "down", amount: int = 300) -> None:
        await self._primary.scroll(direction=direction, amount=amount)

    async def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int = 250,
    ) -> None:
        await self._primary.swipe(
            start_x, start_y, end_x, end_y, duration_ms=duration_ms,
        )

    async def app_launch(self, bundle_id: str) -> None:
        await self._primary.app_launch(bundle_id)

    async def press_key(self, key_combo: str) -> None:
        await self._primary.press_key(key_combo)

    async def ax_tree(self, bundle_id: str | None = None) -> Any:
        return await self._primary.ax_tree(bundle_id=bundle_id)

    async def storage_state_save(
        self, provider: str, project_slug: str | None = None,
    ) -> Any:
        return await self._primary.storage_state_save(
            provider, project_slug=project_slug,
        )

    async def storage_state_load(
        self, provider: str, project_slug: str | None = None,
    ) -> Any:
        return await self._primary.storage_state_load(
            provider, project_slug=project_slug,
        )


def build_default_body_driver(
    *,
    platform: str | None = None,
    ios_device: str | None = None,
    ios_version: str | None = None,
    android_runtime: Literal["docker", "physical"] | None = None,
    android_device_serial: str | None = None,
    browser_headless: bool | None = None,
    browser_storage_state_path: Any | None = None,
    browser_allowed_domains: set[str] | None = None,
) -> Any:
    """Construct the canonical body driver per platform resolution.

    Returns ``None`` when platform resolves to ``"none"`` — caller
    should pass ``None`` through to :class:`Session` so the warden's
    ``no_warden_wired`` deny continues to gate body tools.

    Otherwise returns one of :class:`IosDriver`, :class:`AndroidDriver`,
    or :class:`CompositeMobileDriver`. The driver is **not** started —
    the caller (``cli.py``) wraps ``Session.run()`` with start/stop so
    the driver's lifecycle matches the session's, and start failures
    are surfaced + logged rather than crashing startup.
    """

    resolved = resolve_platform(platform)
    if resolved == "none":
        return None

    if resolved == "web":
        from selffork_body.drivers.web.playwright_driver import PlaywrightWebDriver

        headless_env = os.environ.get("SELFFORK_BODY_BROWSER_HEADLESS", "1").strip()
        headless = (
            browser_headless
            if browser_headless is not None
            else headless_env not in ("0", "false", "no")
        )
        return PlaywrightWebDriver(
            headless=headless,
            storage_state_path=browser_storage_state_path,
            allowed_domains=browser_allowed_domains,
        )

    if resolved == "macos":
        from selffork_body.drivers.desktop.macos.driver import MacOSDesktopDriver

        return MacOSDesktopDriver()

    if resolved == "quest":
        from selffork_body.drivers.vr.quest import QuestDriver

        return QuestDriver(
            device_serial=os.environ.get("SELFFORK_BODY_QUEST_DEVICE"),
        )

    if resolved == "visionpro":
        from selffork_body.drivers.vr.visionpro import VisionProDriver

        return VisionProDriver(
            device_id=os.environ.get("SELFFORK_BODY_VISIONPRO_DEVICE"),
        )

    if resolved == "ios":
        return IosDriver(
            runtime="sim",
            device_id=ios_device or os.environ.get("SELFFORK_BODY_IOS_DEVICE"),
            ios_version=ios_version or os.environ.get(
                "SELFFORK_BODY_IOS_VERSION", "17.2",
            ),
        )

    if resolved == "android":
        runtime_choice: Literal["docker", "physical"] = (
            android_runtime
            or _resolve_android_runtime()
        )
        return AndroidDriver(
            runtime=runtime_choice,
            device_serial=android_device_serial or os.environ.get(
                "SELFFORK_BODY_ANDROID_DEVICE",
            ),
        )

    # both
    ios = IosDriver(
        runtime="sim",
        device_id=ios_device or os.environ.get("SELFFORK_BODY_IOS_DEVICE"),
        ios_version=ios_version or os.environ.get(
            "SELFFORK_BODY_IOS_VERSION", "17.2",
        ),
    )
    runtime_choice = android_runtime or _resolve_android_runtime()
    android = AndroidDriver(
        runtime=runtime_choice,
        device_serial=android_device_serial or os.environ.get(
            "SELFFORK_BODY_ANDROID_DEVICE",
        ),
    )
    return CompositeMobileDriver(ios=ios, android=android, prefer=_resolve_prefer())


def _resolve_android_runtime() -> Literal["docker", "physical"]:
    raw = (os.environ.get("SELFFORK_BODY_ANDROID_RUNTIME") or "docker").lower().strip()
    if raw == "physical":
        return "physical"
    return "docker"
