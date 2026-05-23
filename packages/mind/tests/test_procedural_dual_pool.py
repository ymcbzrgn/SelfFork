"""ADR-009 §3 T4 Procedural PROJECT/GLOBAL split — distiller routing tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from selffork_mind.memory.model import Note
from selffork_mind.memory.tiers.procedural import ProceduralDistiller
from selffork_mind.store.base import (
    GLOBAL_GROUP_ID,
    PoolScope,
    RetrieveConfig,
)
from selffork_mind.store.pool import PoolResolver

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ── helpers ────────────────────────────────────────────────────────────


def _decision(
    *,
    intent: str,
    content: str,
    when: datetime,
    project_slug: str | None,
    group_id: str | None = None,
    session_id: str | None = "sess-1",
) -> Note:
    return Note(
        tier="episodic",
        kind="decision",
        content=content,
        intent=intent,
        valid_from=when,
        project_slug=project_slug,
        group_id=group_id,
        session_id=session_id,
    )


def _tool_call(
    *,
    tool: str,
    when: datetime,
    project_slug: str | None,
    group_id: str | None = None,
    session_id: str | None = "sess-1",
) -> Note:
    return Note(
        tier="episodic",
        kind="pattern",
        content=f"tool:{tool}",
        intent=f"call:{tool}",
        valid_from=when,
        project_slug=project_slug,
        group_id=group_id,
        session_id=session_id,
    )


# ── PROJECT pool distiller (default — target_group_id=None) ────────────


class TestProjectPoolDistillation:
    async def test_default_distiller_writes_to_project_pool(
        self,
        tmp_path: Path,
    ) -> None:
        resolver = PoolResolver(project_slug="proj-a", home=tmp_path, embedding_dim=8)
        await resolver.setup()
        try:
            assert resolver._project is not None
            project_store = resolver._project.notes

            base = datetime.now(UTC) - timedelta(minutes=5)
            decisions = [
                _decision(
                    intent=f"lock embedder bge round{i}",
                    content=f"picked bge-m3 in round {i}",
                    when=base + timedelta(seconds=i),
                    project_slug="proj-a",
                    group_id="p:proj-a",
                    session_id=f"sess-{i}",
                )
                for i in range(2)
            ]
            await project_store.upsert_notes(decisions)

            distiller = ProceduralDistiller(store=project_store, min_theme_count=2)
            report = await distiller.distil(project_slug="proj-a")

            assert report.patterns_written > 0
            # Distilled patterns live in the project pool only.
            patterns = await resolver.retrieve(
                pool_scope=PoolScope(project_slug="proj-a"),
                config=RetrieveConfig(tiers=("procedural",)),
            )
            assert len(patterns) > 0
            global_patterns = await resolver.retrieve(
                pool_scope=PoolScope(include_global=True),
                config=RetrieveConfig(tiers=("procedural",)),
            )
            assert len(global_patterns) == 0
        finally:
            await resolver.teardown()


# ── GLOBAL pool distiller (target_group_id="g:global") ─────────────────


class TestGlobalPoolDistillation:
    """T4 GLOBAL — operator-style cross-project refleks distillation.

    The operator's identity refleks (e.g. "prefers single bundled PR") live
    in the GLOBAL pool. To distill them, the orchestrator constructs a
    distiller whose store is the GLOBAL engine and whose target_group_id
    is GLOBAL_GROUP_ID; the source Episodic events are the GLOBAL pool's
    Heartbeat ticks (workspace-less) plus any cross-project notes manually
    promoted.
    """

    async def test_global_target_stamps_group_id(self, tmp_path: Path) -> None:
        resolver = PoolResolver(project_slug=None, home=tmp_path, embedding_dim=8)
        await resolver.setup()
        try:
            global_store = resolver._global.notes

            # Seed GLOBAL pool with operator-style decision events.
            base = datetime.now(UTC) - timedelta(minutes=5)
            decisions = [
                _decision(
                    intent=f"prefer single bundled pr round{i}",
                    content=f"bundled the migration as one PR in iteration {i}",
                    when=base + timedelta(seconds=i),
                    project_slug=None,
                    group_id=GLOBAL_GROUP_ID,
                    session_id=f"global-sess-{i}",
                )
                for i in range(2)
            ]
            await global_store.upsert_notes(decisions)

            distiller = ProceduralDistiller(
                store=global_store,
                min_theme_count=2,
                target_group_id=GLOBAL_GROUP_ID,
            )
            report = await distiller.distil(project_slug=None)
            assert report.patterns_written > 0

            # All distilled patterns land in GLOBAL pool only.
            global_patterns = await resolver.retrieve(
                pool_scope=PoolScope(include_global=True),
                config=RetrieveConfig(tiers=("procedural",)),
            )
            assert len(global_patterns) == report.patterns_written
            for hit in global_patterns:
                assert hit.note.group_id == GLOBAL_GROUP_ID
        finally:
            await resolver.teardown()

    async def test_global_pool_isolated_from_project(self, tmp_path: Path) -> None:
        resolver = PoolResolver(project_slug="proj-a", home=tmp_path, embedding_dim=8)
        await resolver.setup()
        try:
            assert resolver._project is not None
            project_store = resolver._project.notes
            global_store = resolver._global.notes

            base = datetime.now(UTC) - timedelta(minutes=5)
            # Project-scoped decisions
            await project_store.upsert_notes(
                [
                    _decision(
                        intent=f"lock embedder bge slot{i}",
                        content=f"project pick number {i}",
                        when=base + timedelta(seconds=i),
                        project_slug="proj-a",
                        group_id="p:proj-a",
                        session_id=f"proj-sess-{i}",
                    )
                    for i in range(2)
                ],
            )
            # Global-scoped decisions
            await global_store.upsert_notes(
                [
                    _decision(
                        intent=f"prefer single bundled pr slot{i}",
                        content=f"cross-project habit number {i}",
                        when=base + timedelta(seconds=i + 10),
                        project_slug=None,
                        group_id=GLOBAL_GROUP_ID,
                        session_id=f"global-sess-{i}",
                    )
                    for i in range(2)
                ],
            )

            # Project distiller — only sees project-scope episodic.
            project_distiller = ProceduralDistiller(
                store=project_store,
                min_theme_count=2,
            )
            project_report = await project_distiller.distil(project_slug="proj-a")
            assert project_report.patterns_written > 0

            # Global distiller — only sees global-scope episodic.
            global_distiller = ProceduralDistiller(
                store=global_store,
                min_theme_count=2,
                target_group_id=GLOBAL_GROUP_ID,
            )
            global_report = await global_distiller.distil(project_slug=None)
            assert global_report.patterns_written > 0

            # Verify clean partition.
            project_hits = await resolver.retrieve(
                pool_scope=PoolScope(project_slug="proj-a"),
                config=RetrieveConfig(tiers=("procedural",)),
            )
            global_hits = await resolver.retrieve(
                pool_scope=PoolScope(include_global=True),
                config=RetrieveConfig(tiers=("procedural",)),
            )

            for hit in project_hits:
                assert hit.note.group_id == "p:proj-a"
            for hit in global_hits:
                assert hit.note.group_id == GLOBAL_GROUP_ID

            # No leakage either way.
            project_intents = {h.note.intent for h in project_hits}
            global_intents = {h.note.intent for h in global_hits}
            assert "theme:bundled" not in project_intents  # global term
            assert "theme:bge" not in global_intents  # project term
        finally:
            await resolver.teardown()


# ── Cross-pool retrieval ───────────────────────────────────────────────


class TestCrossPoolRetrieval:
    """Operator daily flow: project query + identity recall in one call."""

    async def test_include_global_unions_t4_patterns(self, tmp_path: Path) -> None:
        resolver = PoolResolver(project_slug="proj-a", home=tmp_path, embedding_dim=8)
        await resolver.setup()
        try:
            assert resolver._project is not None
            project_store = resolver._project.notes
            global_store = resolver._global.notes

            # Seed patterns in BOTH pools.
            project_pattern = Note(
                tier="procedural",
                kind="pattern",
                content='{"type": "sequence", "tool": "code_search"}',
                intent="sequence:project-tool",
                project_slug="proj-a",
                group_id="p:proj-a",
                importance=3.0,
            )
            global_pattern = Note(
                tier="procedural",
                kind="pattern",
                content='{"type": "identity", "preference": "single bundled PR"}',
                intent="theme:bundled",
                project_slug=None,
                group_id=GLOBAL_GROUP_ID,
                importance=3.5,
            )
            await project_store.upsert_note(project_pattern)
            await global_store.upsert_note(global_pattern)

            # Cross-pool query — should see BOTH patterns.
            both = await resolver.retrieve(
                pool_scope=PoolScope(project_slug="proj-a", include_global=True),
                config=RetrieveConfig(tiers=("procedural",), top_k=10),
            )
            intents = {h.note.intent for h in both}
            assert "sequence:project-tool" in intents
            assert "theme:bundled" in intents
        finally:
            await resolver.teardown()


# ── T6 Recall sanity (read-only audit JSONL) ───────────────────────────


class TestRecallReadOnly:
    """T6 Recall stays PROJECT-only per ADR-009 §3.

    Recall is read-only over the project's audit/ JSONL directory; no
    pool routing logic is required at this tier. We re-affirm the shape
    via a minimal smoke test.
    """

    def test_recall_module_imports(self) -> None:
        # Order 2 already delivered RecallReader production-quality;
        # ADR-009 only mandates "PROJECT only (read-only audit JSONL)".
        # We re-import here so a future rename surfaces immediately.
        from selffork_mind.memory.tiers.recall import RecallReader

        assert RecallReader is not None
