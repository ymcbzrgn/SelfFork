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
async def test_returns_snapshot_when_credentials_present(tmp_path: Path) -> None:
    creds = tmp_path / "credentials.json"
    creds.write_text(
        json.dumps({"access_token": "fake", "refresh_token": "fake"}),
        encoding="utf-8",
    )
    snapper = MinimaxSnapper(mmx_home=tmp_path)
    snap = await snapper.snapshot()
    assert snap is not None
    assert snap.cli_id == "minimax-cli"
    assert snap.windows == {}  # full quota probe is deferred to follow-up patch
    assert snap.context is None
    assert snap.source == "credentials-present"


@pytest.mark.anyio
async def test_returns_none_on_invalid_json(tmp_path: Path) -> None:
    creds = tmp_path / "credentials.json"
    creds.write_text("{not json", encoding="utf-8")
    snapper = MinimaxSnapper(mmx_home=tmp_path)
    assert await snapper.snapshot() is None
