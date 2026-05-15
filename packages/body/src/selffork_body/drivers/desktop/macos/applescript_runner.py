"""AppleScript / JXA runner wrapper (M5 — ADR-005 §M5-C4).

Subprocess wrapper around ``osascript -l <lang> -e <script>``. Always T2
risk_tier — the warden gates the call before this runner sees it.
"""

from __future__ import annotations

import asyncio
from typing import Literal

__all__ = ["AppleScriptRunner"]


class AppleScriptRunner:
    """Thin async wrapper around ``osascript``."""

    async def run(
        self,
        script: str,
        *,
        language: Literal["AppleScript", "JavaScript"] = "JavaScript",
    ) -> str:
        cmd = ["osascript", "-l", language, "-e", script]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"osascript failed (rc={proc.returncode}): {stderr.decode(errors='replace')}"
            )
        return stdout.decode(errors="replace")

    async def app_launch(self, bundle_id: str) -> None:
        await self.run(f'Application("{bundle_id}").launch();')

    async def app_activate(self, bundle_id: str) -> None:
        await self.run(f'Application("{bundle_id}").activate();')

    async def app_quit(self, bundle_id: str) -> None:
        await self.run(f'Application("{bundle_id}").quit();')
