"""Minimax Snapper — Token Plan ``/v1/token_plan/remains`` → QuotaSnapshot.

ARGE 2026-05-09: Minimax mmx-cli stores OAuth credentials at
``~/.mmx/credentials.json``. The Token Plan API exposes an authenticated
GET endpoint that returns remaining quota for the active subscription:

  GET https://api.minimax.io/v1/token_plan/remains   (Global)
  GET https://api.minimaxi.com/v1/token_plan/remains (China)
  Authorization: Bearer <oauth_access_token>

This snapper:

1. Reads ``~/.mmx/credentials.json`` and extracts the OAuth access token
   (rejects entries that don't look OAuth-shaped — auth-only kuralı).
2. Probes the Token Plan endpoint and projects the response into
   normalized :class:`WindowState` records.

If the HTTP probe fails (network down, endpoint changed, rate-limit on
the metering endpoint itself), we still emit a snapshot with empty
``windows`` and ``source="credentials-present"`` — the autopilot's
``available_clis`` tool then surfaces ``status="auth_only"``.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from selffork_orchestrator.snappers.base import Snapper
from selffork_shared.quota import QuotaSnapshot, WindowKind, WindowState

__all__ = ["MinimaxSnapper"]

_DEFAULT_MMX_DIR = Path.home() / ".mmx"

_FIVE_HOUR_SECONDS = 5 * 3600
_ONE_DAY_SECONDS = 24 * 3600

_GLOBAL_USAGE_URL = "https://api.minimax.io/v1/token_plan/remains"
_DEFAULT_TIMEOUT_SECONDS = 5.0


class MinimaxSnapper(Snapper):
    """mmx OAuth credentials → QuotaSnapshot via Token Plan probe.

    Args:
        mmx_home: Override (default ``~/.mmx``).
        usage_url: Override probe URL (testing / China region routing).
        http_client: Inject a httpx.AsyncClient (testing).
        timeout_seconds: Per-request timeout when no client is injected.
    """

    def __init__(
        self,
        mmx_home: Path | None = None,
        *,
        usage_url: str = _GLOBAL_USAGE_URL,
        http_client: httpx.AsyncClient | None = None,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(cli_id="minimax-cli")
        self._mmx_home = mmx_home if mmx_home is not None else _DEFAULT_MMX_DIR
        self._usage_url = usage_url
        self._client = http_client
        self._timeout = timeout_seconds

    async def snapshot(self) -> QuotaSnapshot | None:
        access = self._read_access_token()
        if access is None:
            return None
        captured_at = datetime.now(tz=UTC)
        windows = await self._probe_usage(access, captured_at)
        return QuotaSnapshot(
            cli_id="minimax-cli",
            account_id=None,
            windows=windows,
            context=None,
            captured_at=captured_at,
            source="credentials-present",
        )

    # ── helpers ──────────────────────────────────────────────────────────

    def _read_access_token(self) -> str | None:
        credentials = self._mmx_home / "credentials.json"
        if not credentials.exists():
            return None
        try:
            text = credentials.read_text(encoding="utf-8")
            data = json.loads(text)
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        # mmx-cli historically uses ``access_token`` (Hermes/PKCE convention).
        # Probe both keys defensively; reject empty / non-string values.
        access = data.get("access_token")
        if not isinstance(access, str) or not access:
            access = data.get("access")
        if not isinstance(access, str) or not access:
            return None
        return access

    async def _probe_usage(
        self,
        access: str,
        captured_at: datetime,
    ) -> dict[WindowKind, WindowState]:
        try:
            payload = await self._fetch_payload(access)
        except (httpx.HTTPError, ValueError):
            return {}
        return self._project_windows(payload, captured_at=captured_at)

    async def _fetch_payload(self, access: str) -> dict[str, object]:
        headers = {"Authorization": f"Bearer {access}"}
        if self._client is not None:
            response = await self._client.get(self._usage_url, headers=headers)
            response.raise_for_status()
            data = response.json()
        else:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(self._usage_url, headers=headers)
                response.raise_for_status()
                data = response.json()
        if not isinstance(data, dict):
            raise ValueError("token_plan/remains payload is not a JSON object")  # noqa: TRY004
        return data

    @staticmethod
    def _project_windows(
        payload: dict[str, object],
        *,
        captured_at: datetime,
    ) -> dict[WindowKind, WindowState]:
        result: dict[WindowKind, WindowState] = {}
        for source_key, window_seconds, target in (
            ("rate_limit_5h", _FIVE_HOUR_SECONDS, WindowKind.five_hour),
            ("rate_limit_daily", _ONE_DAY_SECONDS, WindowKind.daily),
        ):
            window_data = payload.get(source_key)
            if not isinstance(window_data, dict):
                continue
            used_pct = _coerce_pct(window_data.get("used_percent"))
            resets_at = _coerce_resets_at(
                window_data.get("resets_in_seconds"),
                captured_at=captured_at,
            )
            if used_pct is None or resets_at is None:
                continue
            result[target] = WindowState(
                used_pct=used_pct,
                resets_at=resets_at,
                window_seconds=window_seconds,
            )
        return result


def _coerce_pct(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return min(max(float(value), 0.0), 100.0)
    return None


def _coerce_resets_at(
    resets_in: object,
    *,
    captured_at: datetime,
) -> datetime | None:
    if not isinstance(resets_in, (int, float)) or resets_in <= 0:
        return None
    try:
        return captured_at + timedelta(seconds=int(resets_in))
    except (OverflowError, ValueError):
        return None
