"""On-disk CLI credential detection for the Provider Auth surface.

The operator signs in to each CLI **natively** (``<cli> login`` in a
terminal — the S5 decision, [[cli-provider-routing]]); SelfFork's
dashboard never drives the OAuth flow. So "is this provider signed in?"
is answered by inspecting the credentials each CLI persists on disk,
NOT by a dashboard sign-in record (which stays empty) and NOT by audit
usage (which only shows providers that have already *run*).

Detected surfaces (the four canonical CLIs +
([[four-clis-dont-forget-opencode]]) + mmx for parity):

* ``claude_pro``  — claude-code. macOS Keychain item ``Claude
  Code-credentials`` (account = ``$USER``); Linux/fallback
  ``~/.claude/.credentials.json``.
* ``codex``       — ``~/.codex/auth.json`` (OAuth ``tokens`` or
  ``OPENAI_API_KEY``).
* ``gemini``      — ``~/.gemini/oauth_creds.json`` (``access_token`` +
  ``expiry_date`` ms-epoch → ``expired`` when past).
* ``opencode``    — ``~/.local/share/opencode/auth.json`` (or
  ``~/.config/opencode/auth.json``); a non-empty provider→creds map.
* ``mmx``         — ``~/.mmx/config.json`` (minimax CLI;
  [[minimax-cli-dropped-opencode-m2-7]]).

This module ONLY reports status (connected / disconnected / expired) +
an opaque ``detail`` (the path or ``"keychain"``); it NEVER returns token
values, so a ``ProviderView`` built from it leaks no secrets.
"""

from __future__ import annotations

import getpass
import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from selffork_shared.logging import get_logger

__all__ = [
    "KeychainProbe",
    "ProviderAuthStatus",
    "default_keychain_probe",
    "detect_all",
]

_log = get_logger(__name__)

AuthStatusValue = Literal["connected", "disconnected", "expired"]

# Timeout for the macOS ``security`` keychain probe — generous enough for
# a cold call, short enough to never stall a status poll.
_KEYCHAIN_TIMEOUT_SECONDS = 5.0
_CLAUDE_KEYCHAIN_SERVICE = "Claude Code-credentials"


@dataclass(frozen=True, slots=True)
class ProviderAuthStatus:
    """A provider's on-disk auth status (no secrets).

    ``detail`` is an opaque, non-sensitive hint (the creds path or
    ``"keychain"``) for diagnostics; ``expires_at`` is populated only
    when the creds carry an expiry (gemini today).
    """

    status: AuthStatusValue
    expires_at: datetime | None = None
    detail: str | None = None


# A keychain probe takes ``(service, account)`` and returns whether the
# item exists. Injectable so tests never touch the real keychain.
type KeychainProbe = Callable[[str, str], bool]


def default_keychain_probe(service: str, account: str) -> bool:
    """Return whether a macOS Keychain generic-password item exists.

    Non-darwin platforms always return ``False`` (the caller falls back
    to a file-based check). Any ``security`` failure → ``False`` (treat
    as not-signed-in rather than raising into a status poll).
    """
    if sys.platform != "darwin":
        return False
    try:
        result = subprocess.run(  # noqa: S603 — fixed argv, no shell
            [
                "/usr/bin/security",  # absolute path — no PATH hijack (S607)
                "find-generic-password",
                "-s",
                service,
                "-a",
                account,
            ],
            capture_output=True,
            timeout=_KEYCHAIN_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _load_json(path: Path) -> object | None:
    """Best-effort JSON load — missing/unreadable/malformed → ``None``."""
    try:
        with path.open("r", encoding="utf-8") as fp:
            data: object = json.load(fp)
    except (OSError, ValueError):
        return None
    return data


def _detect_claude_pro(
    home: Path, *, user: str, keychain_probe: KeychainProbe
) -> ProviderAuthStatus:
    if keychain_probe(_CLAUDE_KEYCHAIN_SERVICE, user):
        return ProviderAuthStatus("connected", detail="keychain")
    creds = home / ".claude" / ".credentials.json"
    if creds.is_file():
        return ProviderAuthStatus("connected", detail=str(creds))
    return ProviderAuthStatus("disconnected")


def _detect_codex(home: Path) -> ProviderAuthStatus:
    path = home / ".codex" / "auth.json"
    data = _load_json(path)
    if isinstance(data, dict) and (data.get("tokens") or data.get("OPENAI_API_KEY")):
        return ProviderAuthStatus("connected", detail=str(path))
    return ProviderAuthStatus("disconnected")


def _detect_gemini(home: Path) -> ProviderAuthStatus:
    path = home / ".gemini" / "oauth_creds.json"
    data = _load_json(path)
    if not isinstance(data, dict) or not data.get("access_token"):
        return ProviderAuthStatus("disconnected")
    expiry_ms = data.get("expiry_date")
    if isinstance(expiry_ms, int | float) and not isinstance(expiry_ms, bool):
        expires_at = datetime.fromtimestamp(expiry_ms / 1000, tz=UTC)
        status: AuthStatusValue = "expired" if expires_at < datetime.now(UTC) else "connected"
        return ProviderAuthStatus(status, expires_at=expires_at, detail=str(path))
    return ProviderAuthStatus("connected", detail=str(path))


def _detect_opencode(home: Path) -> ProviderAuthStatus:
    # opencode's auth.json is a provider→creds map; a non-empty map means
    # at least one routed provider (ChatGPT / Minimax / GLM / Zen) is
    # signed in. Two known locations across versions/platforms.
    for rel in (
        Path(".local") / "share" / "opencode" / "auth.json",
        Path(".config") / "opencode" / "auth.json",
    ):
        path = home / rel
        data = _load_json(path)
        if isinstance(data, dict) and data:
            return ProviderAuthStatus("connected", detail=str(path))
    return ProviderAuthStatus("disconnected")


def _detect_mmx(home: Path) -> ProviderAuthStatus:
    path = home / ".mmx" / "config.json"
    if path.is_file():
        return ProviderAuthStatus("connected", detail=str(path))
    return ProviderAuthStatus("disconnected")


def detect_all(
    *,
    home: Path | None = None,
    user: str | None = None,
    keychain_probe: KeychainProbe | None = None,
) -> dict[str, ProviderAuthStatus]:
    """Detect on-disk auth for every provider, keyed by ``ProviderName``.

    Pure + injectable (``home`` / ``user`` / ``keychain_probe``) so tests
    point it at a tmp home + a fake keychain. Every per-provider detector
    is defensive — a malformed/locked creds file degrades to
    ``disconnected`` rather than raising into the status endpoint.
    """
    resolved_home = home or Path.home()
    resolved_user = user or _current_user()
    probe = keychain_probe or default_keychain_probe
    return {
        "claude_pro": _detect_claude_pro(resolved_home, user=resolved_user, keychain_probe=probe),
        "codex": _detect_codex(resolved_home),
        "gemini": _detect_gemini(resolved_home),
        "opencode": _detect_opencode(resolved_home),
        "mmx": _detect_mmx(resolved_home),
    }


def _current_user() -> str:
    try:
        return getpass.getuser()
    except (OSError, KeyError):  # pragma: no cover — no passwd entry
        return ""
