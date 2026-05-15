"""PermissionWarden — 3-mode x 4-tier matrix + CVE-2025-47241 domain compare."""

from __future__ import annotations

import asyncio

import pytest

from selffork_body.sandbox import (
    PermissionWarden,
    WardenMode,
    WardenState,
    build_request,
    normalize_domain,
)

# ---------------------------------------------------------------------------
# normalize_domain — CVE-2025-47241 mitigation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://example.com/path", "example.com"),
        ("user@example.com", "example.com"),
        ("https://attacker@example.com", "example.com"),
        ("EXAMPLE.com", "example.com"),
        ("example.com:443", "example.com"),
        ("https://user:pass@example.com:8443/x", "example.com"),
        ("xn--mnchen-3ya.de", "xn--mnchen-3ya.de"),
        ("münchen.de", "xn--mnchen-3ya.de"),
        ("", ""),
    ],
)
def test_normalize_domain(raw: str, expected: str) -> None:
    assert normalize_domain(raw) == expected


# ---------------------------------------------------------------------------
# 3-mode x 4-tier auto-decision matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "action", "expected_approved"),
    [
        # read_only — only T0 passes
        (WardenMode.READ_ONLY, "screenshot", True),  # T0
        (WardenMode.READ_ONLY, "click", False),  # T1
        (WardenMode.READ_ONLY, "shell_exec", False),  # T2
        (WardenMode.READ_ONLY, "payment_form_submit", False),  # T3
        # workspace_write — T0/T1 pass, T2/T3 require operator
        (WardenMode.WORKSPACE_WRITE, "screenshot", True),
        (WardenMode.WORKSPACE_WRITE, "click", True),
        # danger — T0-T2 pass, T3 still gates
        (WardenMode.DANGER_FULL_ACCESS, "shell_exec", True),
        (WardenMode.DANGER_FULL_ACCESS, "screenshot", True),
    ],
)
async def test_auto_decision_matrix(
    mode: WardenMode, action: str, expected_approved: bool
) -> None:
    warden = PermissionWarden(mode=mode, default_timeout_sec=0.1)
    req = build_request(request_id="r-1", session_id="s-1", action_type=action)
    decision = await warden.request(req)
    assert decision.approved is expected_approved


async def test_workspace_write_t2_requires_operator_and_times_out() -> None:
    warden = PermissionWarden(mode=WardenMode.WORKSPACE_WRITE, default_timeout_sec=0.05)
    req = build_request(
        request_id="r-1", session_id="s-1", action_type="shell_exec"
    )
    decision = await warden.request(req)
    assert decision.approved is False
    assert "timeout" in decision.reason


async def test_workspace_write_t2_operator_approves() -> None:
    warden = PermissionWarden(mode=WardenMode.WORKSPACE_WRITE, default_timeout_sec=2.0)
    req = build_request(request_id="r-1", session_id="s-1", action_type="shell_exec")

    async def _approver() -> None:
        # Yield once so request() registers the future before we resolve it.
        await asyncio.sleep(0.01)
        await warden.operator_decide("r-1", approved=True, reason="ok")

    decision_task = asyncio.create_task(warden.request(req))
    await _approver()
    decision = await decision_task
    assert decision.approved is True
    assert decision.decided_by == "operator"


async def test_danger_t3_requires_operator_and_denies_on_timeout() -> None:
    warden = PermissionWarden(
        mode=WardenMode.DANGER_FULL_ACCESS, default_timeout_sec=0.05
    )
    req = build_request(
        request_id="r-1", session_id="s-1", action_type="payment_form_submit"
    )
    decision = await warden.request(req)
    assert decision.approved is False


# ---------------------------------------------------------------------------
# Domain allowlist + CVE-2025-47241 mitigation in warden.is_domain_allowed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("allowed", "target", "should_allow"),
    [
        ({"example.com"}, "https://example.com/p", True),
        ({"example.com"}, "https://attacker@example.com", True),  # userinfo stripped
        ({"example.com"}, "https://EXAMPLE.com", True),
        ({"example.com"}, "https://api.example.com", True),  # subdomain
        ({"example.com"}, "https://example.com.attacker.tld", False),
        ({"example.com"}, "https://attacker.com", False),
        ({"example.com"}, "https://example.com:8443", True),  # port stripped
    ],
)
async def test_domain_allowlist(
    allowed: set[str], target: str, should_allow: bool
) -> None:
    warden = PermissionWarden(
        mode=WardenMode.WORKSPACE_WRITE,
        allowed_domains=allowed,
        default_timeout_sec=0.05,
    )
    req = build_request(
        request_id="r-1",
        session_id="s-1",
        action_type="navigate",
        target_uri=target,
    )
    decision = await warden.request(req)
    if should_allow:
        assert decision.approved is True
    else:
        assert decision.approved is False
        assert "allowed_domains" in decision.reason


# ---------------------------------------------------------------------------
# kill switch
# ---------------------------------------------------------------------------


async def test_kill_resolves_pending_requests_as_denied() -> None:
    warden = PermissionWarden(mode=WardenMode.WORKSPACE_WRITE, default_timeout_sec=2.0)
    req = build_request(request_id="r-1", session_id="s-1", action_type="shell_exec")

    decision_task = asyncio.create_task(warden.request(req))
    await asyncio.sleep(0.01)  # let request register
    warden.kill("operator_stop")
    decision = await decision_task
    assert decision.approved is False
    assert decision.decision == "killed"
    assert decision.decided_by == "watchdog"
    assert warden.state == WardenState.KILLED


async def test_request_after_kill_immediately_denies() -> None:
    warden = PermissionWarden(mode=WardenMode.WORKSPACE_WRITE)
    warden.kill("manual")
    req = build_request(request_id="r-2", session_id="s-1", action_type="screenshot")
    decision = await warden.request(req)
    assert decision.approved is False
    assert "warden_state:killed" in decision.reason
