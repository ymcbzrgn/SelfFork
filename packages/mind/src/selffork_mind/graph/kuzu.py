"""Kuzu-backed :class:`SemanticGraphStore` (optional, lazy-imported).

Kuzu is an MIT-licensed embedded graph database (Graphiti-compatible,
Cypher-queryable, on-disk single-process).

Order 4 ships the schema + minimal CRUD; HippoRAG 2 PPR runs from the
orchestrator's pure-Python helper :func:`personalized_pagerank` so the
implementation stays backend-neutral.

Install with ``pip install 'selffork-mind[graph-kuzu]'``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from selffork_mind.graph.base import GraphTriple

__all__ = ["KuzuGraphStore"]


_TRIPLES_DDL = """
CREATE NODE TABLE IF NOT EXISTS Phrase (
    id STRING,
    PRIMARY KEY (id)
);
"""
_PASSAGE_DDL = """
CREATE NODE TABLE IF NOT EXISTS Passage (
    id STRING,
    PRIMARY KEY (id)
);
"""
_CONTAINS_DDL = """
CREATE REL TABLE IF NOT EXISTS Contains (
    FROM Passage TO Phrase
);
"""
_TRIPLE_REL_DDL = """
CREATE REL TABLE IF NOT EXISTS Triple (
    FROM Phrase TO Phrase,
    predicate STRING,
    source_passage_id STRING,
    project_slug STRING,
    confidence DOUBLE,
    valid_from STRING,
    valid_until STRING
);
"""


class KuzuGraphStore:
    """Embedded Kuzu backend.

    Requires ``kuzu`` package — install with
    ``pip install 'selffork-mind[graph-kuzu]'``. Construction defers
    the import so unrelated code paths don't pay the cost.
    """

    def __init__(self, *, db_path: Path) -> None:
        self._db_path = db_path
        self._db: object | None = None
        self._conn: object | None = None
        self._setup_done = False

    async def setup(self) -> None:
        if self._setup_done:
            return
        try:
            import kuzu  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - optional dep error path
            raise ImportError(
                "KuzuGraphStore requires the 'kuzu' package. Install with "
                "pip install 'selffork-mind[graph-kuzu]'.",
            ) from exc
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = kuzu.Database(str(self._db_path))
        self._conn = kuzu.Connection(self._db)
        self._init_schema()
        self._setup_done = True

    def _init_schema(self) -> None:
        assert self._conn is not None  # noqa: S101 — internal invariant
        for ddl in (_PASSAGE_DDL, _TRIPLES_DDL, _CONTAINS_DDL, _TRIPLE_REL_DDL):
            self._conn.execute(ddl)  # type: ignore[attr-defined]

    async def teardown(self) -> None:
        self._conn = None
        self._db = None
        self._setup_done = False

    # ── triples ──────────────────────────────────────────────────────────

    async def add_triple(self, triple: GraphTriple) -> None:
        assert self._conn is not None  # noqa: S101
        # MERGE phrases first; then create the Triple relationship.
        self._conn.execute(  # type: ignore[attr-defined]
            "MERGE (s:Phrase {id: $s}); MERGE (o:Phrase {id: $o});",
            {"s": triple.subject, "o": triple.obj},
        )
        self._conn.execute(  # type: ignore[attr-defined]
            "MATCH (s:Phrase {id: $s}), (o:Phrase {id: $o}) "
            "CREATE (s)-[:Triple {"
            "predicate: $p, source_passage_id: $src, project_slug: $proj, "
            "confidence: $c, valid_from: $vf, valid_until: $vu"
            "}]->(o);",
            {
                "s": triple.subject,
                "o": triple.obj,
                "p": triple.predicate,
                "src": str(triple.source_passage_id),
                "proj": triple.project_slug or "",
                "c": triple.confidence,
                "vf": triple.valid_from.isoformat(),
                "vu": triple.valid_until.isoformat() if triple.valid_until else "",
            },
        )

    async def add_triples(self, triples: Sequence[GraphTriple]) -> None:
        for triple in triples:
            await self.add_triple(triple)

    async def supersede_triple(
        self,
        *,
        subject: str,
        predicate: str,
        object_: str,
        source_passage_id: UUID,
        at: datetime | None = None,
    ) -> bool:
        assert self._conn is not None  # noqa: S101
        moment = at if at is not None else datetime.now(UTC)
        # Match the live (no valid_until) edge and stamp it.
        result = self._conn.execute(  # type: ignore[attr-defined]
            "MATCH (s:Phrase {id: $s})-[r:Triple]->(o:Phrase {id: $o}) "
            "WHERE r.predicate = $p AND r.source_passage_id = $src AND r.valid_until = '' "
            "SET r.valid_until = $until "
            "RETURN count(r) AS c;",
            {
                "s": subject,
                "o": object_,
                "p": predicate,
                "src": str(source_passage_id),
                "until": moment.isoformat(),
            },
        )
        return _kuzu_count(result) > 0

    async def list_triples(
        self,
        *,
        project_slug: str | None = None,
        subject: str | None = None,
        predicate: str | None = None,
        object_: str | None = None,
        valid_at: datetime | None = None,
    ) -> list[GraphTriple]:
        assert self._conn is not None  # noqa: S101
        clauses: list[str] = []
        params: dict[str, object] = {}
        if project_slug is not None:
            clauses.append("r.project_slug = $proj")
            params["proj"] = project_slug
        if subject is not None:
            clauses.append("s.id = $s")
            params["s"] = subject
        if predicate is not None:
            clauses.append("r.predicate = $p")
            params["p"] = predicate
        if object_ is not None:
            clauses.append("o.id = $o")
            params["o"] = object_
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        cypher = (
            "MATCH (s:Phrase)-[r:Triple]->(o:Phrase)"
            f"{where} "
            "RETURN s.id, o.id, r.predicate, r.source_passage_id, "
            "r.project_slug, r.confidence, r.valid_from, r.valid_until;"
        )
        rows = self._conn.execute(cypher, params)  # type: ignore[attr-defined]
        out: list[GraphTriple] = []
        for row in _kuzu_rows(rows):
            triple = GraphTriple(
                subject=str(row[0]),
                obj=str(row[1]),
                predicate=str(row[2]),
                source_passage_id=UUID(str(row[3])),
                project_slug=str(row[4]) or None,
                confidence=float(str(row[5])),
                valid_from=datetime.fromisoformat(str(row[6])),
                valid_until=(datetime.fromisoformat(str(row[7])) if row[7] else None),
            )
            if valid_at is not None and not triple.is_currently_valid(at=valid_at):
                continue
            out.append(triple)
        return out

    # ── passage / phrase ─────────────────────────────────────────────────

    async def add_passage(self, *, passage_id: UUID, phrases: Sequence[str]) -> None:
        assert self._conn is not None  # noqa: S101
        self._conn.execute(  # type: ignore[attr-defined]
            "MERGE (p:Passage {id: $id});",
            {"id": str(passage_id)},
        )
        for phrase in phrases:
            self._conn.execute(  # type: ignore[attr-defined]
                "MERGE (ph:Phrase {id: $ph});",
                {"ph": phrase},
            )
            self._conn.execute(  # type: ignore[attr-defined]
                "MATCH (p:Passage {id: $id}), (ph:Phrase {id: $ph}) MERGE (p)-[:Contains]->(ph);",
                {"id": str(passage_id), "ph": phrase},
            )

    async def list_phrases_for_passage(self, passage_id: UUID) -> list[str]:
        assert self._conn is not None  # noqa: S101
        rows = self._conn.execute(  # type: ignore[attr-defined]
            "MATCH (p:Passage {id: $id})-[:Contains]->(ph:Phrase) RETURN ph.id;",
            {"id": str(passage_id)},
        )
        return sorted(str(row[0]) for row in _kuzu_rows(rows))

    async def list_passages_for_phrase(self, phrase: str) -> list[UUID]:
        assert self._conn is not None  # noqa: S101
        rows = self._conn.execute(  # type: ignore[attr-defined]
            "MATCH (p:Passage)-[:Contains]->(ph:Phrase {id: $ph}) RETURN p.id;",
            {"ph": phrase},
        )
        return sorted([UUID(str(row[0])) for row in _kuzu_rows(rows)], key=str)

    async def list_phrase_neighbours(
        self,
        phrase: str,
        *,
        max_hops: int = 2,
    ) -> list[str]:
        assert self._conn is not None  # noqa: S101
        if max_hops < 1:
            return []
        # max_hops walks through passage nodes ignoring Triple direction —
        # HippoRAG 2 calls these "contains-edges". For 1-hop, a single
        # MATCH suffices. For >1 hop, BFS through Python by repeatedly
        # querying the 1-hop frontier (Kuzu's variable-length-path
        # syntax differs across versions; this stays portable).
        visited: set[str] = {phrase}
        frontier: set[str] = {phrase}
        for _ in range(max_hops):
            next_frontier: set[str] = set()
            for cur in frontier:
                rows = self._conn.execute(  # type: ignore[attr-defined]
                    "MATCH (start:Phrase {id: $ph})"
                    "<-[:Contains]-(p:Passage)"
                    "-[:Contains]->(neighbour:Phrase) "
                    "WHERE neighbour.id <> $ph "
                    "RETURN DISTINCT neighbour.id;",
                    {"ph": cur},
                )
                for row in _kuzu_rows(rows):
                    nb = str(row[0])
                    if nb not in visited:
                        visited.add(nb)
                        next_frontier.add(nb)
            frontier = next_frontier
            if not frontier:
                break
        return sorted(visited - {phrase})


# ── Kuzu type-shims ────────────────────────────────────────────────────


def _kuzu_count(result: object) -> int:
    """Pull the first column / first row of a Kuzu count() result."""
    try:
        rows = list(_kuzu_rows(result))
    except Exception:
        return 0
    if not rows:
        return 0
    try:
        return int(str(rows[0][0]))
    except (TypeError, ValueError):
        return 0


def _kuzu_rows(result: object) -> list[list[object]]:
    """Iterate a Kuzu QueryResult into Python rows.

    Kuzu's API uses ``has_next()`` / ``get_next()``; we materialise the
    result here so callers can use list semantics.
    """
    rows: list[list[object]] = []
    has_next = getattr(result, "has_next", None)
    get_next = getattr(result, "get_next", None)
    if has_next is None or get_next is None:
        return rows
    while True:
        try:
            if not has_next():
                break
            row = get_next()
        except Exception:  # pragma: no cover — kuzu specific runtime errors
            break
        if isinstance(row, (list, tuple)):
            rows.append(list(row))
        else:
            rows.append([row])
    return rows
