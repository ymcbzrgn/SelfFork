"""Tests for :class:`ZaiSnapper`."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from selffork_orchestrator.snappers.zai import (
    ZaiSnapper,
    default_opencode_auth_path,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _write_auth(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.anyio
async def test_returns_none_when_auth_missing(tmp_path: Path) -> None:
    snapper = ZaiSnapper(opencode_auth_path=tmp_path / "auth.json")
    assert await snapper.snapshot() is None


@pytest.mark.anyio
async def test_returns_none_on_invalid_json(tmp_path: Path) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text("{not json", encoding="utf-8")
    snapper = ZaiSnapper(opencode_auth_path=auth)
    assert await snapper.snapshot() is None


@pytest.mark.anyio
async def test_returns_none_when_zai_provider_missing(tmp_path: Path) -> None:
    auth = tmp_path / "auth.json"
    _write_auth(
        auth,
        {"providers": {"chatgpt": {"type": "oauth", "access": "x"}}},
    )
    snapper = ZaiSnapper(opencode_auth_path=auth)
    assert await snapper.snapshot() is None


@pytest.mark.anyio
async def test_returns_none_when_zai_uses_api_key(tmp_path: Path) -> None:
    """Auth-only kuralı: API-key path REJECTED."""
    auth = tmp_path / "auth.json"
    _write_auth(
        auth,
        {"providers": {"zai": {"type": "api", "key": "sk-..."}}},
    )
    snapper = ZaiSnapper(opencode_auth_path=auth)
    assert await snapper.snapshot() is None


@pytest.mark.anyio
async def test_returns_none_when_access_token_empty(tmp_path: Path) -> None:
    auth = tmp_path / "auth.json"
    _write_auth(
        auth,
        {"providers": {"zai": {"type": "oauth", "access": ""}}},
    )
    snapper = ZaiSnapper(opencode_auth_path=auth)
    assert await snapper.snapshot() is None


@pytest.mark.anyio
async def test_returns_snapshot_when_oauth_present(tmp_path: Path) -> None:
    auth = tmp_path / "auth.json"
    _write_auth(
        auth,
        {
            "providers": {
                "zai": {"type": "oauth", "access": "ya29.fake", "refresh": "fake"},
                "chatgpt": {"type": "oauth", "access": "fake"},
            },
        },
    )
    snapper = ZaiSnapper(opencode_auth_path=auth)
    snap = await snapper.snapshot()
    assert snap is not None
    assert snap.cli_id == "zai"
    assert snap.windows == {}  # full /v1/usage probe deferred
    assert snap.context is None
    assert snap.source == "opencode-auth-zai"


@pytest.mark.anyio
async def test_returns_none_when_root_is_not_object(tmp_path: Path) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    snapper = ZaiSnapper(opencode_auth_path=auth)
    assert await snapper.snapshot() is None


@pytest.mark.anyio
async def test_returns_none_when_providers_not_dict(tmp_path: Path) -> None:
    auth = tmp_path / "auth.json"
    _write_auth(auth, {"providers": ["zai"]})
    snapper = ZaiSnapper(opencode_auth_path=auth)
    assert await snapper.snapshot() is None


def test_default_opencode_auth_path_returns_a_path() -> None:
    path = default_opencode_auth_path()
    assert path.name == "auth.json"
    assert "opencode" in str(path)


# ── HTTP probe (T15) ──────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_http_probe_populates_windows(tmp_path: Path) -> None:
    """Successful Z.AI /v1/usage probe → populated 5h + daily windows."""
    import httpx
    from selffork_shared.quota import WindowKind

    auth = tmp_path / "auth.json"
    _write_auth(
        auth,
        {"providers": {"zai": {"type": "oauth", "access": "ya29.fake"}}},
    )

    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("authorization") == "Bearer ya29.fake"
        return httpx.Response(
            200,
            json={
                "rate_limit_5h": {"used_percent": 42.0, "resets_in_seconds": 3600},
                "rate_limit_daily": {"used_percent": 18.5, "resets_in_seconds": 7200},
            },
        )

    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        snapper = ZaiSnapper(opencode_auth_path=auth, http_client=client)
        snap = await snapper.snapshot()

    assert snap is not None
    assert snap.windows[WindowKind.five_hour].used_pct == 42.0
    assert snap.windows[WindowKind.daily].used_pct == 18.5


@pytest.mark.anyio
async def test_http_probe_failure_collapses_to_empty_windows(tmp_path: Path) -> None:
    """Network/HTTP failure → snapshot still emitted (auth_only)."""
    import httpx

    auth = tmp_path / "auth.json"
    _write_auth(
        auth,
        {"providers": {"zai": {"type": "oauth", "access": "ya29.fake"}}},
    )

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "service unavailable"})

    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        snapper = ZaiSnapper(opencode_auth_path=auth, http_client=client)
        snap = await snapper.snapshot()

    assert snap is not None
    assert snap.windows == {}
    assert snap.source == "opencode-auth-zai"


@pytest.mark.anyio
async def test_http_probe_skips_malformed_window_entries(tmp_path: Path) -> None:
    """Schema drift in one window doesn't disable the other."""
    import httpx
    from selffork_shared.quota import WindowKind

    auth = tmp_path / "auth.json"
    _write_auth(
        auth,
        {"providers": {"zai": {"type": "oauth", "access": "ya29.fake"}}},
    )

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "rate_limit_5h": {"used_percent": "not-a-number"},
                "rate_limit_daily": {"used_percent": 25.0, "resets_in_seconds": 3600},
            },
        )

    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        snapper = ZaiSnapper(opencode_auth_path=auth, http_client=client)
        snap = await snapper.snapshot()

    assert snap is not None
    assert WindowKind.five_hour not in snap.windows
    assert snap.windows[WindowKind.daily].used_pct == 25.0
