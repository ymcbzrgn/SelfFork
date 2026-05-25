"""Tests for ProviderAuthMonitor + /api/providers/{name}/auth-expired (S5 Faz E).

The monitor is the operator-facing nudge that turns a silent CLI auth
expiry into a Telegram message with the exact re-login command. The
endpoint is the call surface — snappers / invocation wrappers /
manual triggers all reach the same place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from selffork_orchestrator.dashboard.provider_auth_monitor import (
    CLI_LOGIN_COMMANDS,
    ProviderAuthMonitor,
    _format_alert,
)
from selffork_orchestrator.dashboard.provider_router import (
    ProviderRegistry,
    build_provider_router,
)
from selffork_orchestrator.telegram.bridge import (
    NullTelegramBridge,
    TelegramBridge,
    TelegramMessage,
)


@dataclass
class _FakeAttempt:
    delivered: bool = True
    chat_id: int | None = 42
    reason: str | None = None


@dataclass
class _RecordingBridge(TelegramBridge):
    """In-memory Telegram bridge that records ``notify`` calls."""

    delivered: bool = True
    raise_on_notify: bool = False
    sent: list[TelegramMessage] = field(default_factory=list)

    async def notify(self, message: TelegramMessage) -> _FakeAttempt:
        if self.raise_on_notify:
            raise RuntimeError("transport failure")
        self.sent.append(message)
        return _FakeAttempt(delivered=self.delivered)


# ── Unit tests for the monitor ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_sends_telegram_when_bridge_configured() -> None:
    bridge = _RecordingBridge(delivered=True)
    monitor = ProviderAuthMonitor(bridge=bridge)
    alert = await monitor.notify_auth_expired("claude_pro", "401 from API")
    assert alert.delivered is True
    assert alert.cooldown_skipped is False
    assert len(bridge.sent) == 1
    msg = bridge.sent[0]
    assert msg.level == "warn"
    assert "claude_pro" in msg.text
    assert "claude /login" in msg.text  # canonical re-login command
    assert "401 from API" in msg.text


@pytest.mark.asyncio
async def test_notify_skips_when_bridge_is_null() -> None:
    monitor = ProviderAuthMonitor(bridge=NullTelegramBridge())
    alert = await monitor.notify_auth_expired("codex", "no session")
    assert alert.delivered is False
    assert alert.cooldown_skipped is False


@pytest.mark.asyncio
async def test_notify_swallows_bridge_exception() -> None:
    """Telegram transport failure must not crash the alert path."""
    bridge = _RecordingBridge(raise_on_notify=True)
    monitor = ProviderAuthMonitor(bridge=bridge)
    alert = await monitor.notify_auth_expired("gemini", "timeout")
    assert alert.delivered is False
    assert alert.cooldown_skipped is False


@pytest.mark.asyncio
async def test_cooldown_dedupes_repeated_alerts() -> None:
    """A second notify inside the cooldown window is dropped."""
    bridge = _RecordingBridge()
    monitor = ProviderAuthMonitor(
        bridge=bridge,
        cooldown=timedelta(minutes=5),
    )
    first = await monitor.notify_auth_expired("claude_pro", "first")
    second = await monitor.notify_auth_expired("claude_pro", "second")
    assert first.cooldown_skipped is False
    assert first.delivered is True
    assert second.cooldown_skipped is True
    assert second.delivered is False
    assert len(bridge.sent) == 1  # only first delivered


@pytest.mark.asyncio
async def test_cooldown_is_per_provider() -> None:
    """A different provider isn't blocked by another's cooldown."""
    bridge = _RecordingBridge()
    monitor = ProviderAuthMonitor(
        bridge=bridge, cooldown=timedelta(minutes=5)
    )
    await monitor.notify_auth_expired("claude_pro", "x")
    second = await monitor.notify_auth_expired("codex", "y")
    assert second.cooldown_skipped is False
    assert len(bridge.sent) == 2


@pytest.mark.asyncio
async def test_cooldown_resets_after_window() -> None:
    """Once the window passes, a fresh alert goes through."""
    bridge = _RecordingBridge()
    monitor = ProviderAuthMonitor(
        bridge=bridge, cooldown=timedelta(seconds=0)
    )
    await monitor.notify_auth_expired("opencode", "first")
    second = await monitor.notify_auth_expired("opencode", "second")
    assert second.cooldown_skipped is False
    assert second.delivered is True
    assert len(bridge.sent) == 2


@pytest.mark.asyncio
async def test_history_tracks_all_calls() -> None:
    bridge = _RecordingBridge()
    monitor = ProviderAuthMonitor(
        bridge=bridge, cooldown=timedelta(minutes=10)
    )
    await monitor.notify_auth_expired("claude_pro", "1")
    await monitor.notify_auth_expired("claude_pro", "2")  # cooldown
    await monitor.notify_auth_expired("codex", "3")
    history = monitor.history()
    assert len(history) == 3
    assert [h.provider for h in history] == [
        "claude_pro",
        "claude_pro",
        "codex",
    ]
    assert history[1].cooldown_skipped is True


def test_format_alert_includes_login_command_for_each_provider() -> None:
    """Every canonical provider has a documented re-login command."""
    for provider, cmd in CLI_LOGIN_COMMANDS.items():
        text = _format_alert(provider, "test")
        assert provider in text
        assert cmd in text


def test_format_alert_falls_back_for_unknown_provider() -> None:
    text = _format_alert("future_cli", "test")
    assert "future_cli login" in text


def test_format_alert_uses_plain_text_no_html_tags() -> None:
    """Audit-god MEDIUM #4 regression: the PTB bridge HTML-escapes the
    message body, so embedded ``<b>`` / ``<code>`` tags would render
    as literal ``&lt;b&gt;`` in the operator's chat. Verify the
    formatter sticks to plain text + indentation."""
    text = _format_alert("claude_pro", "401 from API")
    assert "<b>" not in text
    assert "<code>" not in text
    assert "</" not in text
    # Plain text content is still present.
    assert "Auth expired" in text
    assert "claude /login" in text


# ── Endpoint integration tests ────────────────────────────────────────────


@pytest.fixture
def _client_and_bridge() -> tuple[TestClient, _RecordingBridge]:
    bridge = _RecordingBridge()
    monitor = ProviderAuthMonitor(
        bridge=bridge, cooldown=timedelta(seconds=0)
    )
    registry = ProviderRegistry()
    app = FastAPI()
    app.include_router(
        # ``creds_detector=dict`` (empty map) keeps these registry-focused
        # tests hermetic — no real keychain subprocess / ~/.codex reads —
        # so list_providers falls back to the in-memory record status.
        build_provider_router(
            registry=registry, auth_monitor=monitor, creds_detector=dict
        ),
    )
    return TestClient(app), bridge


def test_auth_expired_endpoint_sends_alert(
    _client_and_bridge: tuple[TestClient, _RecordingBridge],
) -> None:
    client, bridge = _client_and_bridge
    r = client.post(
        "/api/providers/claude_pro/auth-expired",
        json={"reason": "401 unauthorized"},
    )
    assert r.status_code == 202
    body = r.json()
    assert body["provider"] == "claude_pro"
    assert body["delivered"] is True
    assert body["cooldown_skipped"] is False
    assert len(bridge.sent) == 1
    assert "401 unauthorized" in bridge.sent[0].text


def test_auth_expired_endpoint_accepts_empty_body(
    _client_and_bridge: tuple[TestClient, _RecordingBridge],
) -> None:
    """Missing body uses the default ``reason='auth expired'``."""
    client, _bridge = _client_and_bridge
    r = client.post(
        "/api/providers/codex/auth-expired",
        json={},
    )
    assert r.status_code == 202


def test_auth_expired_endpoint_404_unknown_provider(
    _client_and_bridge: tuple[TestClient, _RecordingBridge],
) -> None:
    client, _bridge = _client_and_bridge
    r = client.post(
        "/api/providers/nope/auth-expired",
        json={"reason": "x"},
    )
    assert r.status_code == 404


def test_auth_expired_endpoint_flips_registry_last_error(
    _client_and_bridge: tuple[TestClient, _RecordingBridge],
) -> None:
    """Connections card reads ``last_error`` — must reflect the expiry."""
    client, _bridge = _client_and_bridge
    r = client.post(
        "/api/providers/gemini/auth-expired",
        json={"reason": "token revoked"},
    )
    assert r.status_code == 202
    listing = client.get("/api/providers")
    gemini = next(p for p in listing.json() if p["name"] == "gemini")
    assert (gemini["last_error"] or "").startswith("auth_expired:")


def test_auth_expired_endpoint_rejects_extra_fields(
    _client_and_bridge: tuple[TestClient, _RecordingBridge],
) -> None:
    """Pydantic strictness — operator must not silently pass extra fields."""
    client, _bridge = _client_and_bridge
    r = client.post(
        "/api/providers/claude_pro/auth-expired",
        json={"reason": "ok", "rogue": "field"},
    )
    assert r.status_code == 422
