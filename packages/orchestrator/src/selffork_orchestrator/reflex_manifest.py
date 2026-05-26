"""Reflex adapter manifest — single source for canonical path + reader.

Pre-M7 this is consulted by ``selffork train --info`` (and future
Heartbeat ``adapter_age`` filters). The M7 QLoRA worker writes the
manifest after a successful adapter swap, and consumers immediately
reflect the new state.

S4 honesty pass (no-mock rule):
:func:`load_adapter_manifest` never raises on missing / unreadable /
malformed content — it returns an :class:`AdapterManifest` with
``trained=False`` and a human-readable ``message``. Callers prefer a
clean empty over a traceback because the empty state IS the truth
pre-M7.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

__all__ = [
    "ADAPTER_MANIFEST_PATH",
    "AdapterManifest",
    "load_adapter_manifest",
]


ADAPTER_MANIFEST_PATH = Path(
    "~/.selffork/reflex/adapters/current/manifest.json",
).expanduser()
"""Canonical adapter manifest location.

The M7 training worker writes here after a successful weight swap; all
consumers read it as the single source of truth for *which* adapter is
currently active. Pre-M7 the file does not exist and
:func:`load_adapter_manifest` returns ``AdapterManifest(trained=False)``
with a human-readable ``message`` explaining the empty state — no
synthesised placeholders.
"""


@dataclass(frozen=True, slots=True)
class AdapterManifest:
    """Honest view of the active adapter, or empty when none exists.

    ``trained=False`` means the manifest is missing, unreadable, or
    malformed; in that case all other fields stay ``None`` and
    :attr:`message` carries the human-readable cause. Consumers MUST
    check :attr:`trained` before relying on any other field.
    """

    trained: bool
    version: str | None = None
    trained_at: str | None = None
    age_days: int | None = None
    examples: int | None = None
    method: str | None = None
    message: str | None = None


def load_adapter_manifest(
    path: Path = ADAPTER_MANIFEST_PATH,
) -> AdapterManifest:
    """Read the canonical adapter manifest, or return an honest empty.

    Never raises on missing / malformed content — the caller (the CLI,
    a Heartbeat filter) prefers a clean ``trained=False`` over a
    traceback. Use :attr:`AdapterManifest.message` to surface the
    failure cause when needed.
    """
    if not path.is_file():
        return AdapterManifest(
            trained=False,
            message=(
                f"No adapter manifest at {path}. The M7 training "
                "worker writes one after the first successful "
                "fine-tune; pre-M7 this is expected."
            ),
        )
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return AdapterManifest(
            trained=False,
            message=f"manifest at {path} is unreadable: {exc}",
        )
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return AdapterManifest(
            trained=False,
            message=f"manifest at {path} is invalid JSON: {exc}",
        )
    if not isinstance(data, dict):
        return AdapterManifest(
            trained=False,
            message=f"manifest at {path} is not a JSON object",
        )
    trained_at = _str_or_none(data.get("trained_at"))
    return AdapterManifest(
        trained=True,
        version=_str_or_none(data.get("version")),
        trained_at=trained_at,
        age_days=_compute_age_days(trained_at),
        examples=_int_or_none(data.get("examples")),
        method=_str_or_none(data.get("method")),
    )


def _str_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _int_or_none(value: object) -> int | None:
    """Honest int extractor — bool rejected explicitly.

    Bool is a subclass of ``int`` in Python, so a manifest with
    ``"examples": true`` must NOT be coerced to ``examples=1``
    (audit-god MAJOR #1, former ``reflex_router._int_or_none``).
    Floats and string-encoded ints are also rejected — the M7 worker
    is the sole writer and should produce typed integers; anything
    else hints at corruption and should surface as an empty field
    rather than a permissive coercion.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _compute_age_days(trained_at: str | None) -> int | None:
    if not trained_at:
        return None
    try:
        ts = datetime.fromisoformat(trained_at)
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    delta = datetime.now(UTC) - ts
    return max(0, delta.days)
