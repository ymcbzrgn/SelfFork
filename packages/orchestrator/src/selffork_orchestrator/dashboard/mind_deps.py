"""Shared Mind helpers — Order 3.

The CLI (:mod:`selffork_orchestrator.cli_mind`) and the cockpit FastAPI
router (:mod:`selffork_orchestrator.dashboard.mind_router`) both need
to:

1. Resolve the per-project Mind root (``~/.selffork/projects/<slug>/mind``)
   or the orphan root from :class:`MindConfig.storage_root`.
2. Open a :class:`DuckDBMindStore` against ``<root>/notes.duckdb``.
3. Build the optional embedder + provenance recorder + projection.

Pulling those into one module avoids the dashboard re-implementing
the same path math (and risking divergence the next time the layout
moves) — both surfaces import from here.

Refactor — no functional change. ``cli_mind.py`` re-exports the
private aliases from this module so its existing tests still patch
the same symbols.
"""

from __future__ import annotations

from pathlib import Path

from selffork_mind.projections import (
    MarkdownProjection,
    MarkdownProjectionConfig,
)
from selffork_mind.projections.provenance import ProvenanceRecorder
from selffork_mind.rag.embedder import (
    EmbedderName,
    EmbeddingProvider,
    build_embedder,
)
from selffork_mind.store.duckdb import DuckDBMindStore
from selffork_shared.config import MindConfig

__all__ = [
    "build_embedder_or_none",
    "build_projection",
    "build_provenance",
    "open_store",
    "resolve_db_path",
    "resolve_mind_root",
]


def resolve_mind_root(
    *,
    config: MindConfig,
    project_slug: str | None,
) -> Path:
    """Per-project Mind dir if ``project_slug`` set, orphan root otherwise.

    Per-project: ``~/.selffork/projects/<slug>/mind/``.
    Orphan: :attr:`MindConfig.storage_root` (default ``~/.selffork/mind``).
    """
    if project_slug is not None:
        return Path("~/.selffork/projects").expanduser() / project_slug / "mind"
    return Path(config.storage_root).expanduser()


def resolve_db_path(*, root: Path) -> Path:
    """``<root>/notes.duckdb`` — the canonical store path."""
    return root / "notes.duckdb"


async def open_store(*, root: Path) -> DuckDBMindStore:
    """Open (and ``setup``) a DuckDB-backed store at ``<root>/notes.duckdb``.

    Caller owns lifecycle — use ``try / finally`` or an async context
    manager to ``await store.teardown()``.
    """
    db = resolve_db_path(root=root)
    db.parent.mkdir(parents=True, exist_ok=True)
    store = DuckDBMindStore(db_path=db)
    await store.setup()
    return store


def build_embedder_or_none(config: MindConfig) -> EmbeddingProvider | None:
    """``None`` when ``mind.embedder == 'none'`` — BM25-only retrieval mode."""
    if config.embedder == "none":
        return None
    name: EmbedderName = config.embedder
    return build_embedder(name)


def build_provenance(
    config: MindConfig,
    *,
    project_slug: str | None,
) -> ProvenanceRecorder | None:
    """Per-project provenance log, or the orphan default — None if disabled."""
    if not config.provenance_path:
        return None
    if project_slug is not None:
        log_path = (
            Path("~/.selffork/projects").expanduser() / project_slug / "mind" / "provenance.jsonl"
        )
    else:
        log_path = Path(config.provenance_path).expanduser()
    return ProvenanceRecorder(log_path=log_path)


def build_projection(
    config: MindConfig,
    *,
    project_slug: str | None,
) -> MarkdownProjection | None:
    """Plain-markdown projection — None if the operator opts out."""
    if not config.projection_root:
        return None
    if project_slug is not None:
        root = Path("~/.selffork/projects").expanduser() / project_slug / "mind" / "markdown"
    else:
        root = Path(config.projection_root).expanduser()
    return MarkdownProjection(MarkdownProjectionConfig(root=root))
