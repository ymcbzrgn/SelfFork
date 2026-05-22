"""CodexBar snapper — secondary quota source via ``codexbar serve`` HTTP.

ADR-007 §4 S-Quota / `[[codexbar-adoption-2026-05-22]]` adapter-shim
pattern. SelfFork's per-CLI snappers (claude_snap.sh statusline,
codex rollout JSONL tail, opencode SQLite, ...) stay as the **primary**
low-latency source. CodexBar runs as a sidecar process and provides:

* A **secondary** cross-check for our 5 CLIs (Claude / Codex / Gemini /
  MiniMax / z.ai), surfacing weekly windows, credits, and Admin-API
  spend that the SelfFork snappers don't capture.
* The **primary** Gemini quota signal when Gemini OTel telemetry is off
  (the OTel log is silent on most operator setups → SelfFork's
  GeminiSnapper produces no QuotaSnapshot at all; CodexBar's OAuth
  ``retrieveUserQuota`` call gives a real number).

The wire shape is documented in
``examples_crucial/CodexBar/docs/cli.md`` §"Sample output (JSON,
pretty)". We map the public ``usage.primary / .secondary`` windows onto
SelfFork's :class:`QuotaSnapshot` schema.

Construction is per-CLI: one ``CodexBarSnapper(cli_id="claude-code")``
produces snapshots labelled ``claude-code`` even though CodexBar's
internal provider id is ``claude``. The translation table lives in
:data:`_PROVIDER_ID_MAP`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Final

import httpx
from pydantic import ValidationError

from selffork_orchestrator.snappers.base import Snapper
from selffork_shared.quota import (
    QuotaSnapshot,
    WindowKind,
    WindowState,
)

__all__ = [
    "DEFAULT_HTTP_TIMEOUT_SECONDS",
    "DEFAULT_SIDECAR_PORT",
    "CodexBarSnapper",
    "map_codexbar_payload",
]

_log = logging.getLogger(__name__)

DEFAULT_SIDECAR_PORT: Final[int] = 8766
"""Default port the SelfFork dashboard binds ``codexbar serve`` to.

Distinct from the dashboard's own port (8765) so the two can run
side-by-side on a single host without a flag collision.
"""

DEFAULT_HTTP_TIMEOUT_SECONDS: Final[float] = 4.0
"""Per-request budget for CodexBar HTTP calls.

CodexBar's ``serve`` keeps a 60-second TTL cache, so most calls return
immediately; we cap at four seconds so a stuck provider request never
blocks SnapperRunner's 1-Hz tick budget.
"""

# CodexBar internal provider ID  →  SelfFork CLIAgent registry key.
# Symmetrical reverse lookup in :data:`_SELFFORK_TO_CODEXBAR`. The
# six entries here cover SelfFork's five priority CLIs plus the
# opencode-routed ``zai`` (Z.AI / GLM) surface.
_PROVIDER_ID_MAP: Final[dict[str, str]] = {
    "claude": "claude-code",
    "codex": "codex",
    "gemini": "gemini-cli",
    "minimax": "minimax-cli",
    "zai": "zai",
    "opencode": "opencode",
}

_SELFFORK_TO_CODEXBAR: Final[dict[str, str]] = {
    v: k for k, v in _PROVIDER_ID_MAP.items()
}


def _selffork_to_codexbar_id(cli_id: str) -> str:
    """Return CodexBar's internal provider id for a SelfFork ``cli_id``.

    Raises:
        ValueError: when ``cli_id`` is outside the supported map. The
            caller should have validated against
            :func:`registered_snapper_ids` first.
    """
    try:
        return _SELFFORK_TO_CODEXBAR[cli_id]
    except KeyError as exc:
        msg = (
            f"CodexBarSnapper: cli_id={cli_id!r} has no CodexBar provider "
            f"mapping; known: {sorted(_SELFFORK_TO_CODEXBAR)}"
        )
        raise ValueError(msg) from exc


# CodexBar's ``windowMinutes`` values, normalised into SelfFork's
# :class:`WindowKind` enum. The 300/10080 values are the Claude/Codex
# subscription windows; 1 and 1440 cover Gemini RPM/RPD; anything else
# falls through to ``rolling``.
_WINDOW_KIND_BY_MINUTES: Final[dict[int, WindowKind]] = {
    300: WindowKind.five_hour,
    10080: WindowKind.seven_day,
    1: WindowKind.per_minute,
    1440: WindowKind.daily,
}


def _window_kind_for_minutes(window_minutes: int) -> WindowKind:
    """Map a CodexBar ``windowMinutes`` value onto a :class:`WindowKind`.

    Unknown values default to :data:`WindowKind.rolling` (CodexBar's
    payload is the source of truth for the actual window length —
    ``window_seconds`` captures that verbatim).
    """
    if window_minutes <= 0:
        return WindowKind.unknown
    return _WINDOW_KIND_BY_MINUTES.get(window_minutes, WindowKind.rolling)


def _parse_iso8601(value: Any) -> datetime | None:
    """Best-effort parse a CodexBar ISO-8601 timestamp.

    CodexBar emits zulu timestamps (``"2025-12-04T19:15:00Z"``);
    :func:`datetime.fromisoformat` accepts the trailing ``Z`` only on
    Python 3.11+, so we normalise to ``+00:00`` before parsing.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _window_from_payload(raw: Any) -> tuple[WindowKind, WindowState] | None:
    """Translate one CodexBar ``usage.<slot>`` block to a SelfFork window.

    Returns ``None`` when the slot is null or malformed — callers fold
    the per-slot ``None`` outputs out of the resulting dict so the
    final QuotaSnapshot only carries windows we trust.
    """
    if not isinstance(raw, dict):
        return None
    used = raw.get("usedPercent")
    minutes = raw.get("windowMinutes")
    resets_at_raw = raw.get("resetsAt")
    if (
        not isinstance(used, (int, float))
        or not isinstance(minutes, int)
        or minutes <= 0
    ):
        return None
    resets_at = _parse_iso8601(resets_at_raw)
    if resets_at is None:
        return None
    try:
        state = WindowState(
            used_pct=max(0.0, min(100.0, float(used))),
            resets_at=resets_at,
            window_seconds=int(minutes) * 60,
        )
    except ValidationError:
        return None
    return _window_kind_for_minutes(int(minutes)), state


def map_codexbar_payload(
    payload: dict[str, Any], *, cli_id: str
) -> QuotaSnapshot | None:
    """Project one CodexBar ``GET /usage`` payload into a :class:`QuotaSnapshot`.

    Returns ``None`` when the payload is unusable (missing usage block,
    no parseable window). Callers (``CodexBarSnapper.snapshot``) drop
    ``None`` results so the dashboard never surfaces a placeholder.
    """
    usage_block = payload.get("usage")
    if not isinstance(usage_block, dict):
        return None

    windows: dict[WindowKind, WindowState] = {}
    for slot in ("primary", "secondary", "tertiary"):
        translated = _window_from_payload(usage_block.get(slot))
        if translated is None:
            continue
        kind, state = translated
        windows.setdefault(kind, state)

    if not windows:
        return None

    captured_at = (
        _parse_iso8601(usage_block.get("updatedAt"))
        or _parse_iso8601(payload.get("status", {}).get("updatedAt"))
        or datetime.now(tz=UTC)
    )
    source_label = payload.get("source")
    source = (
        f"codexbar:{source_label}"
        if isinstance(source_label, str) and source_label
        else "codexbar"
    )

    account_id: str | None = None
    identity = usage_block.get("identity")
    if isinstance(identity, dict):
        candidate = identity.get("accountEmail")
        if isinstance(candidate, str) and candidate.strip():
            account_id = candidate.strip()

    try:
        return QuotaSnapshot(
            cli_id=cli_id,
            account_id=account_id,
            windows=windows,
            context=None,
            captured_at=captured_at,
            source=source,
        )
    except ValidationError:
        return None


class CodexBarSnapper(Snapper):
    """Pull one CLI's quota from a running ``codexbar serve`` sidecar.

    Args:
        cli_id: SelfFork CLIAgent registry key (e.g. ``"claude-code"``).
        base_url: Sidecar URL. Defaults to
            ``http://127.0.0.1:{DEFAULT_SIDECAR_PORT}``; the dashboard
            lifespan injects its real port at construction time.
        client: Pre-built ``httpx.AsyncClient`` (tests inject a mock
            transport). When ``None``, the snapper owns a private client
            and closes it in :meth:`aclose`.
        timeout_seconds: Per-request budget (see
            :data:`DEFAULT_HTTP_TIMEOUT_SECONDS`).
    """

    def __init__(
        self,
        cli_id: str = "claude-code",
        *,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(cli_id=cli_id)
        self._codexbar_provider_id = _selffork_to_codexbar_id(cli_id)
        self._base_url = (
            base_url
            if base_url is not None
            else f"http://127.0.0.1:{DEFAULT_SIDECAR_PORT}"
        ).rstrip("/")
        self._owned_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._timeout = timeout_seconds

    async def snapshot(self) -> QuotaSnapshot | None:
        """Pull the live payload for this snapper's CLI and project it.

        Returns ``None`` for any transient failure — connection refused
        (sidecar not running), HTTP non-2xx, parse error, empty windows.
        Hard exceptions (e.g. malformed base_url) propagate so the
        SnapperRunner audit captures the bug.
        """
        url = f"{self._base_url}/usage"
        try:
            response = await self._client.get(
                url,
                params={
                    "provider": self._codexbar_provider_id,
                    "format": "json",
                },
                timeout=self._timeout,
            )
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.PoolTimeout):
            return None
        except httpx.HTTPError as exc:
            _log.debug("codexbar_snapshot_http_error", extra={"err": str(exc)})
            return None
        if response.status_code != 200:
            return None
        try:
            payload = response.json()
        except ValueError:
            return None

        # ``serve`` returns either a single object (when a ``provider``
        # filter is set) or a list of payloads (all enabled providers).
        # Both shapes are documented in ``docs/cli.md``.
        if isinstance(payload, list):
            matched = next(
                (
                    p
                    for p in payload
                    if isinstance(p, dict)
                    and p.get("provider") == self._codexbar_provider_id
                ),
                None,
            )
            payload = matched
        if not isinstance(payload, dict):
            return None

        return map_codexbar_payload(payload, cli_id=self.cli_id)

    async def aclose(self) -> None:
        if self._owned_client:
            await self._client.aclose()
