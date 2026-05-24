"""CLI affinity storage backends — single-pool keyed counts (S6).

A store holds the discounted ``(task_type, cli, model) → counts`` cells
for one pool (PROJECT or GLOBAL); ``group_id`` (``p:<slug>`` /
``g:global``, ADR-009 §1) is fixed per store. The dual-pool backoff and
selection live above this layer
(:class:`~selffork_mind.affinity.resolver.CliAffinityResolver` in Mind;
the argmax in the orchestrator router).

Each stored row carries a concrete ``model`` (the one a session used).
Two aggregate read shapes roll rows up for the backoff hierarchy:
``aggregate_cli_model(cli, model)`` (over task types) and
``aggregate_cli(cli)`` (over task types **and** models — a known-good CLI
lends a new model a prior). Two backends ship day one (no MVP staging):

* :class:`InMemoryCliAffinityStore` — dict-backed; tests + ephemeral use.
* :class:`DuckDBCliAffinityStore` — file-backed; production. Mirrors the
  :class:`~selffork_mind.store.duckdb.DuckDBMindStore` lifecycle (async
  lock + ``anyio.to_thread`` around the sync ``duckdb`` driver).

Recency decay is applied at **write** time: each :meth:`record` reads the
existing cell, multiplies the counts by ``decay_gamma``, then folds in
the new observation (a per-observation exponential recency-weighted
average — no timestamps needed in the score path).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast, runtime_checkable

import anyio
import duckdb

from selffork_mind.affinity.model import AffinityRecord

__all__ = [
    "CliAffinityStore",
    "DuckDBCliAffinityStore",
    "InMemoryCliAffinityStore",
]


_TASK_NONE_SENTINEL = ""
"""Stored value for a ``None`` ``task_type``.

DuckDB ``PRIMARY KEY`` columns are ``NOT NULL``; a real ``task_type`` is
never the empty string, so ``""`` is an unambiguous sentinel for "task
type unknown". Converted back to ``None`` at the store boundary. ``cli``
and ``model`` are always concrete in a stored row.
"""


_AFFINITY_DDL = """
CREATE TABLE IF NOT EXISTS cli_affinity (
    group_id     VARCHAR NOT NULL,
    task_type    VARCHAR NOT NULL,
    cli          VARCHAR NOT NULL,
    model        VARCHAR NOT NULL,
    success      DOUBLE  NOT NULL DEFAULT 0,
    failure      DOUBLE  NOT NULL DEFAULT 0,
    total_turns  DOUBLE  NOT NULL DEFAULT 0,
    observations DOUBLE  NOT NULL DEFAULT 0,
    last_used    TIMESTAMP,
    PRIMARY KEY (group_id, task_type, cli, model)
)
"""


def _to_sentinel(task_type: str | None) -> str:
    return _TASK_NONE_SENTINEL if task_type is None else task_type


def _from_sentinel(stored: str) -> str | None:
    return None if stored == _TASK_NONE_SENTINEL else stored


def _decayed(
    *,
    old_success: float,
    old_failure: float,
    old_turns: float,
    old_observations: float,
    succeeded: bool,
    turns: int,
    decay_gamma: float,
) -> tuple[float, float, float, float]:
    """Apply per-observation decay then fold in the new outcome."""
    g = decay_gamma
    new_success = g * old_success + (1.0 if succeeded else 0.0)
    new_failure = g * old_failure + (0.0 if succeeded else 1.0)
    new_turns = g * old_turns + float(turns)
    new_observations = g * old_observations + 1.0
    return new_success, new_failure, new_turns, new_observations


@runtime_checkable
class CliAffinityStore(Protocol):
    """Single-pool affinity store contract (ADR-006 §7.3 schema)."""

    group_id: str

    async def setup(self) -> None:
        """Create tables / open connections. Idempotent."""
        ...

    async def teardown(self) -> None:
        """Close connections. Idempotent."""
        ...

    async def record(
        self,
        *,
        task_type: str | None,
        cli: str,
        model: str,
        succeeded: bool,
        turns: int,
        decay_gamma: float,
        now: datetime | None = None,
    ) -> AffinityRecord:
        """Decay the existing ``(task_type, cli, model)`` cell, fold in
        one outcome, persist, and return the updated record."""
        ...

    async def get(
        self, *, task_type: str | None, cli: str, model: str
    ) -> AffinityRecord | None:
        """Fetch one exact ``(task_type, cli, model)`` cell, or ``None``."""
        ...

    async def aggregate_cli_model(
        self, *, cli: str, model: str
    ) -> AffinityRecord | None:
        """Sum every ``task_type`` row for ``(cli, model)`` (``task_type``
        + ``None`` marker), or ``None`` when unseen."""
        ...

    async def aggregate_cli(self, *, cli: str) -> AffinityRecord | None:
        """Sum every ``(task_type, model)`` row for ``cli`` into one
        aggregate (``task_type``/``model`` ``None``), or ``None``."""
        ...

    async def list_records(self) -> list[AffinityRecord]:
        """All stored cells (observability / tests)."""
        ...


class InMemoryCliAffinityStore:
    """Dict-backed :class:`CliAffinityStore` — tests + ephemeral use."""

    def __init__(self, *, group_id: str) -> None:
        self.group_id = group_id
        # key: (task_sentinel, cli, model)
        self._rows: dict[tuple[str, str, str], AffinityRecord] = {}

    async def setup(self) -> None:
        return None

    async def teardown(self) -> None:
        return None

    async def record(
        self,
        *,
        task_type: str | None,
        cli: str,
        model: str,
        succeeded: bool,
        turns: int,
        decay_gamma: float,
        now: datetime | None = None,
    ) -> AffinityRecord:
        moment = now if now is not None else datetime.now(tz=UTC)
        key = (_to_sentinel(task_type), cli, model)
        existing = self._rows.get(key)
        old_s = existing.success if existing else 0.0
        old_f = existing.failure if existing else 0.0
        old_t = existing.total_turns if existing else 0.0
        old_o = existing.observations if existing else 0.0
        new_s, new_f, new_t, new_o = _decayed(
            old_success=old_s,
            old_failure=old_f,
            old_turns=old_t,
            old_observations=old_o,
            succeeded=succeeded,
            turns=turns,
            decay_gamma=decay_gamma,
        )
        record = AffinityRecord(
            group_id=self.group_id,
            task_type=task_type,
            cli=cli,
            model=model,
            success=new_s,
            failure=new_f,
            total_turns=new_t,
            observations=new_o,
            last_used=moment,
        )
        self._rows[key] = record
        return record

    async def get(
        self, *, task_type: str | None, cli: str, model: str
    ) -> AffinityRecord | None:
        return self._rows.get((_to_sentinel(task_type), cli, model))

    async def aggregate_cli_model(
        self, *, cli: str, model: str
    ) -> AffinityRecord | None:
        matched = [
            r for (_, c, m), r in self._rows.items() if c == cli and m == model
        ]
        if not matched:
            return None
        return self._fold(matched, cli=cli, model=model)

    async def aggregate_cli(self, *, cli: str) -> AffinityRecord | None:
        matched = [r for (_, c, _m), r in self._rows.items() if c == cli]
        if not matched:
            return None
        return self._fold(matched, cli=cli, model=None)

    async def list_records(self) -> list[AffinityRecord]:
        return list(self._rows.values())

    def _fold(
        self, rows: list[AffinityRecord], *, cli: str, model: str | None
    ) -> AffinityRecord:
        last_used = max(
            (r.last_used for r in rows if r.last_used is not None),
            default=None,
        )
        return AffinityRecord(
            group_id=self.group_id,
            task_type=None,
            cli=cli,
            model=model,
            success=sum(r.success for r in rows),
            failure=sum(r.failure for r in rows),
            total_turns=sum(r.total_turns for r in rows),
            observations=sum(r.observations for r in rows),
            last_used=last_used,
        )


class DuckDBCliAffinityStore:
    """File-backed :class:`CliAffinityStore` (production).

    One DuckDB file per pool (``<pool>/mind/cli_affinity.duckdb``).
    Lifecycle mirrors :class:`DuckDBMindStore`: an :class:`asyncio.Lock`
    serialises access and every DB call hops to a worker thread via
    ``anyio.to_thread`` (the ``duckdb`` driver is sync).
    """

    def __init__(self, *, group_id: str, db_path: Path) -> None:
        self.group_id = group_id
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
        self._conn.execute(_AFFINITY_DDL)

    async def teardown(self) -> None:
        async with self._lock:
            if self._conn is not None:
                conn = self._conn
                self._conn = None
                await anyio.to_thread.run_sync(conn.close)

    def _require_open(self) -> None:
        if self._conn is None:
            raise RuntimeError(
                "DuckDBCliAffinityStore is not open. Call await setup() first.",
            )

    async def record(
        self,
        *,
        task_type: str | None,
        cli: str,
        model: str,
        succeeded: bool,
        turns: int,
        decay_gamma: float,
        now: datetime | None = None,
    ) -> AffinityRecord:
        moment = now if now is not None else datetime.now(tz=UTC)
        stored_task = _to_sentinel(task_type)
        async with self._lock:
            self._require_open()
            existing = await anyio.to_thread.run_sync(
                self._fetch_counts, stored_task, cli, model
            )
            old_s, old_f, old_t, old_o = existing if existing else (
                0.0,
                0.0,
                0.0,
                0.0,
            )
            new_s, new_f, new_t, new_o = _decayed(
                old_success=old_s,
                old_failure=old_f,
                old_turns=old_t,
                old_observations=old_o,
                succeeded=succeeded,
                turns=turns,
                decay_gamma=decay_gamma,
            )
            await anyio.to_thread.run_sync(
                self._upsert,
                stored_task,
                cli,
                model,
                new_s,
                new_f,
                new_t,
                new_o,
                moment,
            )
        return AffinityRecord(
            group_id=self.group_id,
            task_type=task_type,
            cli=cli,
            model=model,
            success=new_s,
            failure=new_f,
            total_turns=new_t,
            observations=new_o,
            last_used=moment,
        )

    async def get(
        self, *, task_type: str | None, cli: str, model: str
    ) -> AffinityRecord | None:
        stored_task = _to_sentinel(task_type)
        async with self._lock:
            self._require_open()
            counts = await anyio.to_thread.run_sync(
                self._fetch_full, stored_task, cli, model
            )
        if counts is None:
            return None
        success, failure, turns, observations, last_used = counts
        return AffinityRecord(
            group_id=self.group_id,
            task_type=task_type,
            cli=cli,
            model=model,
            success=success,
            failure=failure,
            total_turns=turns,
            observations=observations,
            last_used=last_used,
        )

    async def aggregate_cli_model(
        self, *, cli: str, model: str
    ) -> AffinityRecord | None:
        async with self._lock:
            self._require_open()
            agg = await anyio.to_thread.run_sync(
                self._fetch_aggregate_cli_model, cli, model
            )
        if agg is None:
            return None
        success, failure, turns, observations, last_used = agg
        return AffinityRecord(
            group_id=self.group_id,
            task_type=None,
            cli=cli,
            model=model,
            success=success,
            failure=failure,
            total_turns=turns,
            observations=observations,
            last_used=last_used,
        )

    async def aggregate_cli(self, *, cli: str) -> AffinityRecord | None:
        async with self._lock:
            self._require_open()
            agg = await anyio.to_thread.run_sync(self._fetch_aggregate_cli, cli)
        if agg is None:
            return None
        success, failure, turns, observations, last_used = agg
        return AffinityRecord(
            group_id=self.group_id,
            task_type=None,
            cli=cli,
            model=None,
            success=success,
            failure=failure,
            total_turns=turns,
            observations=observations,
            last_used=last_used,
        )

    async def list_records(self) -> list[AffinityRecord]:
        async with self._lock:
            self._require_open()
            rows = await anyio.to_thread.run_sync(self._fetch_all)
        return [
            AffinityRecord(
                group_id=self.group_id,
                task_type=_from_sentinel(cast(str, row[0])),
                cli=cast(str, row[1]),
                model=cast(str, row[2]),
                success=float(cast(float, row[3])),
                failure=float(cast(float, row[4])),
                total_turns=float(cast(float, row[5])),
                observations=float(cast(float, row[6])),
                last_used=cast("datetime | None", row[7]),
            )
            for row in rows
        ]

    # ── sync DB helpers (run inside anyio.to_thread) ───────────────────

    def _fetch_counts(
        self, stored_task: str, cli: str, model: str
    ) -> tuple[float, float, float, float] | None:
        assert self._conn is not None  # noqa: S101
        row = self._conn.execute(
            "SELECT success, failure, total_turns, observations "
            "FROM cli_affinity WHERE group_id = ? AND task_type = ? "
            "AND cli = ? AND model = ?",
            [self.group_id, stored_task, cli, model],
        ).fetchone()
        if row is None:
            return None
        return (
            float(cast(float, row[0])),
            float(cast(float, row[1])),
            float(cast(float, row[2])),
            float(cast(float, row[3])),
        )

    def _fetch_full(
        self, stored_task: str, cli: str, model: str
    ) -> tuple[float, float, float, float, datetime | None] | None:
        assert self._conn is not None  # noqa: S101
        row = self._conn.execute(
            "SELECT success, failure, total_turns, observations, last_used "
            "FROM cli_affinity WHERE group_id = ? AND task_type = ? "
            "AND cli = ? AND model = ?",
            [self.group_id, stored_task, cli, model],
        ).fetchone()
        if row is None:
            return None
        return (
            float(cast(float, row[0])),
            float(cast(float, row[1])),
            float(cast(float, row[2])),
            float(cast(float, row[3])),
            cast("datetime | None", row[4]),
        )

    def _fetch_aggregate_cli_model(
        self, cli: str, model: str
    ) -> tuple[float, float, float, float, datetime | None] | None:
        assert self._conn is not None  # noqa: S101
        row = self._conn.execute(
            "SELECT SUM(success), SUM(failure), SUM(total_turns), "
            "SUM(observations), MAX(last_used), COUNT(*) "
            "FROM cli_affinity WHERE group_id = ? AND cli = ? AND model = ?",
            [self.group_id, cli, model],
        ).fetchone()
        return _agg_row(row)

    def _fetch_aggregate_cli(
        self, cli: str
    ) -> tuple[float, float, float, float, datetime | None] | None:
        assert self._conn is not None  # noqa: S101
        row = self._conn.execute(
            "SELECT SUM(success), SUM(failure), SUM(total_turns), "
            "SUM(observations), MAX(last_used), COUNT(*) "
            "FROM cli_affinity WHERE group_id = ? AND cli = ?",
            [self.group_id, cli],
        ).fetchone()
        return _agg_row(row)

    def _fetch_all(self) -> list[tuple[object, ...]]:
        assert self._conn is not None  # noqa: S101
        return self._conn.execute(
            "SELECT task_type, cli, model, success, failure, total_turns, "
            "observations, last_used FROM cli_affinity "
            "WHERE group_id = ? ORDER BY cli, model, task_type",
            [self.group_id],
        ).fetchall()

    def _upsert(
        self,
        stored_task: str,
        cli: str,
        model: str,
        success: float,
        failure: float,
        total_turns: float,
        observations: float,
        last_used: datetime,
    ) -> None:
        assert self._conn is not None  # noqa: S101
        self._conn.execute(
            """
            INSERT INTO cli_affinity (
                group_id, task_type, cli, model, success, failure,
                total_turns, observations, last_used
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (group_id, task_type, cli, model) DO UPDATE SET
                success = EXCLUDED.success,
                failure = EXCLUDED.failure,
                total_turns = EXCLUDED.total_turns,
                observations = EXCLUDED.observations,
                last_used = EXCLUDED.last_used
            """,
            [
                self.group_id,
                stored_task,
                cli,
                model,
                success,
                failure,
                total_turns,
                observations,
                last_used,
            ],
        )


def _agg_row(
    row: tuple[object, ...] | None,
) -> tuple[float, float, float, float, datetime | None] | None:
    """Coerce a ``SUM(...)/COUNT(*)`` aggregate row, or ``None`` if empty."""
    if row is None or int(cast(int, row[5])) == 0:
        return None
    return (
        float(cast(float, row[0])),
        float(cast(float, row[1])),
        float(cast(float, row[2])),
        float(cast(float, row[3])),
        cast("datetime | None", row[4]),
    )
