"""Integration tests for the Talk router — S1 Talk Loop.

Real :class:`TalkStore` on tmp_path (no mocks). The Speaker is a small
in-process fake so the router is exercised end-to-end without a model
endpoint — the same way the production router degrades when the
operator's model is offline.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient

from selffork_orchestrator.dashboard.server import DashboardConfig, build_app
from selffork_orchestrator.dashboard.talk_router import build_talk_router
from selffork_orchestrator.talk.speaker import Speaker
from selffork_shared.errors import RuntimeUnhealthyError


class _EchoSpeaker:
    """Fake Speaker — echoes the operator's last message back as a reply."""

    async def reply(self, messages: Sequence[Mapping[str, str]]) -> str:
        last_user = next(
            (m["content"] for m in reversed(list(messages)) if m["role"] == "user"),
            "",
        )
        return f"echo: {last_user}"


class _OfflineSpeaker:
    """Fake Speaker that always fails as if the endpoint were down."""

    async def reply(self, messages: Sequence[Mapping[str, str]]) -> str:
        raise RuntimeUnhealthyError("endpoint unreachable")


def _client(tmp_path: Path, speaker: Speaker | None) -> TestClient:
    app = FastAPI()
    app.include_router(
        build_talk_router(
            talk_db_path=tmp_path / "talk" / "conversations.db",
            speaker=speaker,
        ),
    )
    return TestClient(app)


# ── Send ─────────────────────────────────────────────────────────────────────


class TestSend:
    def test_creates_conversation_and_replies(self, tmp_path: Path) -> None:
        client = _client(tmp_path, _EchoSpeaker())
        r = client.post("/api/talk/send", json={"text": "hello jr"})
        assert r.status_code == 201
        body = r.json()
        assert body["conversation_id"]
        assert body["operator_message"]["role"] == "operator"
        assert body["operator_message"]["content"] == "hello jr"
        assert body["operator_message"]["seq"] == 1
        assert body["reply"]["role"] == "self_jr"
        assert body["reply"]["content"] == "echo: hello jr"
        assert body["reply"]["seq"] == 2
        assert body["speaker_status"] == "ok"

    def test_continues_existing_conversation(self, tmp_path: Path) -> None:
        client = _client(tmp_path, _EchoSpeaker())
        cid = client.post(
            "/api/talk/send", json={"text": "one"}
        ).json()["conversation_id"]
        client.post(
            "/api/talk/send",
            json={"conversation_id": cid, "text": "two"},
        )
        thread = client.get(f"/api/talk/conversations/{cid}").json()
        contents = [m["content"] for m in thread["messages"]]
        assert contents == ["one", "echo: one", "two", "echo: two"]

    def test_empty_text_400(self, tmp_path: Path) -> None:
        client = _client(tmp_path, _EchoSpeaker())
        r = client.post("/api/talk/send", json={"text": "   "})
        assert r.status_code == 400

    def test_unknown_conversation_404(self, tmp_path: Path) -> None:
        client = _client(tmp_path, _EchoSpeaker())
        r = client.post(
            "/api/talk/send",
            json={
                "conversation_id": "00000000-0000-0000-0000-000000000000",
                "text": "hi",
            },
        )
        assert r.status_code == 404

    def test_invalid_conversation_id_400(self, tmp_path: Path) -> None:
        client = _client(tmp_path, _EchoSpeaker())
        r = client.post(
            "/api/talk/send",
            json={"conversation_id": "not-a-uuid", "text": "hi"},
        )
        assert r.status_code == 400

    def test_speaker_offline_persists_operator_message(
        self,
        tmp_path: Path,
    ) -> None:
        client = _client(tmp_path, _OfflineSpeaker())
        r = client.post("/api/talk/send", json={"text": "anyone there"})
        assert r.status_code == 201
        body = r.json()
        assert body["operator_message"]["content"] == "anyone there"
        assert body["reply"] is None
        assert body["speaker_status"] == "offline"
        # The operator message survives even though the Speaker failed.
        thread = client.get(
            f"/api/talk/conversations/{body['conversation_id']}",
        ).json()
        assert [m["content"] for m in thread["messages"]] == ["anyone there"]

    def test_no_speaker_reports_not_configured(self, tmp_path: Path) -> None:
        client = _client(tmp_path, None)
        body = client.post("/api/talk/send", json={"text": "hi"}).json()
        assert body["reply"] is None
        assert body["speaker_status"] == "not_configured"


# ── Conversations ─────────────────────────────────────────────────────────────


class TestConversations:
    def test_list_empty(self, tmp_path: Path) -> None:
        client = _client(tmp_path, _EchoSpeaker())
        r = client.get("/api/talk/conversations")
        assert r.status_code == 200
        assert r.json() == []

    def test_list_after_send(self, tmp_path: Path) -> None:
        client = _client(tmp_path, _EchoSpeaker())
        client.post(
            "/api/talk/send",
            json={"text": "hi", "workspace": "proj-x"},
        )
        listed = client.get("/api/talk/conversations").json()
        assert len(listed) == 1
        assert listed[0]["workspace_slug"] == "proj-x"
        assert listed[0]["title"] == "hi"

    def test_get_thread(self, tmp_path: Path) -> None:
        client = _client(tmp_path, _EchoSpeaker())
        cid = client.post(
            "/api/talk/send", json={"text": "ping"}
        ).json()["conversation_id"]
        r = client.get(f"/api/talk/conversations/{cid}")
        assert r.status_code == 200
        body = r.json()
        assert body["conversation"]["id"] == cid
        assert [m["content"] for m in body["messages"]] == [
            "ping",
            "echo: ping",
        ]

    def test_get_invalid_id_400(self, tmp_path: Path) -> None:
        client = _client(tmp_path, _EchoSpeaker())
        r = client.get("/api/talk/conversations/not-a-uuid")
        assert r.status_code == 400

    def test_get_unknown_404(self, tmp_path: Path) -> None:
        client = _client(tmp_path, _EchoSpeaker())
        r = client.get(
            "/api/talk/conversations/00000000-0000-0000-0000-000000000000",
        )
        assert r.status_code == 404


# ── WS stream ─────────────────────────────────────────────────────────────────


class TestStream:
    def test_streams_drained_and_live_messages(self, tmp_path: Path) -> None:
        client = _client(tmp_path, _EchoSpeaker())
        cid = client.post(
            "/api/talk/send", json={"text": "first"}
        ).json()["conversation_id"]
        # Conversation already holds operator "first" + self_jr "echo: first".
        with client.websocket_connect(f"/api/talk/{cid}/stream") as ws:
            env1 = json.loads(ws.receive_text())
            assert env1["event_type"] == "talk.message"
            assert env1["seq"] == 1
            assert env1["payload"]["role"] == "operator"
            assert env1["payload"]["content"] == "first"

            env2 = json.loads(ws.receive_text())
            assert env2["payload"]["role"] == "self_jr"
            assert env2["payload"]["content"] == "echo: first"

            # A fresh send must surface live (Phase 2 poll).
            client.post(
                "/api/talk/send",
                json={"conversation_id": cid, "text": "second"},
            )
            env3 = json.loads(ws.receive_text())
            assert env3["payload"]["content"] == "second"
            env4 = json.loads(ws.receive_text())
            assert env4["payload"]["content"] == "echo: second"

    def test_unknown_conversation_closes(self, tmp_path: Path) -> None:
        client = _client(tmp_path, _EchoSpeaker())
        with (
            pytest.raises(WebSocketDisconnect),
            client.websocket_connect(
                "/api/talk/00000000-0000-0000-0000-000000000000/stream",
            ) as ws,
        ):
            ws.receive_text()

    def test_invalid_conversation_id_closes(self, tmp_path: Path) -> None:
        client = _client(tmp_path, _EchoSpeaker())
        with (
            pytest.raises(WebSocketDisconnect),
            client.websocket_connect("/api/talk/not-a-uuid/stream") as ws,
        ):
            ws.receive_text()

    def test_reconnect_resyncs_thread(self, tmp_path: Path) -> None:
        client = _client(tmp_path, _EchoSpeaker())
        cid = client.post(
            "/api/talk/send", json={"text": "first"}
        ).json()["conversation_id"]
        # First connection drains the thread, then closes.
        with client.websocket_connect(f"/api/talk/{cid}/stream") as ws:
            ws.receive_text()
            ws.receive_text()
        # A fresh reconnect must re-sync the persisted thread.
        with client.websocket_connect(f"/api/talk/{cid}/stream") as ws:
            replayed = [
                json.loads(ws.receive_text())["payload"]["content"]
                for _ in range(2)
            ]
        assert "first" in replayed
        assert "echo: first" in replayed


# ── Build-app wiring ──────────────────────────────────────────────────────────


class TestWiring:
    def test_talk_router_mounted_on_full_app(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("SELFFORK_TALK_MODEL_ENDPOINT", raising=False)
        config = DashboardConfig(
            audit_dir=tmp_path / "audit",
            resume_dir=tmp_path / "scheduled",
            projects_root=tmp_path / "projects",
            selffork_script=tmp_path / "fake-selffork",
            talk_db_path=tmp_path / "talk" / "conversations.db",
        )
        for directory in (
            config.audit_dir,
            config.resume_dir,
            config.projects_root,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        client = TestClient(build_app(config))

        assert client.get("/api/talk/conversations").json() == []
        # No model endpoint in the environment ⇒ honest not_configured.
        sent = client.post("/api/talk/send", json={"text": "hi"})
        assert sent.status_code == 201
        assert sent.json()["speaker_status"] == "not_configured"
