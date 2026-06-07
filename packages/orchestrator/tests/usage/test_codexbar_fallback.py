"""Tests for the CodexBar secondary-source coordinator (S-Quota Faz C)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

import httpx
import pytest

from selffork_orchestrator.snappers.codexbar import CodexBarSnapper
from selffork_orchestrator.usage.codexbar_fallback import (
    DEFAULT_CODEXBAR_CLI_IDS,
    CodexBarFallbackReader,
    build_codexbar_fallback_reader,
)
from selffork_orchestrator.usage.proactive import (
    ProactiveUsageReader,
    ProactiveUsageReaderConfig,
)
from selffork_shared.quota import (
    QuotaSnapshot,
    WindowKind,
    WindowState,
)

_PRIMARY_SOURCE: Final[str] = "selffork-snapper"
_CODEXBAR_SOURCE: Final[str] = "codexbar:test-transport"


def _make_snapshot(
    *,
    cli_id: str,
    source: str = _PRIMARY_SOURCE,
    used_pct: float = 12.5,
) -> QuotaSnapshot:
    now = datetime.now(tz=UTC)
    return QuotaSnapshot(
        cli_id=cli_id,
        windows={
            WindowKind.five_hour: WindowState(
                used_pct=used_pct,
                resets_at=now + timedelta(hours=5),
                window_seconds=5 * 3600,
            )
        },
        context=None,
        captured_at=now,
        source=source,
    )


def _write_primary_snapshot(state_dir: Path, snapshot: QuotaSnapshot) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / f"{snapshot.cli_id}.json"
    path.write_text(snapshot.model_dump_json())


def _build_primary(state_dir: Path) -> ProactiveUsageReader:
    return ProactiveUsageReader(config=ProactiveUsageReaderConfig(state_dir=state_dir))


def _codexbar_handler(
    *,
    provider: str,
    used_pct: float = 47.0,
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = {
            "provider": provider,
            "version": "0.6.0",
            "source": "test-transport",
            "usage": {
                "primary": {
                    "usedPercent": used_pct,
                    "windowMinutes": 300,
                    "resetsAt": "2099-12-04T19:15:00Z",
                },
                "secondary": None,
                "tertiary": None,
                "updatedAt": "2099-12-04T18:10:22Z",
            },
        }
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


def _build_codexbar_factory(transport: httpx.MockTransport):
    def factory(cli_id: str) -> CodexBarSnapper:
        client = httpx.AsyncClient(transport=transport)
        return CodexBarSnapper(
            cli_id=cli_id,
            base_url="http://test.invalid",
            client=client,
        )

    return factory


# ── primary path ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_primary_wins_when_fresh(tmp_path: Path) -> None:
    primary = _build_primary(tmp_path)
    primary_snap = _make_snapshot(cli_id="claude-code")
    _write_primary_snapshot(tmp_path, primary_snap)

    transport = _codexbar_handler(provider="claude", used_pct=99.0)
    reader = CodexBarFallbackReader(
        primary=primary,
        snapper_factory=_build_codexbar_factory(transport),
    )
    snap = await reader.read("claude-code")
    assert snap is not None
    assert snap.source == _PRIMARY_SOURCE


# ── fallback path ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_falls_back_to_codexbar_when_primary_missing(
    tmp_path: Path,
) -> None:
    # No primary file for gemini-cli on disk.
    primary = _build_primary(tmp_path)
    transport = _codexbar_handler(provider="gemini", used_pct=68.0)
    reader = CodexBarFallbackReader(
        primary=primary,
        snapper_factory=_build_codexbar_factory(transport),
    )
    snap = await reader.read("gemini-cli")
    assert snap is not None
    assert snap.source.startswith("codexbar:")
    assert snap.windows[WindowKind.five_hour].used_pct == 68.0


@pytest.mark.asyncio
async def test_returns_none_when_both_sources_empty(
    tmp_path: Path,
) -> None:
    primary = _build_primary(tmp_path)

    def transport(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="bridge down")

    reader = CodexBarFallbackReader(
        primary=primary,
        snapper_factory=_build_codexbar_factory(httpx.MockTransport(transport)),
    )
    assert await reader.read("claude-code") is None


@pytest.mark.asyncio
async def test_codexbar_skipped_for_unsupported_cli(tmp_path: Path) -> None:
    """A cli_id outside :data:`DEFAULT_CODEXBAR_CLI_IDS` must not spin
    up an HTTP client — returns None immediately."""
    primary = _build_primary(tmp_path)
    transport = httpx.MockTransport(
        lambda req: pytest.fail("should not call CodexBar"),
    )
    reader = CodexBarFallbackReader(
        primary=primary,
        snapper_factory=_build_codexbar_factory(transport),
        cli_ids=frozenset({"claude-code"}),  # restrict
    )
    assert await reader.read("some-future-cli") is None


@pytest.mark.asyncio
async def test_pass_through_when_no_factory(tmp_path: Path) -> None:
    """No snapper_factory ⇒ reader is identical to bare ProactiveUsageReader."""
    primary = _build_primary(tmp_path)
    primary_snap = _make_snapshot(cli_id="codex")
    _write_primary_snapshot(tmp_path, primary_snap)

    reader = CodexBarFallbackReader(primary=primary, snapper_factory=None)
    snap = await reader.read("codex")
    assert snap is not None and snap.cli_id == "codex"
    assert await reader.read("gemini-cli") is None


# ── read_all ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_read_all_union_of_sources(tmp_path: Path) -> None:
    """Primary covers what it has; CodexBar fills any cli_id it misses."""
    primary = _build_primary(tmp_path)
    _write_primary_snapshot(tmp_path, _make_snapshot(cli_id="claude-code"))
    _write_primary_snapshot(tmp_path, _make_snapshot(cli_id="codex"))

    # CodexBar covers everything in its map; the union picks up
    # gemini-cli + minimax-cli + zai + opencode (primary doesn't have
    # them).
    transport = _codexbar_handler(provider="gemini")

    visited: list[str] = []

    def factory(cli_id: str) -> CodexBarSnapper:
        visited.append(cli_id)
        # The mock transport responds with the same provider regardless
        # of the query param; the snapper still maps cli_id correctly.
        client = httpx.AsyncClient(transport=transport)
        return CodexBarSnapper(
            cli_id=cli_id,
            base_url="http://test.invalid",
            client=client,
        )

    reader = CodexBarFallbackReader(
        primary=primary,
        snapper_factory=factory,
    )
    all_snaps = await reader.read_all()
    # Primary keys preserved
    assert "claude-code" in all_snaps and "codex" in all_snaps
    # CodexBar never re-queried providers we already have
    assert "claude-code" not in visited
    assert "codex" not in visited


# ── builder ────────────────────────────────────────────────────────────


def test_builder_disables_when_url_missing(tmp_path: Path) -> None:
    primary = _build_primary(tmp_path)
    reader = build_codexbar_fallback_reader(primary=primary, codexbar_base_url=None)
    assert reader.primary is primary
    assert reader._snapper_factory is None  # type: ignore[attr-defined]


def test_builder_wires_default_factory(tmp_path: Path) -> None:
    primary = _build_primary(tmp_path)
    reader = build_codexbar_fallback_reader(
        primary=primary,
        codexbar_base_url="http://127.0.0.1:8766",
    )
    assert reader._snapper_factory is not None  # type: ignore[attr-defined]


def test_default_cli_ids_match_codexbar_map() -> None:
    # If we ever extend ``_SELFFORK_TO_CODEXBAR`` the fallback should
    # cover the new CLIs without a second-place wire change.
    assert "claude-code" in DEFAULT_CODEXBAR_CLI_IDS
    assert "gemini-cli" in DEFAULT_CODEXBAR_CLI_IDS
    assert "codex" in DEFAULT_CODEXBAR_CLI_IDS
