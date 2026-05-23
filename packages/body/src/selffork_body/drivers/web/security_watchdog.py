"""Page-level security watchdog for the web driver (M5 — ADR-005 §M5-C1).

Reimplements the navigation / popup / redirect-after gating pattern from
browser-use's ``security_watchdog`` (MIT) without copying source. Wraps
:class:`PermissionWarden` so denials surface as audit events and (when the
caller wires it) replace blocked navigations with ``about:blank``.

Domain comparison is delegated to
:func:`selffork_body.sandbox.warden.normalize_domain` which already handles
the CVE-2025-47241 lesson (userinfo + port + IDN).
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable
from typing import Any

from selffork_body.sandbox import normalize_domain

__all__ = ["SecurityWatchdog"]

_log = logging.getLogger(__name__)


class SecurityWatchdog:
    """Page-level navigation guard for a single Playwright session.

    ``allowed_domains`` is the trust set for *this* web session — the higher
    level :class:`PermissionWarden` handles per-action gating; this class
    handles the long-lived browser context.
    """

    def __init__(
        self,
        *,
        allowed_domains: set[str] | None = None,
        on_block: Callable[[str, str], None] | None = None,
    ) -> None:
        self._allowed = {normalize_domain(d) for d in (allowed_domains or set())}
        self._allowed.discard("")
        self._on_block = on_block
        self.blocked_count = 0

    @property
    def allowed_domains(self) -> set[str]:
        return set(self._allowed)

    def is_allowed(self, url: str) -> bool:
        if not self._allowed:
            return True
        normalized = normalize_domain(url)
        if not normalized:
            return False
        for allowed in self._allowed:
            if normalized == allowed or normalized.endswith(f".{allowed}"):
                return True
        return False

    async def on_framenavigated(self, frame) -> None:  # type: ignore[no-untyped-def]
        url = getattr(frame, "url", "")
        if not url or url.startswith("about:"):
            return
        if self.is_allowed(url):
            return
        self.blocked_count += 1
        _log.warning("security_watchdog_block url=%s", url)
        if self._on_block is not None:
            self._on_block("framenavigated", url)
        with contextlib.suppress(Exception):
            await frame.evaluate("window.stop(); window.location.href = 'about:blank';")

    async def on_popup(self, popup) -> None:  # type: ignore[no-untyped-def]
        url = getattr(popup, "url", "")
        if self.is_allowed(url):
            return
        self.blocked_count += 1
        _log.warning("security_watchdog_popup_block url=%s", url)
        if self._on_block is not None:
            self._on_block("popup", url)
        with contextlib.suppress(Exception):
            await popup.close()

    def attach(self, page: Any) -> None:
        """Wire the watchdog to a Playwright page's events."""
        page.on("framenavigated", lambda frame: page.context.event_loop.create_task(
            self.on_framenavigated(frame)
        ) if hasattr(page.context, "event_loop") else None)
        page.on("popup", lambda popup: page.context.event_loop.create_task(
            self.on_popup(popup)
        ) if hasattr(page.context, "event_loop") else None)
