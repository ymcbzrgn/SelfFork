"""Minimax Snapper — Token Plan ``/v1/token_plan/remains`` → QuotaSnapshot.

ARGE 2026-05-09: Minimax mmx-cli stores OAuth credentials at
``~/.mmx/credentials.json``. The Token Plan API exposes an authenticated
GET endpoint that returns remaining quota for the active subscription:

  GET https://api.minimax.io/v1/token_plan/remains
  Authorization: Bearer <oauth_access_token>

(China region: ``https://api.minimaxi.com/v1/token_plan/remains``.)

Order 7 scaffold (this module): the snapper checks credential existence
to decide ``None`` (auth missing) vs an empty-windows snapshot. Full HTTP
probe — non-blocking, region-aware, error-resilient — lands in a
follow-up patch that depends on httpx already in orchestrator deps.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from selffork_orchestrator.snappers.base import Snapper
from selffork_shared.quota import QuotaSnapshot

__all__ = ["MinimaxSnapper"]

_DEFAULT_MMX_DIR = Path.home() / ".mmx"


class MinimaxSnapper(Snapper):
    """Read mmx credentials presence; HTTP quota probe deferred.

    Args:
        mmx_home: Override (default ``~/.mmx``).
    """

    def __init__(self, mmx_home: Path | None = None) -> None:
        super().__init__(cli_id="minimax-cli")
        self._mmx_home = mmx_home if mmx_home is not None else _DEFAULT_MMX_DIR

    async def snapshot(self) -> QuotaSnapshot | None:
        credentials = self._mmx_home / "credentials.json"
        if not credentials.exists():
            return None
        # Optional sanity: ensure the file parses as JSON. We do not extract
        # the access token here — the snapper only confirms login state and
        # emits an empty-windows snapshot. The real quota probe lives in a
        # follow-up patch (httpx GET to /v1/token_plan/remains).
        try:
            text = credentials.read_text(encoding="utf-8")
            json.loads(text)
        except (OSError, json.JSONDecodeError):
            return None

        return QuotaSnapshot(
            cli_id="minimax-cli",
            account_id=None,
            windows={},  # filled by follow-up HTTP probe
            context=None,
            captured_at=datetime.now(tz=UTC),
            source="credentials-present",
        )
