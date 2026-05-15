"""Permission warden — action-level gating for the M5 Body pillar.

State machine (ADR-005 §M5-D2)::

    INACTIVE → ARMED → AWAITING_APPROVAL → APPROVED → EXECUTING → AUDITED → ARMED
                            ↓                              ↓
                         DENIED ──────────────────→ AUDITED
                            ↑
                         KILLED (SIGKILL, any state)

Three modes select per-tier behavior:

* ``read_only``: T0 auto-allow, T1+ auto-deny (screenshots/observation only).
* ``workspace_write``: T0/T1 auto-allow, T2/T3 prompt operator (default).
* ``danger_full_access``: T0-T2 auto-allow, T3 still requires two-key confirm.

Domain comparison (browser-use CVE-2025-47241 lesson) strips userinfo + port
+ IDN-normalises before matching against ``allowed_domains``.
"""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from selffork_body.sandbox.risk_taxonomy import RiskTier, tier_for_action

__all__ = [
    "PermissionDecision",
    "PermissionRequest",
    "PermissionWarden",
    "WardenMode",
    "WardenState",
    "normalize_domain",
]


class WardenMode(Enum):
    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    DANGER_FULL_ACCESS = "danger_full_access"


class WardenState(Enum):
    INACTIVE = "inactive"
    ARMED = "armed"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    EXECUTING = "executing"
    AUDITED = "audited"
    DENIED = "denied"
    KILLED = "killed"


@dataclasses.dataclass(frozen=True, slots=True)
class PermissionRequest:
    request_id: str
    session_id: str
    action_type: str
    risk_tier: RiskTier
    target_uri: str | None
    args_summary: dict[str, Any]
    requested_at: datetime


@dataclasses.dataclass(frozen=True, slots=True)
class PermissionDecision:
    approved: bool
    decision: Literal["allow", "deny", "approved", "killed"]
    reason: str
    decided_at: datetime
    decided_by: Literal["auto", "operator", "warden", "watchdog"]


def normalize_domain(url_or_host: str) -> str:
    """Normalise a URL/host string for allowlist comparison.

    Strips userinfo (``user@``), port, scheme; lowercases; IDN→ASCII via
    ``idna``. Returns empty string for malformed input.
    """
    from urllib.parse import urlparse

    text = url_or_host.strip()
    if "://" not in text:
        text = f"http://{text}"
    parsed = urlparse(text)
    netloc = parsed.netloc or parsed.path
    if "@" in netloc:
        netloc = netloc.rsplit("@", 1)[1]
    if ":" in netloc:
        netloc = netloc.rsplit(":", 1)[0]
    netloc = netloc.lower()
    if not netloc:
        return ""
    try:
        return netloc.encode("idna").decode("ascii")
    except UnicodeError:
        return netloc


class PermissionWarden:
    """Per-session warden. Thread-safe via internal asyncio lock.

    Audit emit (caller responsibility): the warden returns a
    :class:`PermissionDecision`; the caller logs ``body.permission.requested``,
    ``body.permission.deny``, or attaches the decision to the surrounding
    ``body.action.invoke`` / ``body.action.executed`` event.
    """

    def __init__(
        self,
        *,
        mode: WardenMode = WardenMode.WORKSPACE_WRITE,
        allowed_domains: set[str] | None = None,
        action_tier_overrides: dict[str, RiskTier] | None = None,
        default_timeout_sec: float = 30.0,
    ) -> None:
        self._mode = mode
        self._allowed = {normalize_domain(d) for d in (allowed_domains or set())}
        self._allowed.discard("")
        self._tier_overrides = action_tier_overrides or {}
        self._default_timeout = default_timeout_sec
        self._state = WardenState.ARMED
        self._pending: dict[str, asyncio.Future[PermissionDecision]] = {}
        self._lock = asyncio.Lock()

    @property
    def state(self) -> WardenState:
        return self._state

    @property
    def mode(self) -> WardenMode:
        return self._mode

    def set_mode(self, mode: WardenMode) -> None:
        self._mode = mode

    def is_domain_allowed(self, target_uri: str | None) -> bool:
        if not target_uri:
            return True
        if not self._allowed:
            # No allowlist configured ⇒ no domain restriction (legacy / dev mode).
            # Operators wanting strict allowlist must explicitly set ``allowed_domains``.
            return True
        # Only run normalize when the input *looks* like a URL/host. A plain
        # element label such as "Submit" should not be treated as a domain.
        if "://" not in target_uri and "." not in target_uri:
            return True
        normalized = normalize_domain(target_uri)
        if not normalized:
            return False
        # Exact match OR subdomain match
        for allowed in self._allowed:
            if normalized == allowed or normalized.endswith(f".{allowed}"):
                return True
        return False

    def _auto_decision(
        self, action_type: str, risk_tier: RiskTier, target_uri: str | None
    ) -> PermissionDecision | None:
        """Return an auto-decision when policy allows; ``None`` when operator gate is required."""
        now = datetime.now(UTC)
        # Domain check first — applies regardless of tier when target_uri set.
        if target_uri and not self.is_domain_allowed(target_uri):
            return PermissionDecision(
                approved=False,
                decision="deny",
                reason="target_uri not in allowed_domains",
                decided_at=now,
                decided_by="warden",
            )
        if self._mode is WardenMode.READ_ONLY:
            if risk_tier == "T0":
                return PermissionDecision(True, "allow", "read_only:T0_auto", now, "auto")
            return PermissionDecision(False, "deny", f"read_only:tier_{risk_tier}_blocked", now, "warden")
        if self._mode is WardenMode.WORKSPACE_WRITE:
            if risk_tier in ("T0", "T1"):
                return PermissionDecision(True, "allow", "workspace_write:auto", now, "auto")
            return None  # T2/T3 → operator gate
        if self._mode is WardenMode.DANGER_FULL_ACCESS:
            if risk_tier in ("T0", "T1", "T2"):
                return PermissionDecision(True, "allow", "danger:auto_logged", now, "auto")
            return None  # T3 → two-key gate
        return None

    async def request(self, req: PermissionRequest) -> PermissionDecision:
        if self._state in (WardenState.KILLED, WardenState.INACTIVE):
            now = datetime.now(UTC)
            return PermissionDecision(False, "deny", f"warden_state:{self._state.value}", now, "warden")
        async with self._lock:
            auto = self._auto_decision(req.action_type, req.risk_tier, req.target_uri)
            if auto is not None:
                return auto
            # Need operator decision — register pending future
            loop = asyncio.get_running_loop()
            future: asyncio.Future[PermissionDecision] = loop.create_future()
            self._pending[req.request_id] = future
            self._state = WardenState.AWAITING_APPROVAL
        try:
            return await asyncio.wait_for(future, timeout=self._default_timeout)
        except TimeoutError:
            now = datetime.now(UTC)
            return PermissionDecision(
                False,
                "deny",
                f"timeout_after_{self._default_timeout}s",
                now,
                "warden",
            )
        finally:
            async with self._lock:
                self._pending.pop(req.request_id, None)
                if not self._pending and self._state == WardenState.AWAITING_APPROVAL:
                    self._state = WardenState.ARMED

    async def operator_decide(self, request_id: str, *, approved: bool, reason: str) -> bool:
        """Resolve a pending request. Returns ``True`` when matched, ``False`` otherwise."""
        async with self._lock:
            future = self._pending.get(request_id)
            if future is None or future.done():
                return False
            future.set_result(
                PermissionDecision(
                    approved=approved,
                    decision="approved" if approved else "deny",
                    reason=reason,
                    decided_at=datetime.now(UTC),
                    decided_by="operator",
                )
            )
            return True

    def kill(self, reason: str = "kill_requested") -> None:
        """Sync-safe kill switch. Resolves all pending requests as denied."""
        self._state = WardenState.KILLED
        for future in list(self._pending.values()):
            if not future.done():
                future.set_result(
                    PermissionDecision(
                        approved=False,
                        decision="killed",
                        reason=reason,
                        decided_at=datetime.now(UTC),
                        decided_by="watchdog",
                    )
                )
        self._pending.clear()


def build_request(
    *,
    request_id: str,
    session_id: str,
    action_type: str,
    target_uri: str | None = None,
    args_summary: dict[str, Any] | None = None,
    tier_overrides: dict[str, RiskTier] | None = None,
) -> PermissionRequest:
    """Helper to construct a request with auto-resolved tier."""
    return PermissionRequest(
        request_id=request_id,
        session_id=session_id,
        action_type=action_type,
        risk_tier=tier_for_action(action_type, tier_overrides),
        target_uri=target_uri,
        args_summary=args_summary or {},
        requested_at=datetime.now(UTC),
    )
