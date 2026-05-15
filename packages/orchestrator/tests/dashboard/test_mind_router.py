"""Integration tests for /api/projects/<slug>/mind/* endpoints — Order 3.

Real :class:`DuckDBMindStore` per request (no mocks). Tests stage
``project_slug`` directories under ``tmp_path`` and the dashboard's
mind_router opens its own per-request store at the canonical
``~/.selffork/projects/<slug>/mind/notes.duckdb`` path — we monkeypatch
the home directory so the test never touches the real ``~``.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import anyio
import pytest
from fastapi.testclient import TestClient

from selffork_mind.memory.model import Note
from selffork_orchestrator.dashboard.mind_deps import open_store
from selffork_orchestrator.dashboard.server import (
    DashboardConfig,
    build_app,
)


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect ``~/.selffork`` to ``tmp_path/home/.selffork`` for the test.

    The mind_router resolves the per-project store from
    ``Path("~/.selffork/projects").expanduser()`` so we have to control
    the home dir to avoid touching the operator's real Mind state.
    """
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    return home


def _client(tmp_path: Path) -> TestClient:
    config = DashboardConfig(
        audit_dir=tmp_path / "audit",
        resume_dir=tmp_path / "scheduled",
        projects_root=tmp_path / "projects",
        selffork_script=tmp_path / "fake-selffork",
    )
    config.audit_dir.mkdir(parents=True, exist_ok=True)
    config.resume_dir.mkdir(parents=True, exist_ok=True)
    config.projects_root.mkdir(parents=True, exist_ok=True)
    return TestClient(build_app(config))


def _seed_notes(slug: str, notes: list[Note]) -> None:
    """Seed real notes into the per-project DuckDB store."""

    async def _do() -> None:
        root = Path("~/.selffork/projects").expanduser() / slug / "mind"
        store = await open_store(root=root)
        try:
            await store.upsert_notes(notes)
        finally:
            await store.teardown()

    anyio.run(_do)


# ── /stats ───────────────────────────────────────────────────────────────────


class TestMindStats:
    def test_empty_project_returns_empty_tiers(
        self,
        tmp_path: Path,
        fake_home: Path,
    ) -> None:
        client = _client(tmp_path)
        r = client.get("/api/projects/calc/mind/stats")
        assert r.status_code == 200
        assert r.json() == {"tiers": {}}

    def test_returns_tier_counts(self, tmp_path: Path, fake_home: Path) -> None:
        _seed_notes(
            "calc",
            [
                Note(
                    tier="working",
                    kind="pointer",
                    content="w1",
                    project_slug="calc",
                ),
                Note(
                    tier="episodic",
                    kind="observation",
                    content="e1",
                    project_slug="calc",
                ),
                Note(
                    tier="episodic",
                    kind="observation",
                    content="e2",
                    project_slug="calc",
                ),
            ],
        )
        client = _client(tmp_path)
        r = client.get("/api/projects/calc/mind/stats")
        assert r.status_code == 200
        body = r.json()
        assert body["tiers"]["working"]["count"] == 1
        assert body["tiers"]["episodic"]["count"] == 2
        assert body["tiers"]["working"]["last_updated"] is not None


# ── /notes (list + detail) ───────────────────────────────────────────────────


class TestMindNotesList:
    def test_returns_only_project_scoped(
        self,
        tmp_path: Path,
        fake_home: Path,
    ) -> None:
        _seed_notes(
            "alpha",
            [
                Note(
                    tier="episodic",
                    kind="observation",
                    content="alpha-1",
                    project_slug="alpha",
                ),
            ],
        )
        _seed_notes(
            "beta",
            [
                Note(
                    tier="episodic",
                    kind="observation",
                    content="beta-1",
                    project_slug="beta",
                ),
            ],
        )
        client = _client(tmp_path)
        r = client.get("/api/projects/alpha/mind/notes")
        assert r.status_code == 200
        contents = {n["content"] for n in r.json()}
        assert contents == {"alpha-1"}

    def test_filter_by_tier(self, tmp_path: Path, fake_home: Path) -> None:
        _seed_notes(
            "p",
            [
                Note(
                    tier="working",
                    kind="pointer",
                    content="w",
                    project_slug="p",
                ),
                Note(
                    tier="episodic",
                    kind="observation",
                    content="e",
                    project_slug="p",
                ),
            ],
        )
        client = _client(tmp_path)
        r = client.get("/api/projects/p/mind/notes?tier=working")
        assert r.status_code == 200
        contents = [n["content"] for n in r.json()]
        assert contents == ["w"]

    def test_unknown_tier_400(self, tmp_path: Path, fake_home: Path) -> None:
        client = _client(tmp_path)
        r = client.get("/api/projects/p/mind/notes?tier=banana")
        assert r.status_code == 400


class TestMindNotesDetail:
    def test_returns_note_by_id(self, tmp_path: Path, fake_home: Path) -> None:
        note = Note(
            tier="episodic",
            kind="observation",
            content="hello",
            project_slug="calc",
        )
        _seed_notes("calc", [note])

        client = _client(tmp_path)
        r = client.get(f"/api/projects/calc/mind/notes/{note.id}")
        assert r.status_code == 200
        assert r.json()["content"] == "hello"
        assert r.json()["id"] == str(note.id)

    def test_unknown_returns_404(self, tmp_path: Path, fake_home: Path) -> None:
        client = _client(tmp_path)
        r = client.get(
            "/api/projects/calc/mind/notes/00000000-0000-0000-0000-000000000000",
        )
        assert r.status_code == 404

    def test_invalid_uuid_400(self, tmp_path: Path, fake_home: Path) -> None:
        client = _client(tmp_path)
        r = client.get("/api/projects/calc/mind/notes/not-a-uuid")
        assert r.status_code == 400

    def test_cross_project_access_404(
        self,
        tmp_path: Path,
        fake_home: Path,
    ) -> None:
        # Note seeded for project "alpha"; querying via "beta" must 404.
        note = Note(
            tier="episodic",
            kind="observation",
            content="alpha-secret",
            project_slug="alpha",
        )
        _seed_notes("alpha", [note])

        client = _client(tmp_path)
        r = client.get(f"/api/projects/beta/mind/notes/{note.id}")
        assert r.status_code == 404


# ── /notes (create + supersede) ──────────────────────────────────────────────


class TestMindNotesCreate:
    def test_creates_note_persisting_in_project_store(
        self,
        tmp_path: Path,
        fake_home: Path,
    ) -> None:
        client = _client(tmp_path)
        r = client.post(
            "/api/projects/calc/mind/notes",
            json={
                "content": "use BGE-M3 for embeddings",
                "tier": "reflection",
                "kind": "decision",
                "intent": "embedder choice",
                "tag_pairs": [["topic", "embedder"]],
            },
        )
        assert r.status_code == 201
        body = r.json()
        assert body["content"] == "use BGE-M3 for embeddings"
        assert body["tier"] == "reflection"
        assert body["project_slug"] == "calc"

        # On-disk side: the note appears in /stats.
        stats = client.get("/api/projects/calc/mind/stats").json()
        assert stats["tiers"]["reflection"]["count"] == 1

    def test_empty_content_400(self, tmp_path: Path, fake_home: Path) -> None:
        client = _client(tmp_path)
        r = client.post(
            "/api/projects/calc/mind/notes",
            json={"content": "   ", "tier": "episodic", "kind": "observation"},
        )
        assert r.status_code == 400

    def test_unknown_tier_400(self, tmp_path: Path, fake_home: Path) -> None:
        client = _client(tmp_path)
        r = client.post(
            "/api/projects/calc/mind/notes",
            json={"content": "hi", "tier": "banana", "kind": "observation"},
        )
        assert r.status_code == 400


class TestMindNotesSupersede:
    def test_delete_supersedes_note(
        self,
        tmp_path: Path,
        fake_home: Path,
    ) -> None:
        note = Note(
            tier="episodic",
            kind="observation",
            content="bye",
            project_slug="calc",
        )
        _seed_notes("calc", [note])

        client = _client(tmp_path)
        r = client.delete(f"/api/projects/calc/mind/notes/{note.id}")
        assert r.status_code == 204

        # Stats no longer count it.
        stats = client.get("/api/projects/calc/mind/stats").json()
        assert "episodic" not in stats["tiers"]

    def test_unknown_returns_404(self, tmp_path: Path, fake_home: Path) -> None:
        client = _client(tmp_path)
        r = client.delete(
            "/api/projects/calc/mind/notes/00000000-0000-0000-0000-000000000000",
        )
        assert r.status_code == 404


# ── /recall ──────────────────────────────────────────────────────────────────


class TestMindRecall:
    def test_returns_project_notes(
        self,
        tmp_path: Path,
        fake_home: Path,
    ) -> None:
        _seed_notes(
            "calc",
            [
                Note(
                    tier="episodic",
                    kind="observation",
                    content="alpha",
                    project_slug="calc",
                ),
                Note(
                    tier="episodic",
                    kind="observation",
                    content="beta",
                    project_slug="calc",
                ),
            ],
        )
        client = _client(tmp_path)
        r = client.post(
            "/api/projects/calc/mind/recall",
            json={"query": "anything", "top_k": 10},
        )
        assert r.status_code == 200
        body = r.json()
        contents = {h["content"] for h in body["hits"]}
        assert contents == {"alpha", "beta"}
        # Filter-only matches use the store's recency-weighted baseline
        # score (importance * recency-factor); we just assert positivity
        # because the absolute value depends on now() vs valid_from.
        assert len(body["scores"]) == 2
        assert all(s > 0 for s in body["scores"])

    def test_filter_by_tier(self, tmp_path: Path, fake_home: Path) -> None:
        _seed_notes(
            "calc",
            [
                Note(
                    tier="working",
                    kind="pointer",
                    content="w",
                    project_slug="calc",
                ),
                Note(
                    tier="episodic",
                    kind="observation",
                    content="e",
                    project_slug="calc",
                ),
            ],
        )
        client = _client(tmp_path)
        r = client.post(
            "/api/projects/calc/mind/recall",
            json={"query": "x", "tier": "working"},
        )
        assert r.status_code == 200
        assert [h["content"] for h in r.json()["hits"]] == ["w"]

    def test_top_k_clamp_400(self, tmp_path: Path, fake_home: Path) -> None:
        client = _client(tmp_path)
        r = client.post(
            "/api/projects/calc/mind/recall",
            json={"query": "x", "top_k": 0},
        )
        assert r.status_code == 400


# ── WS provenance stream ─────────────────────────────────────────────────────


class TestMindProvenanceStream:
    def test_streams_existing_then_appended(
        self,
        tmp_path: Path,
        fake_home: Path,
    ) -> None:
        log_path = (
            fake_home / ".selffork" / "projects" / "calc" / "mind"
            / "provenance.jsonl"
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # Pre-existing entries.
        for i in range(2):
            log_path.write_text(
                (log_path.read_text(encoding="utf-8") if log_path.is_file() else "")
                + json.dumps(
                    {
                        "ts": datetime.now(UTC).isoformat(),
                        "correlation_id": f"c{i}",
                        "session_id": f"s{i}",
                        "project_slug": "calc",
                        "query": f"q{i}",
                        "note_ids": [],
                        "scores": [],
                        "retriever": "hybrid",
                        "reranker": None,
                    },
                )
                + "\n",
                encoding="utf-8",
            )

        client = _client(tmp_path)
        with client.websocket_connect(
            "/api/projects/calc/mind/provenance/stream",
        ) as ws:
            # Phase 2 drain — receive the two pre-existing entries.
            first = json.loads(ws.receive_text())
            second = json.loads(ws.receive_text())
            assert first["event_type"] == "mind"
            assert first["seq"] == 1
            assert first["payload"]["query"] == "q0"
            assert second["seq"] == 2
            assert second["payload"]["query"] == "q1"

            # Append a third entry.
            with log_path.open("a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "ts": datetime.now(UTC).isoformat(),
                            "correlation_id": "c-new",
                            "session_id": "s-new",
                            "project_slug": "calc",
                            "query": "q-new",
                            "note_ids": [],
                            "scores": [],
                            "retriever": "hybrid",
                            "reranker": None,
                        },
                    )
                    + "\n",
                )

            third = json.loads(ws.receive_text())
            assert third["event_type"] == "mind"
            assert third["seq"] == 3
            assert third["payload"]["query"] == "q-new"


# Sanity: the helpers we import must accept anyio.run sync invocation.
def test_anyio_run_smoke() -> None:
    async def _do() -> int:
        await asyncio.sleep(0)
        return 42

    assert anyio.run(_do) == 42
