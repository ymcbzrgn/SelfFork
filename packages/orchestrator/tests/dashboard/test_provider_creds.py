"""On-disk CLI credential detection (B1 — Connections auth auto-detect).

Every test points the detector at a ``tmp_path`` home + a fake keychain
probe so it never reads the developer's real ~/.codex / keychain.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from selffork_orchestrator.dashboard.provider_creds import (
    ProviderAuthStatus,
    detect_all,
)


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _never(_service: str, _account: str) -> bool:
    return False


def _always(_service: str, _account: str) -> bool:
    return True


def _detect(
    home: Path,
    *,
    keychain: bool = False,
) -> dict[str, ProviderAuthStatus]:
    return detect_all(
        home=home,
        user="tester",
        keychain_probe=_always if keychain else _never,
    )


# ── codex ────────────────────────────────────────────────────────────


def test_codex_connected_via_tokens(tmp_path: Path) -> None:
    _write(tmp_path / ".codex" / "auth.json", {"tokens": {"access": "x"}})
    assert _detect(tmp_path)["codex"].status == "connected"


def test_codex_connected_via_api_key(tmp_path: Path) -> None:
    _write(tmp_path / ".codex" / "auth.json", {"OPENAI_API_KEY": "sk-x"})
    assert _detect(tmp_path)["codex"].status == "connected"


def test_codex_disconnected_when_absent(tmp_path: Path) -> None:
    assert _detect(tmp_path)["codex"].status == "disconnected"


def test_codex_disconnected_when_malformed(tmp_path: Path) -> None:
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "auth.json").write_text("{not json", encoding="utf-8")
    assert _detect(tmp_path)["codex"].status == "disconnected"


def test_codex_disconnected_when_empty_creds(tmp_path: Path) -> None:
    _write(tmp_path / ".codex" / "auth.json", {"auth_mode": "chatgpt"})
    assert _detect(tmp_path)["codex"].status == "disconnected"


# ── gemini ───────────────────────────────────────────────────────────


def test_gemini_connected_future_expiry(tmp_path: Path) -> None:
    future = int((datetime.now(UTC) + timedelta(hours=1)).timestamp() * 1000)
    _write(
        tmp_path / ".gemini" / "oauth_creds.json",
        {"access_token": "a", "expiry_date": future},
    )
    status = _detect(tmp_path)["gemini"]
    assert status.status == "connected"
    assert status.expires_at is not None


def test_gemini_expired_past_expiry(tmp_path: Path) -> None:
    past = int((datetime.now(UTC) - timedelta(hours=1)).timestamp() * 1000)
    _write(
        tmp_path / ".gemini" / "oauth_creds.json",
        {"access_token": "a", "expiry_date": past},
    )
    status = _detect(tmp_path)["gemini"]
    assert status.status == "expired"
    assert status.expires_at is not None


def test_gemini_connected_without_expiry(tmp_path: Path) -> None:
    _write(tmp_path / ".gemini" / "oauth_creds.json", {"access_token": "a"})
    assert _detect(tmp_path)["gemini"].status == "connected"


def test_gemini_disconnected_without_access_token(tmp_path: Path) -> None:
    _write(tmp_path / ".gemini" / "oauth_creds.json", {"scope": "x"})
    assert _detect(tmp_path)["gemini"].status == "disconnected"


# ── opencode ─────────────────────────────────────────────────────────


def test_opencode_connected_local_share(tmp_path: Path) -> None:
    _write(
        tmp_path / ".local" / "share" / "opencode" / "auth.json",
        {"openai": {"token": "x"}, "zai": {"token": "y"}},
    )
    assert _detect(tmp_path)["opencode"].status == "connected"


def test_opencode_connected_config_fallback(tmp_path: Path) -> None:
    _write(
        tmp_path / ".config" / "opencode" / "auth.json",
        {"google": {"token": "x"}},
    )
    assert _detect(tmp_path)["opencode"].status == "connected"


def test_opencode_disconnected_empty_map(tmp_path: Path) -> None:
    _write(tmp_path / ".local" / "share" / "opencode" / "auth.json", {})
    assert _detect(tmp_path)["opencode"].status == "disconnected"


def test_opencode_disconnected_when_absent(tmp_path: Path) -> None:
    assert _detect(tmp_path)["opencode"].status == "disconnected"


# ── claude_pro ───────────────────────────────────────────────────────


def test_claude_pro_connected_via_keychain(tmp_path: Path) -> None:
    status = _detect(tmp_path, keychain=True)["claude_pro"]
    assert status.status == "connected"
    assert status.detail == "keychain"


def test_claude_pro_connected_via_linux_credentials(tmp_path: Path) -> None:
    _write(tmp_path / ".claude" / ".credentials.json", {"accessToken": "x"})
    # Keychain miss (non-darwin / not found) → file fallback.
    status = _detect(tmp_path, keychain=False)["claude_pro"]
    assert status.status == "connected"


def test_claude_pro_disconnected(tmp_path: Path) -> None:
    assert _detect(tmp_path, keychain=False)["claude_pro"].status == "disconnected"


# ── mmx + detect_all shape ───────────────────────────────────────────


def test_mmx_connected_when_config_present(tmp_path: Path) -> None:
    _write(tmp_path / ".mmx" / "config.json", {"apiKey": "x"})
    assert _detect(tmp_path)["mmx"].status == "connected"


def test_mmx_disconnected_when_absent(tmp_path: Path) -> None:
    assert _detect(tmp_path)["mmx"].status == "disconnected"


def test_detect_all_returns_every_provider(tmp_path: Path) -> None:
    result = _detect(tmp_path)
    assert set(result) == {"claude_pro", "codex", "gemini", "opencode", "mmx"}
    # Empty home → everything disconnected (no false positives).
    assert all(s.status == "disconnected" for s in result.values())
