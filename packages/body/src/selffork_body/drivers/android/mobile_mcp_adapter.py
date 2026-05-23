"""mobile-mcp HTTP adapter (M5 — ADR-005 §M5-C2).

Talks to ``mobile-next/mobile-mcp`` server's REST surface. Tap / swipe /
type / screenshot / app launch / install APK / press_key / ax tree dump
all map to specific endpoints; we keep the adapter thin so M5 can swap to
mobile-mcp's MCP-over-stdio variant if the team prefers later.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal, cast

__all__ = ["MobileMcpAdapter"]

_log = logging.getLogger(__name__)


class MobileMcpAdapter:
    """HTTP wrapper around a running ``mobile-mcp`` server."""

    def __init__(self, mcp_url: str = "http://127.0.0.1:8000") -> None:
        self.mcp_url = mcp_url.rstrip("/")
        # ``httpx.AsyncClient`` is lazily constructed inside
        # ``_ensure_client`` so module import is cheap; typed ``Any``
        # so the lazy import doesn't surface as ``None`` everywhere.
        self._client: Any = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def tap(self, x: int, y: int) -> None:
        client = self._ensure_client()
        r = await client.post(f"{self.mcp_url}/tap", json={"x": x, "y": y})
        r.raise_for_status()

    async def long_press(self, x: int, y: int, duration_ms: int = 800) -> None:
        client = self._ensure_client()
        r = await client.post(
            f"{self.mcp_url}/long_press",
            json={"x": x, "y": y, "duration_ms": duration_ms},
        )
        r.raise_for_status()

    async def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int = 250,
    ) -> None:
        client = self._ensure_client()
        r = await client.post(
            f"{self.mcp_url}/swipe",
            json={
                "start_x": start_x, "start_y": start_y,
                "end_x": end_x, "end_y": end_y,
                "duration_ms": duration_ms,
            },
        )
        r.raise_for_status()

    async def type_text(self, text: str) -> None:
        client = self._ensure_client()
        r = await client.post(f"{self.mcp_url}/type", json={"text": text})
        r.raise_for_status()

    async def screenshot(self) -> bytes:
        client = self._ensure_client()
        r = await client.get(f"{self.mcp_url}/screenshot")
        r.raise_for_status()
        return cast(bytes, r.content)

    async def install_apk(self, apk_path: Path) -> None:
        client = self._ensure_client()
        with apk_path.open("rb") as fh:
            files = {"apk": (apk_path.name, fh, "application/vnd.android.package-archive")}
            r = await client.post(f"{self.mcp_url}/install_apk", files=files)
        r.raise_for_status()

    async def app_launch(self, package: str) -> None:
        client = self._ensure_client()
        r = await client.post(f"{self.mcp_url}/launch", json={"package": package})
        r.raise_for_status()

    async def press_key(
        self,
        key: Literal["back", "home", "menu", "app_switch", "power", "volume_up", "volume_down"],
    ) -> None:
        client = self._ensure_client()
        r = await client.post(f"{self.mcp_url}/press_key", json={"key": key})
        r.raise_for_status()

    async def dump_a11y_tree(self) -> dict[str, Any]:
        client = self._ensure_client()
        r = await client.get(f"{self.mcp_url}/a11y_tree")
        r.raise_for_status()
        return cast("dict[str, Any]", r.json())
