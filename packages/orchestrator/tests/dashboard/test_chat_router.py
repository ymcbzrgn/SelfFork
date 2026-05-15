"""Integration tests for /api/sessions/<id>/chat endpoints — Order 4.

Real :class:`BranchStore` per test (no mocks). The fake home dir
fixture redirects ``~`` so the chat DB lands under ``tmp_path``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from selffork_orchestrator.dashboard.server import (
    DashboardConfig,
    build_app,
)


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
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
        chat_db_path=tmp_path / "chat" / "branches.db",
    )
    config.audit_dir.mkdir(parents=True, exist_ok=True)
    config.resume_dir.mkdir(parents=True, exist_ok=True)
    config.projects_root.mkdir(parents=True, exist_ok=True)
    return TestClient(build_app(config))


# ── Messages ─────────────────────────────────────────────────────────────────


class TestPostMessage:
    def test_seeds_main_branch_on_first_message(
        self,
        tmp_path: Path,
        fake_home: Path,
    ) -> None:
        client = _client(tmp_path)
        r = client.post(
            "/api/sessions/sess-1/messages",
            json={"content": "hello", "role": "user"},
        )
        assert r.status_code == 201
        body = r.json()
        assert body["content"] == "hello"
        assert body["role"] == "user"
        # Branch was minted automatically.
        branches = client.get("/api/sessions/sess-1/branches").json()
        assert len(branches) == 1
        assert branches[0]["label"] == "main"
        assert branches[0]["is_active"] is True

    def test_default_role_is_user(
        self,
        tmp_path: Path,
        fake_home: Path,
    ) -> None:
        client = _client(tmp_path)
        r = client.post(
            "/api/sessions/sess-1/messages",
            json={"content": "hi"},
        )
        assert r.status_code == 201
        assert r.json()["role"] == "user"

    def test_invalid_role_400(
        self,
        tmp_path: Path,
        fake_home: Path,
    ) -> None:
        client = _client(tmp_path)
        r = client.post(
            "/api/sessions/sess-1/messages",
            json={"content": "x", "role": "banana"},
        )
        assert r.status_code == 400

    def test_empty_content_400(
        self,
        tmp_path: Path,
        fake_home: Path,
    ) -> None:
        client = _client(tmp_path)
        r = client.post(
            "/api/sessions/sess-1/messages",
            json={"content": "   "},
        )
        assert r.status_code == 400


class TestListMessages:
    def test_returns_active_branch_messages(
        self,
        tmp_path: Path,
        fake_home: Path,
    ) -> None:
        client = _client(tmp_path)
        client.post(
            "/api/sessions/sess-1/messages",
            json={"content": "m1"},
        )
        client.post(
            "/api/sessions/sess-1/messages",
            json={"content": "m2", "role": "assistant"},
        )
        r = client.get("/api/sessions/sess-1/messages")
        assert r.status_code == 200
        contents = [m["content"] for m in r.json()]
        assert contents == ["m1", "m2"]

    def test_filter_by_branch(
        self,
        tmp_path: Path,
        fake_home: Path,
    ) -> None:
        client = _client(tmp_path)
        client.post(
            "/api/sessions/sess-1/messages",
            json={"content": "main-1"},
        )
        first_msg = client.post(
            "/api/sessions/sess-1/messages",
            json={"content": "main-2"},
        ).json()

        # Edit forks a new branch.
        new_branch = client.post(
            f"/api/sessions/sess-1/messages/{first_msg['id']}/edit",
            json={"content": "edited"},
        ).json()
        # Default ``GET`` returns the active (newly-forked) branch.
        active = client.get("/api/sessions/sess-1/messages").json()
        active_contents = [m["content"] for m in active]
        # Prefix copied + edited message appended.
        assert "edited" in active_contents

        # Original branch — pass branch_id explicitly.
        first_branch_id = next(
            b["id"]
            for b in client.get("/api/sessions/sess-1/branches").json()
            if b["id"] != new_branch["id"]
        )
        r = client.get(
            f"/api/sessions/sess-1/messages?branch_id={first_branch_id}",
        )
        contents = [m["content"] for m in r.json()]
        assert contents == ["main-1", "main-2"]

    def test_unknown_session_returns_empty(
        self,
        tmp_path: Path,
        fake_home: Path,
    ) -> None:
        client = _client(tmp_path)
        r = client.get("/api/sessions/never/messages")
        assert r.status_code == 200
        assert r.json() == []


# ── Edit / Branching ─────────────────────────────────────────────────────────


class TestEditMessage:
    def test_edit_creates_new_active_branch(
        self,
        tmp_path: Path,
        fake_home: Path,
    ) -> None:
        client = _client(tmp_path)
        msg = client.post(
            "/api/sessions/sess-1/messages",
            json={"content": "original"},
        ).json()
        r = client.post(
            f"/api/sessions/sess-1/messages/{msg['id']}/edit",
            json={"content": "rewritten"},
        )
        assert r.status_code == 201
        new_branch = r.json()
        assert new_branch["fork_message_id"] == msg["id"]
        assert new_branch["is_active"] is True

        # Active branch's last message is the edit.
        active_msgs = client.get("/api/sessions/sess-1/messages").json()
        assert active_msgs[-1]["content"] == "rewritten"

    def test_edit_uses_custom_label(
        self,
        tmp_path: Path,
        fake_home: Path,
    ) -> None:
        client = _client(tmp_path)
        msg = client.post(
            "/api/sessions/sess-1/messages",
            json={"content": "x"},
        ).json()
        r = client.post(
            f"/api/sessions/sess-1/messages/{msg['id']}/edit",
            json={"content": "y", "branch_label": "exploration-1"},
        )
        assert r.json()["label"] == "exploration-1"

    def test_unknown_message_404(
        self,
        tmp_path: Path,
        fake_home: Path,
    ) -> None:
        client = _client(tmp_path)
        r = client.post(
            "/api/sessions/sess-1/messages/00000000-0000-0000-0000-000000000000/edit",
            json={"content": "x"},
        )
        assert r.status_code == 404

    def test_invalid_message_id_400(
        self,
        tmp_path: Path,
        fake_home: Path,
    ) -> None:
        client = _client(tmp_path)
        r = client.post(
            "/api/sessions/sess-1/messages/not-a-uuid/edit",
            json={"content": "x"},
        )
        assert r.status_code == 400


class TestBranches:
    def test_list_orders_by_created_at(
        self,
        tmp_path: Path,
        fake_home: Path,
    ) -> None:
        client = _client(tmp_path)
        msg = client.post(
            "/api/sessions/sess-1/messages",
            json={"content": "a"},
        ).json()
        client.post(
            f"/api/sessions/sess-1/messages/{msg['id']}/edit",
            json={"content": "b"},
        )
        client.post(
            f"/api/sessions/sess-1/messages/{msg['id']}/edit",
            json={"content": "c"},
        )
        branches = client.get("/api/sessions/sess-1/branches").json()
        assert next(b["label"] for b in branches) == "main"
        assert len(branches) == 3

    def test_set_active_branch_round_trip(
        self,
        tmp_path: Path,
        fake_home: Path,
    ) -> None:
        client = _client(tmp_path)
        msg = client.post(
            "/api/sessions/sess-1/messages",
            json={"content": "hi"},
        ).json()
        client.post(
            f"/api/sessions/sess-1/messages/{msg['id']}/edit",
            json={"content": "alt"},
        )
        branches = client.get("/api/sessions/sess-1/branches").json()
        main_id = next(b["id"] for b in branches if b["label"] == "main")
        r = client.patch(
            "/api/sessions/sess-1/active-branch",
            json={"branch_id": main_id},
        )
        assert r.status_code == 200
        assert r.json()["id"] == main_id
        assert r.json()["is_active"] is True

    def test_active_branch_unknown_404(
        self,
        tmp_path: Path,
        fake_home: Path,
    ) -> None:
        client = _client(tmp_path)
        r = client.patch(
            "/api/sessions/sess-1/active-branch",
            json={"branch_id": "00000000-0000-0000-0000-000000000000"},
        )
        assert r.status_code == 404


# ── WS chat stream ───────────────────────────────────────────────────────────


class TestChatStream:
    def test_emits_envelope_for_appended_message(
        self,
        tmp_path: Path,
        fake_home: Path,
    ) -> None:
        client = _client(tmp_path)
        # Seed one message before the WS opens so the Phase 1 drain
        # surfaces it.
        client.post(
            "/api/sessions/sess-1/messages",
            json={"content": "first"},
        )
        with client.websocket_connect(
            "/api/sessions/sess-1/chat/stream",
        ) as ws:
            first = json.loads(ws.receive_text())
            assert first["event_type"] == "chat.token"
            assert first["session_id"] == "sess-1"
            assert first["payload"]["content"] == "first"
            assert first["seq"] == 1

            # Append another message — Phase 2 must surface it.
            client.post(
                "/api/sessions/sess-1/messages",
                json={"content": "second"},
            )
            second = json.loads(ws.receive_text())
            assert second["payload"]["content"] == "second"
            assert second["seq"] == 2
