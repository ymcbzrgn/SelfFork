"""Dual-pool routing — PROJECT + GLOBAL memory havuzu primitive.

Per ADR-009:

- PROJECT pool: ``~/.selffork/projects/<slug>/mind/{notes.duckdb,vectors.lance}``
- GLOBAL pool: ``~/.selffork/global/mind/{notes.duckdb,vectors.lance}``

:class:`PoolResolver` opens one :class:`DuckDBMindStore` +
:class:`LanceDBVectorStore` pair per pool, dispatches a
:class:`~selffork_mind.store.base.PoolScope` to the right engine(s), and
merges cross-pool hits.

Concurrency: parallel queries via :func:`asyncio.gather`. Each engine is
single-writer + multi-reader; per-pool isolation means the GLOBAL pool's
writes never lock a PROJECT pool's reads (and vice versa). Filesystem-level
proje silmek (``rm -rf ~/.selffork/projects/<slug>``) global pool'u bozmaz.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from selffork_mind.graph.base import GraphTriple, SemanticGraphStore
from selffork_mind.graph.in_memory import InMemoryGraphStore
from selffork_mind.memory.model import Note
from selffork_mind.store.base import (
    GLOBAL_GROUP_ID,
    PoolScope,
    RetrievalHit,
    RetrieveConfig,
    StoreScope,
    project_group_id,
)
from selffork_mind.store.duckdb import DuckDBMindStore
from selffork_mind.store.lance import LanceDBVectorStore, VectorEntry, VectorHit

__all__ = [
    "PoolKind",
    "PoolPaths",
    "PoolResolver",
    "default_global_pool_root",
    "default_project_pool_root",
    "default_selffork_home",
]


PoolKind = Literal["project", "global"]


def default_selffork_home() -> Path:
    """Resolve the SelfFork data root.

    Order:

    1. ``SELFFORK_HOME`` environment variable.
    2. ``~/.selffork``.

    Mirrors the convention used by orchestrator's ``projects/store.py`` and
    heartbeat audit paths so the same root works across all subsystems.
    """
    env = os.environ.get("SELFFORK_HOME")
    if env:
        return Path(env).expanduser().resolve()
    return Path.home() / ".selffork"


def default_project_pool_root(project_slug: str, *, home: Path | None = None) -> Path:
    """Per-project mind directory — ADR-009 §2.

    ``~/.selffork/projects/<slug>/mind/``
    """
    if not project_slug:
        raise ValueError("project_slug cannot be empty")
    root = home or default_selffork_home()
    return root / "projects" / project_slug / "mind"


def default_global_pool_root(*, home: Path | None = None) -> Path:
    """Cross-project global mind directory — ADR-009 §2.

    ``~/.selffork/global/mind/``
    """
    root = home or default_selffork_home()
    return root / "global" / "mind"


@dataclass(frozen=True, slots=True)
class PoolPaths:
    """Resolved filesystem paths for a single pool — ADR-009 §2.

    ``notes_db`` is the DuckDB file path. ``vectors_dir`` is the LanceDB
    table directory (LanceDB requires a directory, not a file).
    """

    notes_db: Path
    vectors_dir: Path

    @classmethod
    def for_project(cls, project_slug: str, *, home: Path | None = None) -> PoolPaths:
        root = default_project_pool_root(project_slug, home=home)
        return cls(
            notes_db=root / "notes.duckdb",
            vectors_dir=root / "vectors.lance",
        )

    @classmethod
    def for_global(cls, *, home: Path | None = None) -> PoolPaths:
        root = default_global_pool_root(home=home)
        return cls(
            notes_db=root / "notes.duckdb",
            vectors_dir=root / "vectors.lance",
        )


@dataclass
class _PoolEngines:
    """Per-pool engine triple (DuckDB + LanceDB + Graph).

    ADR-009 §3 T3 Semantic Graph PROJECT + GLOBAL split — each pool
    carries its own graph store so triples never cross pool boundaries
    accidentally. The default factory is :class:`InMemoryGraphStore`
    (zero-config, Apache 2.0); operators swap to
    :class:`~selffork_mind.graph.kuzu.KuzuGraphStore` by passing a custom
    ``graph_store_factory`` to :class:`PoolResolver`.
    """

    notes: DuckDBMindStore
    vectors: LanceDBVectorStore
    graph: SemanticGraphStore
    group_id: str
    setup_done: bool = False


@dataclass
class PoolResolver:
    """Dual-pool query router (ADR-009 §6).

    The resolver is project-bound (a single project slug is attached on
    construction). Cross-pool queries set ``include_global=True`` on the
    :class:`PoolScope`; the resolver then dispatches in parallel and merges
    results sorted by score descending.

    Single-pool queries (``include_global=False``) hit only the PROJECT
    engine — backward-compatible with Order 1-3 behaviour.

    Global-only queries (``project_slug=None, include_global=True``) hit
    only the GLOBAL engine — used by identity recall and cross-project
    reflection workflows.

    ``graph_store_factory`` is the pluggable T3 backend hook (ADR-009 §3):
    it defaults to :class:`InMemoryGraphStore` and is called once per pool
    to build that pool's graph engine. Pass e.g.
    ``graph_store_factory=lambda: KuzuGraphStore(db_path=...)`` to swap the
    on-disk Kuzu backend in without touching any existing call site.
    """

    project_slug: str | None
    home: Path | None = None
    embedding_dim: int = 1024
    graph_store_factory: Callable[[], SemanticGraphStore] = InMemoryGraphStore
    _project: _PoolEngines | None = field(default=None, init=False, repr=False)
    _global: _PoolEngines | None = field(default=None, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    # ── lifecycle ──────────────────────────────────────────────────────

    async def setup(self) -> None:
        """Open engines on demand.

        We lazily open PROJECT and GLOBAL engines on first use so resolvers
        with ``include_global=False`` never pay LanceDB startup cost for
        the global pool.
        """
        async with self._lock:
            await self._ensure_project()
            await self._ensure_global()

    async def _ensure_project(self) -> _PoolEngines | None:
        if self.project_slug is None:
            return None
        if self._project is None:
            paths = PoolPaths.for_project(self.project_slug, home=self.home)
            self._project = _PoolEngines(
                notes=DuckDBMindStore(db_path=paths.notes_db),
                vectors=LanceDBVectorStore(
                    db_path=paths.vectors_dir,
                    embedding_dim=self.embedding_dim,
                ),
                graph=self.graph_store_factory(),
                group_id=project_group_id(self.project_slug),
            )
        if not self._project.setup_done:
            await self._project.notes.setup()
            await self._project.vectors.setup()
            await self._project.graph.setup()
            self._project.setup_done = True
        return self._project

    async def _ensure_global(self) -> _PoolEngines:
        if self._global is None:
            paths = PoolPaths.for_global(home=self.home)
            self._global = _PoolEngines(
                notes=DuckDBMindStore(db_path=paths.notes_db),
                vectors=LanceDBVectorStore(
                    db_path=paths.vectors_dir,
                    embedding_dim=self.embedding_dim,
                ),
                graph=self.graph_store_factory(),
                group_id=GLOBAL_GROUP_ID,
            )
        if not self._global.setup_done:
            await self._global.notes.setup()
            await self._global.vectors.setup()
            await self._global.graph.setup()
            self._global.setup_done = True
        return self._global

    async def teardown(self) -> None:
        async with self._lock:
            tasks: list[asyncio.Future[None]] = []
            engines = [e for e in (self._project, self._global) if e is not None]
            for engine in engines:
                if engine.setup_done:
                    tasks.append(asyncio.ensure_future(engine.notes.teardown()))
                    tasks.append(asyncio.ensure_future(engine.vectors.teardown()))
                    tasks.append(asyncio.ensure_future(engine.graph.teardown()))
            if tasks:
                await asyncio.gather(*tasks)
            for engine in engines:
                engine.setup_done = False

    # ── writes ─────────────────────────────────────────────────────────

    async def upsert_note(self, note: Note, *, pool: PoolKind) -> Note:
        """Write a note to one pool only — cross-pool writes are not allowed.

        Notes are *promoted* to the GLOBAL pool by explicit decision (Reflex
        consolidation, manual operator promotion), never by accidental
        cross-pool insert.
        """
        engines = await self._engines_for(pool)
        # Stamp the group_id field so the row's partition is unambiguous.
        stamped = note.model_copy(update={"group_id": engines.group_id})
        return await engines.notes.upsert_note(stamped)

    async def add_triple(self, triple: GraphTriple, *, pool: PoolKind) -> None:
        """Write a graph triple to one pool only (ADR-009 §3 T3 split).

        The triple's ``group_id`` field is stamped to the pool's literal so
        cross-pool consolidators can distinguish provenance even when
        triples flow through merge buffers.
        """
        engines = await self._engines_for(pool)
        stamped = GraphTriple(
            subject=triple.subject,
            predicate=triple.predicate,
            obj=triple.obj,
            source_passage_id=triple.source_passage_id,
            project_slug=triple.project_slug,
            group_id=engines.group_id,
            confidence=triple.confidence,
            valid_from=triple.valid_from,
            valid_until=triple.valid_until,
        )
        await engines.graph.add_triple(stamped)

    async def list_triples(
        self,
        *,
        pool_scope: PoolScope,
        subject: str | None = None,
        predicate: str | None = None,
        object_: str | None = None,
        valid_at: datetime | None = None,
    ) -> list[GraphTriple]:
        """Cross-pool triple list — parallel queries + merge.

        Returns triples sorted by (subject, predicate, obj, source_passage_id)
        — same deterministic ordering as the in-memory store, applied across
        the merged result so callers see stable output regardless of which
        engine yielded a row.
        """
        group_ids = pool_scope.group_ids()
        if not group_ids:
            return []
        targets = await self._targets_for_group_ids(group_ids)
        if not targets:
            return []

        async def _one(engine: _PoolEngines) -> list[GraphTriple]:
            return await engine.graph.list_triples(
                subject=subject,
                predicate=predicate,
                object_=object_,
                valid_at=valid_at,
            )

        per_pool = await asyncio.gather(*(_one(e) for e in targets))
        merged: list[GraphTriple] = [t for pool in per_pool for t in pool]
        merged.sort(key=lambda t: (t.subject, t.predicate, t.obj, str(t.source_passage_id)))
        return merged

    async def upsert_vector(self, entry: VectorEntry, *, pool: PoolKind) -> None:
        """Write a vector to one pool only."""
        engines = await self._engines_for(pool)
        # Ensure the entry carries the pool's group_id (mirrors the notes write).
        stamped = VectorEntry(
            note_id=entry.note_id,
            group_id=engines.group_id,
            project_slug=entry.project_slug,
            session_id=entry.session_id,
            tier=entry.tier,
            vector=entry.vector,
            content_hash=entry.content_hash,
            written_at=entry.written_at,
        )
        await engines.vectors.upsert_vector(stamped)

    # ── reads ──────────────────────────────────────────────────────────

    async def retrieve(
        self,
        *,
        pool_scope: PoolScope,
        config: RetrieveConfig,
    ) -> list[RetrievalHit]:
        """Cross-pool retrieve — parallel queries + merge by score.

        ``pool_scope.group_ids()`` is expanded; each group_id picks one engine.
        ``config.scope.group_id`` is overridden per engine so each query sees
        only its own pool's rows.

        Order of results: stable descending by score; in the case of a tie,
        PROJECT pool hits precede GLOBAL pool hits (operator's project work
        usually beats cross-project lessons for the same query).
        """
        group_ids = pool_scope.group_ids()
        if not group_ids:
            return []

        targets = await self._targets_for_group_ids(group_ids)
        if not targets:
            return []

        async def _one(engine: _PoolEngines) -> list[RetrievalHit]:
            scoped = RetrieveConfig(
                tiers=config.tiers,
                scope=StoreScope(
                    project_slug=config.scope.project_slug,
                    session_id=config.scope.session_id,
                    cli_agent=config.scope.cli_agent,
                    operator_id=config.scope.operator_id,
                    group_id=engine.group_id,
                ),
                filter=config.filter,
                tag_pairs=config.tag_pairs,
                tag_match_mode=config.tag_match_mode,
                query_embedding=config.query_embedding,
                top_k=config.top_k,
                rerank_overfetch=config.rerank_overfetch,
                valid_at=config.valid_at,
                include_invalid=config.include_invalid,
                file_path=config.file_path,
            )
            return await engine.notes.retrieve(scoped)

        per_pool = await asyncio.gather(*(_one(e) for e in targets))
        return _merge_hits(per_pool, top_k=config.top_k)

    async def query_vectors(
        self,
        query_vector: Sequence[float],
        *,
        pool_scope: PoolScope,
        top_k: int = 20,
        tier: str | None = None,
    ) -> list[VectorHit]:
        """Cross-pool vector ANN — parallel + merge by score descending."""
        group_ids = pool_scope.group_ids()
        if not group_ids:
            return []

        targets = await self._targets_for_group_ids(group_ids)
        if not targets:
            return []

        async def _one(engine: _PoolEngines) -> list[VectorHit]:
            return await engine.vectors.query(
                query_vector,
                group_ids=(engine.group_id,),
                top_k=top_k,
                tier=tier,  # type: ignore[arg-type]
            )

        per_pool = await asyncio.gather(*(_one(e) for e in targets))
        merged: list[VectorHit] = [hit for hits in per_pool for hit in hits]
        merged.sort(key=lambda h: h.score, reverse=True)
        return merged[:top_k]

    # ── helpers ────────────────────────────────────────────────────────

    async def _engines_for(self, pool: PoolKind) -> _PoolEngines:
        if pool == "project":
            engines = await self._ensure_project()
            if engines is None:
                raise RuntimeError(
                    "PoolResolver has no project_slug; cannot write to PROJECT pool.",
                )
            return engines
        if pool == "global":
            return await self._ensure_global()
        raise ValueError(f"Unknown pool kind: {pool!r}")

    async def _targets_for_group_ids(
        self,
        group_ids: tuple[str, ...],
    ) -> list[_PoolEngines]:
        targets: list[_PoolEngines] = []
        wants_global = GLOBAL_GROUP_ID in group_ids
        wants_project = any(gid.startswith("p:") for gid in group_ids)
        if wants_project:
            project = await self._ensure_project()
            if project is not None:
                targets.append(project)
        if wants_global:
            targets.append(await self._ensure_global())
        return targets


def _merge_hits(
    per_pool: Sequence[list[RetrievalHit]],
    *,
    top_k: int,
) -> list[RetrievalHit]:
    """Merge per-pool hits into one ranked list.

    Strategy: descending by score; PROJECT pool first on score ties (the
    operator's project work usually beats cross-project lessons for the
    same exact query). Stable so individual pool ordering is preserved
    within a single tier.
    """
    flat: list[tuple[int, RetrievalHit]] = []
    for pool_idx, hits in enumerate(per_pool):
        for hit in hits:
            flat.append((pool_idx, hit))
    flat.sort(key=lambda pair: (-pair[1].score, pair[0]))
    return [hit for _, hit in flat[:top_k]]
