"""Auto Dream gate + pipeline tests (ADR-009 §4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from selffork_mind.memory.model import Note
from selffork_mind.memory.tiers.reflection import Reflector
from selffork_mind.reflection.auto_dream import (
    AutoDreamCheckpoint,
    AutoDreamConfig,
    AutoDreamGate,
    AutoDreamRunner,
    load_dream_checkpoint,
    save_dream_checkpoint,
)
from selffork_mind.store.duckdb import DuckDBMindStore

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ── AutoDreamConfig ────────────────────────────────────────────────────


class TestAutoDreamConfig:
    def test_defaults_match_anthropic_spec(self) -> None:
        cfg = AutoDreamConfig()
        assert cfg.hours_threshold == 24.0
        assert cfg.sessions_threshold == 5
        assert cfg.idle_minutes == 5.0

    def test_custom_values(self) -> None:
        cfg = AutoDreamConfig(hours_threshold=1.0, sessions_threshold=2, idle_minutes=0.5)
        assert cfg.hours_threshold == 1.0
        assert cfg.sessions_threshold == 2
        assert cfg.idle_minutes == 0.5

    def test_negative_hours_raises(self) -> None:
        with pytest.raises(ValueError, match="hours_threshold must be"):
            AutoDreamConfig(hours_threshold=-1.0)

    def test_negative_sessions_raises(self) -> None:
        with pytest.raises(ValueError, match="sessions_threshold must be"):
            AutoDreamConfig(sessions_threshold=-1)

    def test_negative_idle_raises(self) -> None:
        with pytest.raises(ValueError, match="idle_minutes must be"):
            AutoDreamConfig(idle_minutes=-0.5)


# ── AutoDreamCheckpoint ────────────────────────────────────────────────


class TestAutoDreamCheckpoint:
    def test_roundtrip(self) -> None:
        cp = AutoDreamCheckpoint(
            last_dream_at=datetime(2026, 5, 23, 0, 0, tzinfo=UTC),
            sessions_since_last_dream=7,
            last_reflections_written=3,
        )
        restored = AutoDreamCheckpoint.from_dict(cp.to_dict())
        assert restored.last_dream_at == cp.last_dream_at
        assert restored.sessions_since_last_dream == 7
        assert restored.last_reflections_written == 3

    def test_default_empty(self) -> None:
        cp = AutoDreamCheckpoint()
        assert cp.last_dream_at is None
        assert cp.sessions_since_last_dream == 0

    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        path = tmp_path / "dream-checkpoint.json"
        cp = AutoDreamCheckpoint(
            last_dream_at=datetime(2026, 5, 23, 10, 0, tzinfo=UTC),
            sessions_since_last_dream=4,
            last_reflections_written=2,
        )
        save_dream_checkpoint(path, cp)
        restored = load_dream_checkpoint(path)
        assert restored.last_dream_at == cp.last_dream_at
        assert restored.sessions_since_last_dream == 4

    def test_load_missing_returns_default(self, tmp_path: Path) -> None:
        cp = load_dream_checkpoint(tmp_path / "missing.json")
        assert cp == AutoDreamCheckpoint()

    def test_load_malformed_returns_default(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("not json", encoding="utf-8")
        cp = load_dream_checkpoint(bad)
        assert cp == AutoDreamCheckpoint()


# ── AutoDreamGate ──────────────────────────────────────────────────────


class TestAutoDreamGate:
    def test_no_prior_dream_only_blocks_on_sessions(self) -> None:
        gate = AutoDreamGate(config=AutoDreamConfig())
        decision = gate.evaluate(
            checkpoint=AutoDreamCheckpoint(),
            now=datetime.now(UTC),
            rate_limited=False,
            last_activity_at=None,
        )
        # Hours condition passes (no last_dream_at); sessions=0 < 5 blocks.
        assert not decision.should_run
        assert any("sessions_short" in c for c in decision.failed_conditions)

    def test_hours_block(self) -> None:
        gate = AutoDreamGate(config=AutoDreamConfig())
        now = datetime.now(UTC)
        decision = gate.evaluate(
            checkpoint=AutoDreamCheckpoint(
                last_dream_at=now - timedelta(hours=1),  # less than 24h ago
                sessions_since_last_dream=100,
            ),
            now=now,
            rate_limited=False,
            last_activity_at=None,
        )
        assert not decision.should_run
        assert any("hours_remaining" in c for c in decision.failed_conditions)

    def test_rate_limited_block(self) -> None:
        gate = AutoDreamGate(config=AutoDreamConfig())
        now = datetime.now(UTC)
        decision = gate.evaluate(
            checkpoint=AutoDreamCheckpoint(
                last_dream_at=now - timedelta(hours=25),
                sessions_since_last_dream=10,
            ),
            now=now,
            rate_limited=True,  # blocked here
            last_activity_at=None,
        )
        assert not decision.should_run
        assert "rate_limited" in decision.failed_conditions

    def test_idle_block(self) -> None:
        gate = AutoDreamGate(config=AutoDreamConfig())
        now = datetime.now(UTC)
        decision = gate.evaluate(
            checkpoint=AutoDreamCheckpoint(
                last_dream_at=now - timedelta(hours=25),
                sessions_since_last_dream=10,
            ),
            now=now,
            rate_limited=False,
            last_activity_at=now - timedelta(seconds=30),  # active in last 5 min
        )
        assert not decision.should_run
        assert any("active_within" in c for c in decision.failed_conditions)

    def test_all_conditions_pass(self) -> None:
        gate = AutoDreamGate(config=AutoDreamConfig())
        now = datetime.now(UTC)
        decision = gate.evaluate(
            checkpoint=AutoDreamCheckpoint(
                last_dream_at=now - timedelta(hours=25),
                sessions_since_last_dream=10,
            ),
            now=now,
            rate_limited=False,
            last_activity_at=now - timedelta(minutes=10),  # idle
        )
        assert decision.should_run
        assert decision.failed_conditions == ()
        # bool conversion is the verdict
        assert bool(decision)

    def test_no_activity_signal_means_idle(self) -> None:
        gate = AutoDreamGate(config=AutoDreamConfig())
        now = datetime.now(UTC)
        decision = gate.evaluate(
            checkpoint=AutoDreamCheckpoint(
                last_dream_at=now - timedelta(hours=25),
                sessions_since_last_dream=10,
            ),
            now=now,
            rate_limited=False,
            last_activity_at=None,  # explicitly disabled (test mode)
        )
        assert decision.should_run

    def test_multiple_failures_all_listed(self) -> None:
        gate = AutoDreamGate(config=AutoDreamConfig())
        now = datetime.now(UTC)
        decision = gate.evaluate(
            checkpoint=AutoDreamCheckpoint(
                last_dream_at=now - timedelta(hours=1),  # blocks
                sessions_since_last_dream=2,  # blocks
            ),
            now=now,
            rate_limited=True,  # blocks
            last_activity_at=now,  # blocks
        )
        assert not decision.should_run
        # All four conditions fail.
        assert len(decision.failed_conditions) == 4


# ── AutoDreamRunner end-to-end ─────────────────────────────────────────


@pytest.fixture
async def global_store(tmp_path: Path):
    s = DuckDBMindStore(db_path=tmp_path / "global.duckdb")
    await s.setup()
    yield s
    await s.teardown()


async def _seed_episodic(store: DuckDBMindStore, n: int) -> None:
    base = datetime.now(UTC) - timedelta(hours=1)
    notes = [
        Note(
            tier="episodic",
            kind="observation",
            content=f"global event {i} about consolidation theme",
            intent=f"event-{i}",
            valid_from=base + timedelta(minutes=i),
            project_slug=None,
            group_id="g:global",
            session_id=f"sess-{i}",
            importance=2.0,
        )
        for i in range(n)
    ]
    await store.upsert_notes(notes)


class TestRunnerGateBlocks:
    async def test_maybe_run_returns_none_when_gate_blocks(
        self,
        tmp_path: Path,
        global_store: DuckDBMindStore,
    ) -> None:
        reflector = Reflector(store=global_store)
        runner = AutoDreamRunner(
            reflector=reflector,
            checkpoint_path=tmp_path / "dream-checkpoint.json",
            config=AutoDreamConfig(),  # default 5-session threshold blocks
        )
        result = await runner.maybe_run(
            rate_limited=False,
            last_activity_at=None,
        )
        assert result is None


class TestRunnerForceRun:
    async def test_force_run_writes_reflections(
        self,
        tmp_path: Path,
        global_store: DuckDBMindStore,
    ) -> None:
        await _seed_episodic(global_store, n=8)

        reflector = Reflector(store=global_store)
        runner = AutoDreamRunner(
            reflector=reflector,
            checkpoint_path=tmp_path / "dream-checkpoint.json",
        )
        report = await runner.force_run(project_slug=None)
        assert report.reflection.candidates_examined > 0
        assert report.new_checkpoint.last_dream_at is not None
        assert report.new_checkpoint.sessions_since_last_dream == 0

        # Checkpoint persisted.
        cp = load_dream_checkpoint(tmp_path / "dream-checkpoint.json")
        assert cp.last_dream_at == report.new_checkpoint.last_dream_at


class TestRunnerPassThrough:
    async def test_maybe_run_returns_report_when_gate_open(
        self,
        tmp_path: Path,
        global_store: DuckDBMindStore,
    ) -> None:
        await _seed_episodic(global_store, n=6)

        ckpt_path = tmp_path / "dream-checkpoint.json"
        save_dream_checkpoint(
            ckpt_path,
            AutoDreamCheckpoint(
                last_dream_at=datetime.now(UTC) - timedelta(hours=25),
                sessions_since_last_dream=10,
            ),
        )

        reflector = Reflector(store=global_store)
        runner = AutoDreamRunner(
            reflector=reflector,
            checkpoint_path=ckpt_path,
        )
        report = await runner.maybe_run(
            rate_limited=False,
            last_activity_at=None,  # idle
        )
        assert report is not None
        assert report.duration_seconds >= 0
        payload = report.to_payload()
        assert "reflection" in payload
        assert "new_checkpoint" in payload


class TestBumpSessions:
    async def test_bump_sessions_increments(self, tmp_path: Path) -> None:
        from selffork_mind.memory.tiers.reflection import Reflector

        store = DuckDBMindStore(db_path=tmp_path / "store.duckdb")
        await store.setup()
        try:
            reflector = Reflector(store=store)
            runner = AutoDreamRunner(
                reflector=reflector,
                checkpoint_path=tmp_path / "dream-checkpoint.json",
            )
            cp1 = await runner.bump_sessions()
            assert cp1.sessions_since_last_dream == 1
            cp2 = await runner.bump_sessions(delta=3)
            assert cp2.sessions_since_last_dream == 4
            # Persistence.
            disk = load_dream_checkpoint(tmp_path / "dream-checkpoint.json")
            assert disk.sessions_since_last_dream == 4
        finally:
            await store.teardown()

    async def test_bump_does_not_go_negative(self, tmp_path: Path) -> None:
        store = DuckDBMindStore(db_path=tmp_path / "store.duckdb")
        await store.setup()
        try:
            reflector = Reflector(store=store)
            runner = AutoDreamRunner(
                reflector=reflector,
                checkpoint_path=tmp_path / "dream-checkpoint.json",
            )
            cp = await runner.bump_sessions(delta=-5)
            assert cp.sessions_since_last_dream == 0
        finally:
            await store.teardown()


class TestEvaluateGate:
    async def test_public_gate_evaluation(self, tmp_path: Path) -> None:
        store = DuckDBMindStore(db_path=tmp_path / "store.duckdb")
        await store.setup()
        try:
            reflector = Reflector(store=store)
            runner = AutoDreamRunner(
                reflector=reflector,
                checkpoint_path=tmp_path / "dream-checkpoint.json",
            )
            now = datetime.now(UTC)
            save_dream_checkpoint(
                tmp_path / "dream-checkpoint.json",
                AutoDreamCheckpoint(
                    last_dream_at=now - timedelta(hours=25),
                    sessions_since_last_dream=10,
                ),
            )
            decision = await runner.evaluate_gate(
                now=now,
                rate_limited=False,
                last_activity_at=None,
            )
            assert decision.should_run
        finally:
            await store.teardown()


class TestSessionsCounter:
    async def test_async_counter_overrides_checkpoint(
        self,
        tmp_path: Path,
    ) -> None:
        store = DuckDBMindStore(db_path=tmp_path / "store.duckdb")
        await store.setup()
        try:
            reflector = Reflector(store=store)

            async def counter() -> int:
                return 99

            runner = AutoDreamRunner(
                reflector=reflector,
                checkpoint_path=tmp_path / "dream-checkpoint.json",
                sessions_counter=counter,
            )
            now = datetime.now(UTC)
            save_dream_checkpoint(
                tmp_path / "dream-checkpoint.json",
                AutoDreamCheckpoint(
                    last_dream_at=now - timedelta(hours=25),
                    sessions_since_last_dream=0,  # checkpoint says 0, counter says 99
                ),
            )
            decision = await runner.evaluate_gate(
                now=now,
                rate_limited=False,
                last_activity_at=None,
            )
            assert decision.should_run  # counter's 99 unblocked the sessions condition
        finally:
            await store.teardown()

    async def test_counter_exception_does_not_crash_gate(
        self,
        tmp_path: Path,
    ) -> None:
        store = DuckDBMindStore(db_path=tmp_path / "store.duckdb")
        await store.setup()
        try:
            reflector = Reflector(store=store)

            async def bad_counter() -> int:
                raise RuntimeError("counter died")

            runner = AutoDreamRunner(
                reflector=reflector,
                checkpoint_path=tmp_path / "dream-checkpoint.json",
                sessions_counter=bad_counter,
            )
            decision = await runner.evaluate_gate(
                now=datetime.now(UTC),
                rate_limited=False,
                last_activity_at=None,
            )
            # Gate still produced a verdict (false, because no checkpoint sessions).
            assert decision.should_run is False
        finally:
            await store.teardown()
