"""Tests for :class:`MinimaxSnapper`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from selffork_orchestrator.snappers.minimax import MinimaxSnapper


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_returns_none_when_credentials_missing(tmp_path: Path) -> None:
    snapper = MinimaxSnapper(mmx_home=tmp_path)
    assert await snapper.snapshot() is None


@pytest.mark.anyio
async def test_returns_snapshot_when_credentials_present_http_unreachable(
    tmp_path: Path,
) -> None:
    """With creds but no network mock, HTTP probe fails → empty windows."""
    creds = tmp_path / "credentials.json"
    creds.write_text(
        json.dumps({"access_token": "fake", "refresh_token": "fake"}),
        encoding="utf-8",
    )
    # Use an httpx MockTransport that always errors so we don't hit the
    # real network from CI.
    import httpx

    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network unreachable", request=request)

    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        snapper = MinimaxSnapper(mmx_home=tmp_path, http_client=client)
        snap = await snapper.snapshot()
    assert snap is not None
    assert snap.cli_id == "minimax-cli"
    assert snap.windows == {}  # HTTP probe failed → auth_only path
    assert snap.context is None
    assert snap.source == "credentials-present"


@pytest.mark.anyio
async def test_returns_none_on_invalid_json(tmp_path: Path) -> None:
    creds = tmp_path / "credentials.json"
    creds.write_text("{not json", encoding="utf-8")
    snapper = MinimaxSnapper(mmx_home=tmp_path)
    assert await snapper.snapshot() is None


# ── HTTP probe (T16) ──────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_http_probe_populates_windows(tmp_path: Path) -> None:
    """Successful Minimax /v1/token_plan/remains probe → 5h+daily windows."""
    import httpx

    from selffork_shared.quota import WindowKind

    creds = tmp_path / "credentials.json"
    creds.write_text(
        json.dumps({"access_token": "ya29.fake", "refresh_token": "fake"}),
        encoding="utf-8",
    )

    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("authorization") == "Bearer ya29.fake"
        return httpx.Response(
            200,
            json={
                "rate_limit_5h": {"used_percent": 65.0, "resets_in_seconds": 1200},
                "rate_limit_daily": {"used_percent": 22.5, "resets_in_seconds": 7200},
            },
        )

    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        snapper = MinimaxSnapper(mmx_home=tmp_path, http_client=client)
        snap = await snapper.snapshot()

    assert snap is not None
    assert snap.windows[WindowKind.five_hour].used_pct == 65.0
    assert snap.windows[WindowKind.daily].used_pct == 22.5


@pytest.mark.anyio
async def test_http_probe_503_collapses_to_empty(tmp_path: Path) -> None:
    import httpx

    creds = tmp_path / "credentials.json"
    creds.write_text(
        json.dumps({"access_token": "ya29.fake"}),
        encoding="utf-8",
    )

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "service unavailable"})

    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        snapper = MinimaxSnapper(mmx_home=tmp_path, http_client=client)
        snap = await snapper.snapshot()

    assert snap is not None
    assert snap.windows == {}


@pytest.mark.anyio
async def test_falls_back_to_access_field_when_access_token_missing(
    tmp_path: Path,
) -> None:
    """OAuth library variations may use ``access`` instead of ``access_token``."""
    import httpx

    from selffork_shared.quota import WindowKind

    creds = tmp_path / "credentials.json"
    creds.write_text(
        json.dumps({"access": "ya29.alt"}),
        encoding="utf-8",
    )

    captured_token: dict[str, str] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured_token["auth"] = request.headers.get("authorization", "")
        return httpx.Response(
            200,
            json={
                "rate_limit_5h": {"used_percent": 1.0, "resets_in_seconds": 60},
            },
        )

    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        snapper = MinimaxSnapper(mmx_home=tmp_path, http_client=client)
        snap = await snapper.snapshot()

    assert captured_token["auth"] == "Bearer ya29.alt"
    assert snap is not None
    assert WindowKind.five_hour in snap.windows
