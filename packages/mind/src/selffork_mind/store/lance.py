"""LanceDB vector store — high-scale T2 Episodic vector backend.

Per ADR-002 §2 + ADR-009 §1:

LanceDB (Apache 2.0) holds high-volume vector embeddings with built-in
time-travel and Arrow-native columnar layout. DuckDB
(:class:`~selffork_mind.store.duckdb.DuckDBMindStore`) holds the relational
metadata (notes table, tags, filter DSL evaluation). The two are companions:

- DuckDB: ``upsert_note`` / ``retrieve`` with filter + tag + bi-temporal + small-scale cosine.
- LanceDB: ``upsert_vector`` / ``query`` for large-scale vector ANN over T2 Episodic.

Cross-pool partitioning via :data:`GROUP_ID_COLUMN` mirrors ADR-009 §1
(Graphiti pattern). Both PROJECT and GLOBAL pools have their own LanceDB
table directory under
``~/.selffork/projects/<slug>/mind/vectors.lance/`` and
``~/.selffork/global/mind/vectors.lance/`` respectively — the LanceDBVectorStore
opens the directory belonging to one pool at a time;
:class:`~selffork_mind.store.pool.PoolResolver` decides which.

Concurrency model: LanceDB Python SDK exposes a sync API. We wrap all
DB calls in :func:`anyio.to_thread.run_sync` so the orchestrator's event
loop is never blocked.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import anyio

from selffork_mind.memory.model import TierName

__all__ = [
    "GROUP_ID_COLUMN",
    "LanceDBVectorStore",
    "VectorEntry",
    "VectorHit",
]


GROUP_ID_COLUMN: str = "group_id"
"""Dual-pool partition column name in LanceDB (ADR-009 §1)."""

_TABLE_NAME: str = "episodic_vectors"
_EMBEDDING_DIM_DEFAULT: int = 1024  # BGE-M3 default (ADR-002 §3).


@dataclass(frozen=True, slots=True)
class VectorEntry:
    """One row to insert into LanceDB.

    ``note_id`` is the FK back to the DuckDB ``notes`` table — vector + metadata
    join is done in :class:`~selffork_mind.store.pool.PoolResolver`.
    """

    note_id: UUID
    group_id: str
    project_slug: str | None
    session_id: str | None
    tier: TierName
    vector: tuple[float, ...]
    content_hash: str
    written_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class VectorHit:
    """One row returned from a vector ANN query."""

    note_id: UUID
    group_id: str
    score: float
    project_slug: str | None
    session_id: str | None
    tier: TierName


class LanceDBVectorStore:
    """File-backed LanceDB store scoped to a single pool directory.

    The pool resolver opens one instance per pool (PROJECT or GLOBAL); cross-pool
    queries are orchestrated above this layer by running queries in parallel and
    merging hits.
    """

    def __init__(
        self,
        *,
        db_path: Path,
        embedding_dim: int = _EMBEDDING_DIM_DEFAULT,
    ) -> None:
        if embedding_dim <= 0:
            raise ValueError(f"embedding_dim must be positive, got {embedding_dim}")
        self._db_path = db_path
        self._embedding_dim = embedding_dim
        self._lock = asyncio.Lock()
        self._db: object | None = None
        self._table: object | None = None

    @property
    def embedding_dim(self) -> int:
        return self._embedding_dim

    @property
    def db_path(self) -> Path:
        return self._db_path

    # ── lifecycle ──────────────────────────────────────────────────────

    async def setup(self) -> None:
        async with self._lock:
            if self._table is not None:
                return
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db = await anyio.to_thread.run_sync(self._connect_sync)
            self._table = await anyio.to_thread.run_sync(self._open_or_create_table_sync)

    def _connect_sync(self) -> object:
        import lancedb

        return lancedb.connect(str(self._db_path))

    def _open_or_create_table_sync(self) -> object:
        assert self._db is not None  # noqa: S101
        import pyarrow as pa

        # LanceDB 0.30+: list_tables() returns a paginated structure
        # ``[('tables', [name, ...]), ('page_token', None)]`` — flatten
        # the ``tables`` slot to a flat list of names. Treat any unexpected
        # shape as "no tables yet" to fall through to create.
        raw = self._db.list_tables()  # type: ignore[attr-defined]
        try:
            paginated = dict(raw)
        except (TypeError, ValueError):
            paginated = {}
        existing = paginated.get("tables") or []
        if _TABLE_NAME in existing:
            return self._db.open_table(_TABLE_NAME)  # type: ignore[attr-defined]
        schema = pa.schema(
            [
                pa.field("note_id", pa.string(), nullable=False),
                pa.field(GROUP_ID_COLUMN, pa.string(), nullable=False),
                pa.field("project_slug", pa.string(), nullable=True),
                pa.field("session_id", pa.string(), nullable=True),
                pa.field("tier", pa.string(), nullable=False),
                pa.field(
                    "vector",
                    pa.list_(pa.float32(), list_size=self._embedding_dim),
                    nullable=False,
                ),
                pa.field("content_hash", pa.string(), nullable=False),
                pa.field("written_at", pa.timestamp("us", tz="UTC"), nullable=False),
            ],
        )
        return self._db.create_table(_TABLE_NAME, schema=schema)  # type: ignore[attr-defined]

    async def teardown(self) -> None:
        async with self._lock:
            # LanceDB has no explicit close on the table; clearing the references
            # is enough — the underlying connection releases file handles on GC.
            self._table = None
            self._db = None

    # ── writes ─────────────────────────────────────────────────────────

    async def upsert_vector(self, entry: VectorEntry) -> None:
        await self.upsert_vectors([entry])

    async def upsert_vectors(self, entries: Sequence[VectorEntry]) -> None:
        if not entries:
            return
        rows = [self._entry_to_row(e) for e in entries]
        async with self._lock:
            self._require_open()
            await anyio.to_thread.run_sync(self._upsert_rows_sync, rows)

    def _entry_to_row(self, entry: VectorEntry) -> dict[str, object]:
        if len(entry.vector) != self._embedding_dim:
            raise ValueError(
                f"vector dim mismatch: got {len(entry.vector)}, "
                f"expected {self._embedding_dim}",
            )
        return {
            "note_id": str(entry.note_id),
            GROUP_ID_COLUMN: entry.group_id,
            "project_slug": entry.project_slug,
            "session_id": entry.session_id,
            "tier": entry.tier,
            "vector": list(entry.vector),
            "content_hash": entry.content_hash,
            "written_at": entry.written_at or datetime.now(UTC),
        }

    def _upsert_rows_sync(self, rows: list[dict[str, object]]) -> None:
        assert self._table is not None  # noqa: S101
        # LanceDB merge_insert uses the ``note_id`` as the conflict key; this
        # mirrors DuckDB's ON CONFLICT (id) DO UPDATE.
        self._table.merge_insert("note_id").when_matched_update_all().when_not_matched_insert_all().execute(rows)  # type: ignore[attr-defined]

    async def delete(self, note_id: UUID) -> None:
        async with self._lock:
            self._require_open()
            await anyio.to_thread.run_sync(
                lambda: self._table.delete(f"note_id = '{note_id}'"),  # type: ignore[union-attr]
            )

    # ── reads ──────────────────────────────────────────────────────────

    async def query(
        self,
        query_vector: Sequence[float],
        *,
        group_ids: tuple[str, ...] = (),
        top_k: int = 20,
        tier: TierName | None = None,
    ) -> list[VectorHit]:
        """ANN query with optional group_id filter (dual-pool partitioning)."""
        if len(query_vector) != self._embedding_dim:
            raise ValueError(
                f"query_vector dim mismatch: got {len(query_vector)}, "
                f"expected {self._embedding_dim}",
            )
        async with self._lock:
            self._require_open()

            def _search() -> list[dict[str, object]]:
                assert self._table is not None  # noqa: S101
                search = self._table.search(list(query_vector))  # type: ignore[attr-defined]
                clauses: list[str] = []
                if group_ids:
                    # Inline literal-quoted IN clause — values come from the
                    # type-narrow ``group_ids`` tuple (caller-supplied
                    # via PoolScope), not user input. SQL-injection surface
                    # is none because the values are bounded to ASCII slugs
                    # (validated upstream).
                    quoted = ",".join(f"'{gid}'" for gid in group_ids)
                    clauses.append(f"{GROUP_ID_COLUMN} IN ({quoted})")
                if tier is not None:
                    clauses.append(f"tier = '{tier}'")
                if clauses:
                    search = search.where(" AND ".join(clauses), prefilter=True)
                search = search.limit(top_k)
                # ``to_list`` returns plain dicts; ``_distance`` is LanceDB's
                # cosine distance (lower = closer). Convert to similarity
                # by ``1 - distance`` for higher = better.
                return list(search.to_list())

            rows = await anyio.to_thread.run_sync(_search)

        hits: list[VectorHit] = []
        for r in rows:
            distance_raw = r.get("_distance", 0.0)
            distance = float(distance_raw) if isinstance(distance_raw, (int, float)) else 0.0
            tier_val = r.get("tier", "")
            tier_name = tier_val if isinstance(tier_val, str) else ""
            proj_raw = r.get("project_slug")
            proj = proj_raw if isinstance(proj_raw, str) else None
            sess_raw = r.get("session_id")
            sess = sess_raw if isinstance(sess_raw, str) else None
            hits.append(
                VectorHit(
                    note_id=UUID(str(r["note_id"])),
                    group_id=str(r[GROUP_ID_COLUMN]),
                    score=1.0 - distance,
                    project_slug=proj,
                    session_id=sess,
                    tier=tier_name,  # type: ignore[arg-type]
                ),
            )
        return hits

    async def count(self, *, group_id: str | None = None) -> int:
        """Row count (optionally scoped to one group_id)."""
        async with self._lock:
            self._require_open()

            def _count() -> int:
                assert self._table is not None  # noqa: S101
                if group_id is None:
                    return int(self._table.count_rows())  # type: ignore[attr-defined]
                return int(self._table.count_rows(filter=f"{GROUP_ID_COLUMN} = '{group_id}'"))  # type: ignore[attr-defined]

            return await anyio.to_thread.run_sync(_count)

    # ── helpers ────────────────────────────────────────────────────────

    def _require_open(self) -> None:
        if self._table is None:
            raise RuntimeError(
                "LanceDBVectorStore is not open. Call await setup() first.",
            )
