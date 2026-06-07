"""Secondary-source coordinator: ProactiveUsageReader → CodexBar fallback.

ADR-007 §4 S-Quota / `[[codexbar-adoption-2026-05-22]]` — SelfFork's
file-tail snappers stay as the **primary** low-latency quota source.
When a snapshot is missing or stale (the canonical Gemini case: OTel
telemetry off → :class:`GeminiSnapper` never writes a snapshot),
this reader transparently falls back to the running ``codexbar
serve`` sidecar.

The sync :class:`ProactiveUsageReader` is intentionally untouched —
the Jr autopilot's ``quota_snapshot`` tool runs in a sync context
and must not pay for an HTTP round-trip. The async surface here is
the one Dashboard endpoints (``GET /api/usage/...``) call.

Design notes:

* **Composition over inheritance.** We wrap a ``ProactiveUsageReader``
  instead of subclassing it; tests inject canned readers + canned
  snappers without touching the file-tail path.
* **Per-CLI snapper factory.** A factory closure produces one
  :class:`CodexBarSnapper` per call so the underlying ``httpx``
  client stays scoped (no shared connection-pool surprises across
  concurrent dashboard requests).
* **Gemini "primary CodexBar" rule.** Reflected naturally:
  ``GeminiSnapper`` returns ``None`` when telemetry is off, so the
  primary path returns ``None`` and we fall through to CodexBar.
  No special-case branching needed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from selffork_orchestrator.snappers.codexbar import (
    _SELFFORK_TO_CODEXBAR,
    CodexBarSnapper,
)
from selffork_orchestrator.usage.proactive import ProactiveUsageReader
from selffork_shared.quota import QuotaSnapshot

__all__ = [
    "DEFAULT_CODEXBAR_CLI_IDS",
    "CodexBarFallbackReader",
    "build_codexbar_fallback_reader",
]

_log = logging.getLogger(__name__)


DEFAULT_CODEXBAR_CLI_IDS: Final[frozenset[str]] = frozenset(_SELFFORK_TO_CODEXBAR.keys())
"""SelfFork ``cli_id``s that have a CodexBar provider mapping.

Derived from :data:`selffork_orchestrator.snappers.codexbar._SELFFORK_TO_CODEXBAR`
so the two stay in lockstep. Anything not in this set short-circuits
to ``None`` rather than spinning up an HTTP client for a provider
CodexBar doesn't know about.
"""


SnapperFactory = Callable[[str], CodexBarSnapper]
"""Build a :class:`CodexBarSnapper` for one SelfFork ``cli_id``.

The default factory ties the snapper to a known ``base_url``; tests
substitute a factory that returns an instance backed by an
``httpx.MockTransport``.
"""


@dataclass(frozen=True, slots=True)
class _CodexBarFallbackConfig:
    """Frozen config holder kept private to discourage external instancing."""

    base_url: str | None
    cli_ids: frozenset[str]


class CodexBarFallbackReader:
    """Async reader: primary (snapper file) → secondary (CodexBar).

    Args:
        primary: Existing sync :class:`ProactiveUsageReader`. Reused
            as the file-tail source; never mutated.
        snapper_factory: Builds a :class:`CodexBarSnapper` for a given
            SelfFork ``cli_id``. When ``None``, the reader behaves as
            a pass-through to ``primary`` (CodexBar disabled).
        cli_ids: Set of SelfFork ``cli_id``s to attempt the CodexBar
            fallback for. Defaults to :data:`DEFAULT_CODEXBAR_CLI_IDS`.
    """

    def __init__(
        self,
        *,
        primary: ProactiveUsageReader,
        snapper_factory: SnapperFactory | None = None,
        cli_ids: frozenset[str] | None = None,
    ) -> None:
        self._primary = primary
        self._snapper_factory = snapper_factory
        self._cli_ids = cli_ids if cli_ids is not None else DEFAULT_CODEXBAR_CLI_IDS

    @property
    def primary(self) -> ProactiveUsageReader:
        """Pass-through to the underlying sync reader (autopilot tool)."""
        return self._primary

    async def read(self, cli_id: str) -> QuotaSnapshot | None:
        """Resolve the freshest snapshot for ``cli_id``.

        Returns:
            * The primary file-tail snapshot when it exists and is fresh.
            * The CodexBar snapshot otherwise, when the sidecar is
              configured + the cli_id is mapped.
            * ``None`` when both sources have no usable data.

        ``CodexBarSnapper.aclose`` is always invoked — the snapper
        only lives for the duration of one call so tests stay
        deterministic and connection pools don't leak across
        concurrent dashboard requests.
        """
        primary_snap = self._primary.read(cli_id)
        if primary_snap is not None:
            return primary_snap
        if self._snapper_factory is None:
            return None
        if cli_id not in self._cli_ids:
            return None
        snapper = self._snapper_factory(cli_id)
        try:
            return await snapper.snapshot()
        except Exception:
            _log.warning(
                "codexbar_fallback_failed",
                extra={"cli_id": cli_id},
                exc_info=True,
            )
            return None
        finally:
            await snapper.aclose()

    async def read_all(self) -> dict[str, QuotaSnapshot]:
        """Return one snapshot per known CLI (primary union CodexBar).

        Primary keys come first; CodexBar fills in any cli_id from
        :attr:`cli_ids` that the primary layer missed. Snapshots are
        only returned when a real signal exists — never fabricated.
        """
        result = self._primary.read_all()
        if self._snapper_factory is None:
            return result
        missing = self._cli_ids.difference(result.keys())
        for cli_id in sorted(missing):
            snap = await self.read(cli_id)
            if snap is not None:
                result[cli_id] = snap
        return result


def build_codexbar_fallback_reader(
    *,
    primary: ProactiveUsageReader,
    codexbar_base_url: str | None,
    snapper_builder: Callable[[str, str], CodexBarSnapper] | None = None,
) -> CodexBarFallbackReader:
    """Wire the default fallback reader against a live sidecar.

    Args:
        primary: The dashboard's existing :class:`ProactiveUsageReader`.
        codexbar_base_url: Sidecar URL (``CodexBarServer.base_url``)
            or ``None`` to disable the fallback.
        snapper_builder: ``(cli_id, base_url) → CodexBarSnapper`` for
            advanced tests. Default uses the production constructor.

    Returns:
        A :class:`CodexBarFallbackReader` ready for dashboard wiring.
    """
    if codexbar_base_url is None:
        return CodexBarFallbackReader(primary=primary, snapper_factory=None)

    builder = snapper_builder or (
        lambda cli_id, base_url: CodexBarSnapper(cli_id=cli_id, base_url=base_url)
    )

    def factory(cli_id: str) -> CodexBarSnapper:
        return builder(cli_id, codexbar_base_url)

    return CodexBarFallbackReader(primary=primary, snapper_factory=factory)
