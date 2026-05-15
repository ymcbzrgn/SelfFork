"""Z.AI / GLM Coding Plan snapper.

ARGE 2026-05-09: Yamaç's Z.AI subscription is routed through
``opencode auth login`` (native OAuth). The OAuth token lives in
opencode's auth.json under the ``zai`` provider key (``providers.zai.access``).

This snapper:

1. Confirms login state from opencode's auth.json (auth-only kuralı —
   we deliberately reject ``providers.zai`` entries that aren't
   ``type: "oauth"``).
2. Probes Z.AI's quota endpoint (``GET /v1/usage`` with the OAuth Bearer
   token) and projects the response into normalized
   :class:`WindowState` records.

If the HTTP probe fails (network down, endpoint changed, rate limit
on the metering endpoint itself), we still emit a snapshot with empty
``windows`` and ``source="opencode-auth-zai"`` — the autopilot's
``available_clis`` tool then surfaces ``status="auth_only"`` so Jr can
decide rather than silently routing real work to a CLI whose quota is
unknown.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from selffork_orchestrator.snappers.base import Snapper
from selffork_shared.quota import (
    QuotaSnapshot,
    WindowKind,
    WindowState,
)

__all__ = ["ZaiSnapper", "default_opencode_auth_path"]

# Z.AI subscription Coding Plan windows: 5h primary + daily secondary
# (Verdent guide 2026-05-09; Plus tier ~300 prompts/5h, Max ~1000).
_FIVE_HOUR_SECONDS = 5 * 3600
_ONE_DAY_SECONDS = 24 * 3600

# Probe endpoint (international tier). The CN tier (api.z.ai vs api.bigmodel.cn)
# uses the same path; SelfFork is operator-side single-region today.
_DEFAULT_USAGE_URL = "https://api.z.ai/v1/usage"
_DEFAULT_TIMEOUT_SECONDS = 5.0


def default_opencode_auth_path() -> Path:
    """Resolve opencode's auth.json (macOS / Linux fallback).

    On macOS opencode writes to ``~/Library/Application Support/opencode/auth.json``;
    Linux falls back to ``~/.local/share/opencode/auth.json``. Snapper picks
    whichever exists at call time so the same code works on both.
    """
    macos_path = Path.home() / "Library" / "Application Support" / "opencode" / "auth.json"
    if macos_path.exists():
        return macos_path
    return Path.home() / ".local" / "share" / "opencode" / "auth.json"


class ZaiSnapper(Snapper):
    """Z.AI subscription snapper.

    Args:
        opencode_auth_path: Override (default resolves macOS / Linux paths).
        usage_url: Override probe URL (testing / region routing).
        http_client: Inject a httpx.AsyncClient (testing). Default: lazy
            short-lived per-call client with ``timeout=5.0``.
    """

    def __init__(
        self,
        opencode_auth_path: Path | None = None,
        *,
        usage_url: str = _DEFAULT_USAGE_URL,
        http_client: httpx.AsyncClient | None = None,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(cli_id="zai")
        self._auth_path = (
            opencode_auth_path if opencode_auth_path is not None else default_opencode_auth_path()
        )
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
            cli_id="zai",
            account_id=None,
            windows=windows,
            context=None,
            captured_at=captured_at,
            source="opencode-auth-zai",
        )

    # ── helpers ──────────────────────────────────────────────────────────

    def _read_access_token(self) -> str | None:
        """Return a valid OAuth access token from opencode's auth.json,
        or ``None`` when the snapper should skip this tick (no login,
        malformed JSON, API-key entry, missing access).
        """
        if not self._auth_path.exists():
            return None
        try:
            text = self._auth_path.read_text(encoding="utf-8")
            data = json.loads(text)
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        providers = data.get("providers")
        if not isinstance(providers, dict):
            return None
        zai = providers.get("zai")
        if not isinstance(zai, dict):
            return None
        # Auth-only kuralı: API-key path REJECTED.
        if zai.get("type") != "oauth":
            return None
        access = zai.get("access")
        if not isinstance(access, str) or not access:
            return None
        return access

    async def _probe_usage(
        self,
        access: str,
        captured_at: datetime,
    ) -> dict[WindowKind, WindowState]:
        """GET /v1/usage; project response into normalized windows.

        Network/HTTP failures collapse to empty windows (caller surfaces
        ``auth_only`` status). Schema unknowns are skipped silently —
        Z.AI's documented response includes ``rate_limit_5h`` /
        ``rate_limit_daily`` style fields; we read whichever subset is
        present at call time.
        """
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
            raise ValueError("usage payload is not a JSON object")  # noqa: TRY004
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
