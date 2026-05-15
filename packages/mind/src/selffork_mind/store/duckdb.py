"""DuckDB reference implementation of :class:`~selffork_mind.store.base.MindStore`.

Single-file embedded; per-project DB at
``~/.selffork/projects/<slug>/mind/notes.duckdb`` (or
``~/.selffork/mind/notes.duckdb`` for the global / no-project case).

DuckDB v1 supports the ``vss`` extension for vector cosine search
(``ARRAY<FLOAT, N>`` columns + HNSW index). This backend stores embeddings
directly when supplied; backends without embedding info fall back to
filter-only retrieval.

Concurrency model: DuckDB is single-writer + multi-reader. We serialise
writes through an asyncio Lock and run all DB calls on a worker thread
(via :func:`anyio.to_thread.run_sync`) so the orchestrator's event loop is
never blocked.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import anyio
import duckdb

from selffork_mind.memory.filters import (
    Filter,
    FilterAll,
    FilterAny,
    FilterCondition,
    FilterNot,
)
from selffork_mind.memory.model import Note, TierName
from selffork_mind.memory.tags import Tag, TagMatchMode
from selffork_mind.store.base import (
    MindStore,
    RetrievalHit,
    RetrieveConfig,
    StoreScope,
    TierStats,
)

__all__ = ["DuckDBMindStore"]


_NOTES_DDL = """
CREATE TABLE IF NOT EXISTS notes (
    id UUID PRIMARY KEY,
    schema_version INTEGER NOT NULL DEFAULT 1,
    tier TEXT NOT NULL,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    intent TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_until TIMESTAMPTZ,
    project_slug TEXT,
    session_id TEXT,
    source_pointer TEXT,
    path_scope_json TEXT NOT NULL DEFAULT '[]',
    always_apply BOOLEAN NOT NULL DEFAULT FALSE,
    importance DOUBLE NOT NULL DEFAULT 1.0,
    pinned BOOLEAN NOT NULL DEFAULT FALSE,
    embedding DOUBLE[],
    embedder_name TEXT,
    embedder_dim INTEGER,
    written_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

_TAGS_DDL = """
CREATE TABLE IF NOT EXISTS tags (
    note_id UUID NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (note_id, key, value)
);
"""

_INDICES = (
    "CREATE INDEX IF NOT EXISTS idx_notes_tier ON notes(tier);",
    "CREATE INDEX IF NOT EXISTS idx_notes_project_slug ON notes(project_slug);",
    "CREATE INDEX IF NOT EXISTS idx_notes_session_id ON notes(session_id);",
    "CREATE INDEX IF NOT EXISTS idx_notes_content_hash ON notes(content_hash);",
    "CREATE INDEX IF NOT EXISTS idx_tags_note_id ON tags(note_id);",
    "CREATE INDEX IF NOT EXISTS idx_tags_key_value ON tags(key, value);",
)


class DuckDBMindStore(MindStore):
    """File-backed DuckDB implementation of :class:`MindStore`."""

    def __init__(self, *, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = asyncio.Lock()
        self._conn: duckdb.DuckDBPyConnection | None = None

    async def setup(self) -> None:
        async with self._lock:
            if self._conn is not None:
                return
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = await anyio.to_thread.run_sync(
                lambda: duckdb.connect(str(self._db_path)),
            )
            await anyio.to_thread.run_sync(self._init_schema)

    def _init_schema(self) -> None:
        assert self._conn is not None  # noqa: S101
        self._conn.execute(_NOTES_DDL)
        self._conn.execute(_TAGS_DDL)
        for ddl in _INDICES:
            self._conn.execute(ddl)

    async def teardown(self) -> None:
        async with self._lock:
            if self._conn is not None:
                conn = self._conn
                self._conn = None
                await anyio.to_thread.run_sync(conn.close)

    # ── writes ─────────────────────────────────────────────────────────

    async def upsert_note(self, note: Note) -> Note:
        result = await self.upsert_notes([note])
        return result[0]

    async def upsert_notes(self, notes: Sequence[Note]) -> list[Note]:
        if not notes:
            return []
        async with self._lock:
            self._require_open()
            rows = [self._note_to_row(n) for n in notes]
            await anyio.to_thread.run_sync(self._upsert_rows, rows)
        return list(notes)

    def _upsert_rows(self, rows: list[tuple[object, ...]]) -> None:
        assert self._conn is not None  # noqa: S101
        # DuckDB INSERT ... ON CONFLICT supports per-column updates.
        self._conn.executemany(
            """
            INSERT INTO notes (
                id, schema_version, tier, kind, content, intent, content_hash,
                valid_from, valid_until, project_slug, session_id,
                source_pointer, path_scope_json, always_apply,
                importance, pinned, embedding, embedder_name, embedder_dim,
                written_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                schema_version = EXCLUDED.schema_version,
                tier = EXCLUDED.tier,
                kind = EXCLUDED.kind,
                content = EXCLUDED.content,
                intent = EXCLUDED.intent,
                content_hash = EXCLUDED.content_hash,
                valid_from = EXCLUDED.valid_from,
                valid_until = EXCLUDED.valid_until,
                project_slug = EXCLUDED.project_slug,
                session_id = EXCLUDED.session_id,
                source_pointer = EXCLUDED.source_pointer,
                path_scope_json = EXCLUDED.path_scope_json,
                always_apply = EXCLUDED.always_apply,
                importance = EXCLUDED.importance,
                pinned = EXCLUDED.pinned,
                embedding = EXCLUDED.embedding,
                embedder_name = EXCLUDED.embedder_name,
                embedder_dim = EXCLUDED.embedder_dim,
                written_at = EXCLUDED.written_at
            """,
            rows,
        )

    @staticmethod
    def _note_to_row(note: Note) -> tuple[object, ...]:
        return (
            note.id,
            note.schema_version,
            note.tier,
            note.kind,
            note.content,
            note.intent,
            note.content_hash,
            note.valid_from,
            note.valid_until,
            note.project_slug,
            note.session_id,
            note.source_pointer,
            json.dumps(list(note.path_scope)),
            note.always_apply,
            note.importance,
            note.pinned,
            None,  # embedding (set via attach_embedding when ready)
            None,
            None,
            datetime.now(UTC),
        )

    async def supersede(
        self,
        note_id: UUID,
        *,
        at: datetime | None = None,
    ) -> Note | None:
        moment = at if at is not None else datetime.now(UTC)
        async with self._lock:
            self._require_open()
            await anyio.to_thread.run_sync(
                lambda: self._conn.execute(  # type: ignore[union-attr]
                    "UPDATE notes SET valid_until = ? WHERE id = ?",
                    [moment, note_id],
                ),
            )
        return await self.get_note(note_id)

    async def attach_tag(self, tag: Tag) -> Tag:
        await self.attach_tags([tag])
        return tag

    async def attach_tags(self, tags: Sequence[Tag]) -> list[Tag]:
        if not tags:
            return []
        async with self._lock:
            self._require_open()
            rows = [(t.note_id, t.key, t.value, t.created_at) for t in tags]
            await anyio.to_thread.run_sync(
                lambda: self._conn.executemany(  # type: ignore[union-attr]
                    "INSERT OR IGNORE INTO tags (note_id, key, value, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    rows,
                ),
            )
        return list(tags)

    async def attach_embedding(
        self,
        *,
        note_id: UUID,
        vector: Sequence[float],
        embedder_name: str,
    ) -> None:
        async with self._lock:
            self._require_open()
            vec = [float(x) for x in vector]
            dim = len(vec)
            await anyio.to_thread.run_sync(
                lambda: self._conn.execute(  # type: ignore[union-attr]
                    "UPDATE notes SET embedding = ?, embedder_name = ?, "
                    "embedder_dim = ? WHERE id = ?",
                    [vec, embedder_name, dim, note_id],
                ),
            )

    async def get_embedding(
        self,
        note_id: UUID,
    ) -> tuple[list[float], str] | None:
        async with self._lock:
            self._require_open()

            def _fetch() -> tuple[object, object] | None:
                assert self._conn is not None  # noqa: S101
                rows = self._conn.execute(
                    "SELECT embedding, embedder_name FROM notes WHERE id = ?",
                    [note_id],
                ).fetchall()
                if not rows:
                    return None
                return (rows[0][0], rows[0][1])

            row = await anyio.to_thread.run_sync(_fetch)
        if row is None:
            return None
        vec_raw, name_raw = row
        if vec_raw is None or name_raw is None:
            return None
        if not isinstance(vec_raw, (list, tuple)):
            return None
        return ([float(x) for x in vec_raw], str(name_raw))

    async def detach_tag(self, *, note_id: UUID, key: str, value: str) -> bool:
        async with self._lock:
            self._require_open()

            def _delete() -> int:
                assert self._conn is not None  # noqa: S101
                cursor = self._conn.execute(
                    "DELETE FROM tags WHERE note_id = ? AND key = ? AND value = ? RETURNING 1",
                    [note_id, key, value],
                )
                return len(cursor.fetchall())

            deleted = await anyio.to_thread.run_sync(_delete)
        return deleted > 0

    # ── reads ──────────────────────────────────────────────────────────

    async def get_note(self, note_id: UUID) -> Note | None:
        result = await self.get_notes([note_id])
        return result[0] if result else None

    async def get_notes(self, note_ids: Sequence[UUID]) -> list[Note]:
        if not note_ids:
            return []
        async with self._lock:
            self._require_open()
            placeholders = ",".join("?" for _ in note_ids)

            def _fetch() -> list[Any]:
                assert self._conn is not None  # noqa: S101
                # placeholders is "?,?,?" — safe; no user input in SQL string.
                rows = self._conn.execute(
                    f"SELECT * FROM notes WHERE id IN ({placeholders})",  # noqa: S608
                    list(note_ids),
                ).fetchall()
                cols = [d[0] for d in self._conn.description or ()]
                return [dict(zip(cols, r, strict=True)) for r in rows]

            rows = await anyio.to_thread.run_sync(_fetch)
        by_id = {r["id"]: self._row_to_note(r) for r in rows}
        return [by_id[nid] for nid in note_ids if nid in by_id]

    async def list_tags(self, note_id: UUID) -> list[Tag]:
        async with self._lock:
            self._require_open()

            def _fetch() -> list[Any]:
                assert self._conn is not None  # noqa: S101
                return self._conn.execute(
                    "SELECT note_id, key, value, created_at FROM tags "
                    "WHERE note_id = ? ORDER BY created_at",
                    [note_id],
                ).fetchall()

            rows = await anyio.to_thread.run_sync(_fetch)
        return [Tag(note_id=r[0], key=r[1], value=r[2], created_at=r[3]) for r in rows]

    async def count_by_tier(self, scope: StoreScope) -> dict[TierName, TierStats]:
        """Per-tier counts + recency. Order 3 — M4 cockpit Context tab."""
        async with self._lock:
            self._require_open()

            def _count() -> dict[TierName, TierStats]:
                assert self._conn is not None  # noqa: S101
                clauses = ["valid_until IS NULL"]
                params: list[object] = []
                if scope.project_slug is not None:
                    clauses.append("project_slug = ?")
                    params.append(scope.project_slug)
                if scope.session_id is not None:
                    clauses.append("session_id = ?")
                    params.append(scope.session_id)
                where = " AND ".join(clauses)
                # ``where`` is composed only from constant clause strings
                # above — user input is bound through ``params``. No
                # injection surface; S608 is a false positive on the
                # f-string composition.
                base = "SELECT tier, COUNT(*), MAX(written_at) FROM notes"
                sql = f"{base} WHERE {where} GROUP BY tier"
                cursor = self._conn.execute(sql, params)
                # ``tier`` column is constrained at the model layer
                # (Note.tier is a Literal); cast satisfies mypy without
                # adding a runtime check that would never fire.
                return {
                    cast("TierName", row[0]): TierStats(
                        count=int(row[1]),
                        last_updated=row[2],
                    )
                    for row in cursor.fetchall()
                }

            return await anyio.to_thread.run_sync(_count)

    async def retrieve(self, config: RetrieveConfig) -> list[RetrievalHit]:
        async with self._lock:
            self._require_open()

            def _query() -> list[Any]:
                assert self._conn is not None  # noqa: S101
                sql, params = _build_retrieve_sql(config)
                rows = self._conn.execute(sql, params).fetchall()
                cols = [d[0] for d in self._conn.description or ()]
                return [dict(zip(cols, r, strict=True)) for r in rows]

            rows = await anyio.to_thread.run_sync(_query)

        # Apply path-scope filter in Python (DuckDB has no glob predicate that
        # plays nicely with our JSON-encoded path_scope_json column).
        notes = [self._row_to_note(r) for r in rows]
        if config.file_path is not None:
            notes = [n for n in notes if _path_scope_matches(n, config.file_path)]

        # Apply tag match-mode filter in Python — cleaner than the SQL
        # gymnastics for ANY/ALL semantics.
        if config.tag_pairs:
            notes = await self._filter_by_tags(notes, config)

        hits = await self._score(notes, config)
        hits.sort(key=lambda h: h.score, reverse=True)
        cap = config.top_k * config.rerank_overfetch
        return hits[:cap]

    async def _score(
        self,
        notes: list[Note],
        config: RetrieveConfig,
    ) -> list[RetrievalHit]:
        if config.query_embedding is None:
            return [RetrievalHit(note=n, score=_baseline_score(n)) for n in notes]
        if not notes:
            return []

        # Vector path: fetch each note's embedding (when present) and rank by
        # cosine similarity. Notes without an embedding fall back to the
        # baseline score, scaled into [0, 1] so vector hits dominate when
        # both populations exist.
        ids = [n.id for n in notes]
        async with self._lock:
            self._require_open()
            placeholders = ",".join("?" for _ in ids)

            def _fetch() -> list[Any]:
                assert self._conn is not None  # noqa: S101
                # placeholders is "?,?,?" — safe; no user input in SQL string.
                return self._conn.execute(
                    f"SELECT id, embedding FROM notes WHERE id IN ({placeholders})",  # noqa: S608
                    list(ids),
                ).fetchall()

            rows = await anyio.to_thread.run_sync(_fetch)

        embeddings: dict[UUID, list[float]] = {}
        for note_id, vec in rows:
            if vec is None:
                continue
            embeddings[note_id] = [float(x) for x in vec]

        query_vec = list(config.query_embedding)
        hits: list[RetrievalHit] = []
        for n in notes:
            stored = embeddings.get(n.id)
            if stored is None:
                # No embedding stored yet — fall back to a small baseline so
                # the note can still surface, but never outrank a real match.
                hits.append(RetrievalHit(note=n, score=_baseline_fallback(n)))
                continue
            score = _cosine_similarity(query_vec, stored)
            hits.append(RetrievalHit(note=n, score=score))
        return hits

    async def _filter_by_tags(
        self,
        notes: list[Note],
        config: RetrieveConfig,
    ) -> list[Note]:
        if not notes:
            return []
        ids = [n.id for n in notes]
        async with self._lock:
            self._require_open()
            placeholders = ",".join("?" for _ in ids)

            def _fetch() -> list[Any]:
                assert self._conn is not None  # noqa: S101
                # placeholders is "?,?,?" — safe; no user input in SQL string.
                return self._conn.execute(
                    f"SELECT note_id, key, value FROM tags WHERE note_id IN ({placeholders})",  # noqa: S608
                    list(ids),
                ).fetchall()

            rows = await anyio.to_thread.run_sync(_fetch)
        per_note: dict[UUID, set[tuple[str, str]]] = {nid: set() for nid in ids}
        for nid, key, value in rows:
            per_note.setdefault(nid, set()).add((key, value))

        wanted: set[tuple[str, str]] = set(config.tag_pairs)
        if not wanted:
            return notes

        def _matches(tags: set[tuple[str, str]]) -> bool:
            if config.tag_match_mode is TagMatchMode.ALL:
                return wanted.issubset(tags)
            return bool(wanted & tags)

        return [n for n in notes if _matches(per_note.get(n.id, set()))]

    # ── helpers ────────────────────────────────────────────────────────

    def _require_open(self) -> None:
        if self._conn is None:
            raise RuntimeError(
                "DuckDBMindStore is not open. Call await setup() first.",
            )

    @staticmethod
    def _row_to_note(row: dict[str, object]) -> Note:
        path_scope_raw = row.get("path_scope_json", "[]")
        if not isinstance(path_scope_raw, str):
            path_scope_raw = "[]"
        path_scope = tuple(json.loads(path_scope_raw))
        valid_from = row["valid_from"]
        valid_until = row.get("valid_until")
        return Note.model_validate(
            {
                "id": row["id"],
                "schema_version": row["schema_version"],
                "tier": row["tier"],
                "kind": row["kind"],
                "content": row["content"],
                "intent": row["intent"],
                "content_hash": row["content_hash"],
                "valid_from": valid_from,
                "valid_until": valid_until,
                "project_slug": row["project_slug"],
                "session_id": row["session_id"],
                "source_pointer": row.get("source_pointer"),
                "path_scope": path_scope,
                "always_apply": bool(row["always_apply"]),
                "importance": float(row["importance"]),  # type: ignore[arg-type]
                "pinned": bool(row["pinned"]),
            },
        )


# ── retrieve SQL builder ────────────────────────────────────────────────────


def _build_retrieve_sql(config: RetrieveConfig) -> tuple[str, list[object]]:
    """Translate a :class:`RetrieveConfig` into DuckDB SQL + params."""
    where: list[str] = []
    params: list[object] = []

    if config.tiers:
        placeholders = ",".join("?" for _ in config.tiers)
        where.append(f"tier IN ({placeholders})")
        params.extend(config.tiers)

    where.extend(_scope_clauses(config.scope, params))

    if not config.include_invalid:
        moment = config.valid_at if config.valid_at is not None else datetime.now(UTC)
        where.append("valid_from <= ?")
        params.append(moment)
        where.append("(valid_until IS NULL OR valid_until > ?)")
        params.append(moment)

    if config.filter is not None:
        clause, sub_params = _filter_to_sql(config.filter)
        where.append(clause)
        params.extend(sub_params)

    sql = "SELECT * FROM notes"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY pinned DESC, importance DESC, valid_from DESC"
    return sql, params


def _scope_clauses(scope: StoreScope, params: list[object]) -> list[str]:
    out: list[str] = []
    if scope.project_slug is not None:
        out.append("project_slug = ?")
        params.append(scope.project_slug)
    if scope.session_id is not None:
        out.append("session_id = ?")
        params.append(scope.session_id)
    # cli_agent and operator_id are tag-encoded (Order 1 keeps the column
    # surface narrow); they apply via tag_keys/tag_values.
    return out


def _filter_to_sql(f: Filter) -> tuple[str, list[object]]:
    if isinstance(f, FilterCondition):
        return _condition_to_sql(f)
    if isinstance(f, FilterAll):
        if not f.children:
            return ("TRUE", [])
        parts = [_filter_to_sql(c) for c in f.children]
        clause = "(" + " AND ".join(p[0] for p in parts) + ")"
        params: list[object] = [p for sub in parts for p in sub[1]]
        return clause, params
    if isinstance(f, FilterAny):
        if not f.children:
            return ("FALSE", [])
        parts = [_filter_to_sql(c) for c in f.children]
        clause = "(" + " OR ".join(p[0] for p in parts) + ")"
        params = [p for sub in parts for p in sub[1]]
        return clause, params
    if isinstance(f, FilterNot):
        sub_clause, sub_params = _filter_to_sql(f.child)
        return f"(NOT {sub_clause})", sub_params
    raise TypeError(f"Unknown filter shape: {type(f).__name__}")


_OP_TO_SQL: dict[str, str] = {
    "eq": "=",
    "ne": "!=",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
}


def _condition_to_sql(c: FilterCondition) -> tuple[str, list[object]]:
    col = c.field
    if c.op in _OP_TO_SQL:
        return f"{col} {_OP_TO_SQL[c.op]} ?", [c.value]
    if c.op in {"in_", "in"}:
        if not isinstance(c.value, (list, tuple)) or not c.value:
            return "FALSE", []
        placeholders = ",".join("?" for _ in c.value)
        return f"{col} IN ({placeholders})", list(c.value)
    if c.op == "nin":
        if not isinstance(c.value, (list, tuple)) or not c.value:
            return "TRUE", []
        placeholders = ",".join("?" for _ in c.value)
        return f"{col} NOT IN ({placeholders})", list(c.value)
    if c.op == "contains":
        return f"{col} LIKE ?", [f"%{c.value}%"]
    if c.op == "icontains":
        return f"LOWER({col}) LIKE LOWER(?)", [f"%{c.value}%"]
    raise ValueError(f"Unsupported filter op: {c.op!r}")


def _path_scope_matches(note: Note, file_path: str) -> bool:
    """Path-scope glob matcher.

    Uses :func:`fnmatch.fnmatch`. Note: stdlib ``fnmatch`` does NOT
    treat ``**`` as a recursive wildcard (Python 3.13's ``glob.translate``
    does, but we stay 3.12-compatible). For the operator's typical
    Cursor-style globs (``packages/mind/**/*.py``) this means single-
    level matching only — operators wanting recursive matches should
    enumerate explicit subdirectory globs or wait for the Order 4+
    upgrade to ``glob.translate``.
    """
    if note.always_apply:
        return True
    if not note.path_scope:
        return True  # unscoped notes always match
    return any(fnmatch(file_path, pattern) for pattern in note.path_scope)


def _baseline_score(note: Note) -> float:
    """Filter-only baseline score (no query embedding).

    Pinned notes always sort first. Otherwise: importance * recency factor
    where recency factor decays exponentially over a 7-day half-life.
    """
    if note.pinned:
        return 1e9
    delta_seconds = max(
        0.0,
        (datetime.now(UTC) - note.valid_from).total_seconds(),
    )
    half_life_seconds = 7 * 24 * 3600
    decay: float = 0.5 ** (delta_seconds / half_life_seconds)
    return float(note.importance) * decay


def _baseline_fallback(note: Note) -> float:
    """Vector-path fallback for notes without a stored embedding.

    Capped to ``< 1.0`` so a real cosine match always outranks an
    embedding-less note when both populations co-exist in one query.
    """
    if note.pinned:
        return 0.99
    delta_seconds = max(
        0.0,
        (datetime.now(UTC) - note.valid_from).total_seconds(),
    )
    half_life_seconds = 7 * 24 * 3600
    decay: float = 0.5 ** (delta_seconds / half_life_seconds)
    importance_norm = min(float(note.importance) / 10.0, 1.0)
    return float(0.5 * importance_norm * decay)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity for two equal-length float vectors.

    Returns 0.0 when either vector is the zero vector or dimensions
    mismatch — the latter is treated as "incompatible embedder", not a
    crash, so a corpus migrating to a new embedder degrades gracefully
    instead of raising mid-query.
    """
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(dot / (norm_a * norm_b))
