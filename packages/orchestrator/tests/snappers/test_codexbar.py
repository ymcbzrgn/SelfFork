"""Tests for the CodexBar snapper (S-Quota Faz A).

Pure unit tests: we mount an ``httpx.MockTransport`` so the snapper
never touches the network. Covers the happy path, the per-slot window
mapping matrix, transient failure handling, and the provider-id ↔
cli_id translation table.
"""

from __future__ import annotations

import json

import httpx
import pytest

from selffork_orchestrator.snappers.codexbar import (
    DEFAULT_SIDECAR_PORT,
    CodexBarSnapper,
    map_codexbar_payload,
)
from selffork_shared.quota import WindowKind


def _payload(
    *,
    provider: str = "claude",
    primary_used: float = 28.0,
    primary_minutes: int = 300,
    secondary_used: float | None = 59.0,
    secondary_minutes: int | None = 10080,
    tertiary: dict | None = None,
    updated_at: str = "2025-12-04T18:10:22Z",
) -> dict:
    """Return a deep-copied payload skeleton matching CodexBar's JSON."""
    secondary = (
        {
            "usedPercent": secondary_used,
            "windowMinutes": secondary_minutes,
            "resetsAt": "2025-12-05T17:00:00Z",
        }
        if secondary_used is not None and secondary_minutes is not None
        else None
    )
    return {
        "provider": provider,
        "version": "0.6.0",
        "source": "openai-web",
        "status": {
            "indicator": "none",
            "description": "Operational",
            "updatedAt": "2025-12-04T17:55:00Z",
            "url": "https://status.openai.com/",
        },
        "usage": {
            "primary": {
                "usedPercent": primary_used,
                "windowMinutes": primary_minutes,
                "resetsAt": "2025-12-04T19:15:00Z",
            },
            "secondary": secondary,
            "tertiary": tertiary,
            "updatedAt": updated_at,
            "identity": {
                "providerID": provider,
                "accountEmail": "user@example.com",
                "accountOrganization": None,
                "loginMethod": "plus",
            },
        },
    }


def _client_for(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ── map_codexbar_payload (pure mapper) ─────────────────────────────────


def test_mapper_translates_five_hour_and_seven_day() -> None:
    snap = map_codexbar_payload(_payload(), cli_id="claude-code")
    assert snap is not None
    assert snap.cli_id == "claude-code"
    assert snap.source.startswith("codexbar:")
    assert WindowKind.five_hour in snap.windows
    assert WindowKind.seven_day in snap.windows
    assert snap.windows[WindowKind.five_hour].used_pct == 28.0
    assert snap.windows[WindowKind.five_hour].window_seconds == 300 * 60
    assert snap.account_id == "user@example.com"


def test_mapper_rolls_back_to_generic_window_kind() -> None:
    snap = map_codexbar_payload(
        _payload(primary_minutes=42, secondary_used=None, secondary_minutes=None),
        cli_id="claude-code",
    )
    assert snap is not None
    assert WindowKind.rolling in snap.windows


def test_mapper_returns_none_for_missing_usage_block() -> None:
    assert map_codexbar_payload({"provider": "claude"}, cli_id="claude-code") is None


def test_mapper_returns_none_when_all_slots_drop() -> None:
    bad = _payload(
        primary_used=12.0,
        primary_minutes=-1,
        secondary_used=None,
        secondary_minutes=None,
    )
    assert map_codexbar_payload(bad, cli_id="claude-code") is None


def test_mapper_per_minute_and_daily() -> None:
    rpm = _payload(primary_minutes=1, secondary_used=None, secondary_minutes=None)
    out = map_codexbar_payload(rpm, cli_id="gemini-cli")
    assert out is not None and WindowKind.per_minute in out.windows

    daily = _payload(primary_minutes=1440, secondary_used=None, secondary_minutes=None)
    out2 = map_codexbar_payload(daily, cli_id="gemini-cli")
    assert out2 is not None and WindowKind.daily in out2.windows


def test_mapper_normalises_z_suffix_timestamps() -> None:
    snap = map_codexbar_payload(_payload(), cli_id="claude-code")
    assert snap is not None
    assert snap.windows[WindowKind.five_hour].resets_at.tzinfo is not None


# ── CodexBarSnapper (HTTP) ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_snapper_happy_path() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/usage"
        assert request.url.params["provider"] == "claude"
        return httpx.Response(200, json=_payload(provider="claude"))

    snapper = CodexBarSnapper(
        cli_id="claude-code",
        base_url="http://test.invalid",
        client=_client_for(handler),
    )
    snap = await snapper.snapshot()
    assert snap is not None
    assert snap.cli_id == "claude-code"
    assert WindowKind.five_hour in snap.windows
    await snapper.aclose()


@pytest.mark.asyncio
async def test_snapper_returns_none_on_connect_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sidecar down", request=request)

    snapper = CodexBarSnapper(
        cli_id="claude-code",
        base_url="http://test.invalid",
        client=_client_for(handler),
    )
    assert await snapper.snapshot() is None
    await snapper.aclose()


@pytest.mark.asyncio
async def test_snapper_returns_none_on_non_2xx() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="bridge down")

    snapper = CodexBarSnapper(
        cli_id="claude-code",
        base_url="http://test.invalid",
        client=_client_for(handler),
    )
    assert await snapper.snapshot() is None
    await snapper.aclose()


@pytest.mark.asyncio
async def test_snapper_returns_none_on_bad_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<<not json>>")

    snapper = CodexBarSnapper(
        cli_id="claude-code",
        base_url="http://test.invalid",
        client=_client_for(handler),
    )
    assert await snapper.snapshot() is None
    await snapper.aclose()


@pytest.mark.asyncio
async def test_snapper_handles_array_response() -> None:
    """``codexbar serve`` returns an array when the provider filter is
    missing or the operator enabled multiple providers. The snapper
    picks the one matching its mapped id."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = [
            _payload(provider="codex"),
            _payload(provider="claude"),
        ]
        return httpx.Response(200, content=json.dumps(body).encode("utf-8"))

    snapper = CodexBarSnapper(
        cli_id="claude-code",
        base_url="http://test.invalid",
        client=_client_for(handler),
    )
    snap = await snapper.snapshot()
    assert snap is not None and snap.cli_id == "claude-code"
    await snapper.aclose()


@pytest.mark.asyncio
async def test_snapper_translates_each_supported_cli_id() -> None:
    """Every SelfFork cli_id we claim to handle must map to a CodexBar id."""
    cases = [
        ("claude-code", "claude"),
        ("codex", "codex"),
        ("gemini-cli", "gemini"),
        ("minimax-cli", "minimax"),
        ("zai", "zai"),
        ("opencode", "opencode"),
    ]
    for selffork_id, codexbar_id in cases:
        seen_provider: list[str] = []

        def handler(
            request: httpx.Request,
            _expected: str = codexbar_id,
            _sink: list[str] = seen_provider,
        ) -> httpx.Response:
            # Defaults pin loop-scoped values so ruff B023 stays happy.
            _sink.append(request.url.params["provider"])
            return httpx.Response(
                200, json=_payload(provider=_expected)
            )

        snapper = CodexBarSnapper(
            cli_id=selffork_id,
            base_url="http://test.invalid",
            client=_client_for(handler),
        )
        snap = await snapper.snapshot()
        assert snap is not None
        assert snap.cli_id == selffork_id
        assert seen_provider == [codexbar_id]
        await snapper.aclose()


def test_default_port_is_distinct_from_dashboard() -> None:
    """The sidecar default port must not collide with the dashboard's 8765."""
    assert DEFAULT_SIDECAR_PORT == 8766


def test_unknown_cli_id_raises_value_error() -> None:
    with pytest.raises(ValueError, match="no CodexBar provider"):
        CodexBarSnapper(cli_id="some-future-cli")
