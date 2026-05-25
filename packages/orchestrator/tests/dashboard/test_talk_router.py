"""Integration tests for the Talk router — S1 Talk Loop + S-Stream (ADR-011).

Real :class:`TalkStore` on tmp_path (no mocks). The Speaker is a small
in-process fake so the router is exercised end-to-end without a model
endpoint — the same way the production router degrades when the
operator's model is offline.

Under S-Stream the router no longer holds the POST open for the
generation — ``/send`` returns ``speaker_status="streaming"`` plus a
``generation_id`` and the reply (or error / cancelled marker) arrives
over the Talk WebSocket asynchronously, driven by an
``asyncio.create_task`` background task.

**Why the context-managed client matters.** A background task only makes
progress while its event loop runs. Starlette's ``TestClient`` spins a
throwaway loop *per request* unless it's entered as a context manager,
in which case it keeps ONE persistent loop alive (in a portal thread)
for the whole block. The ``make_client`` fixture below enters the client
so ``POST /send`` → ``asyncio.create_task`` → token stream actually
progresses; otherwise the task is orphaned and the reply never lands.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from pathlib import Path

import pytest
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient

from selffork_orchestrator.dashboard.server import DashboardConfig, build_app
from selffork_orchestrator.dashboard.talk_router import build_talk_router
from selffork_orchestrator.dashboard.ws_protocol import ReplayRegistry
from selffork_orchestrator.talk.speaker import (
    Speaker,
    StreamDone,
    StreamEvent,
    TokenChunk,
)
from selffork_shared.errors import RuntimeUnhealthyError, SpeakerStalledError

# ── Test speakers ───────────────────────────────────────────────────────────


def _last_user(messages: Sequence[Mapping[str, str]]) -> str:
    return next(
        (m["content"] for m in reversed(list(messages)) if m["role"] == "user"),
        "",
    )


class _EchoSpeaker:
    """Echoes the operator's last message back as a reply.

    Implements the full :class:`Speaker` Protocol — ``reply()`` (legacy
    back-compat surface kept for any caller that prefers a one-shot
    accumulate) AND ``reply_stream()`` (the path the Talk router drives
    under ADR-011). The stream yields one token per word to exercise the
    multi-chunk path in the broadcaster.
    """

    async def reply(self, messages: Sequence[Mapping[str, str]]) -> str:
        return f"echo: {_last_user(messages)}"

    async def reply_stream(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        stall_seconds: float | None = None,
    ) -> AsyncIterator[StreamEvent]:
        full = f"echo: {_last_user(messages)}"
        for piece in full.split(" "):
            yield TokenChunk(text=piece + " ")
        yield StreamDone(full_reply=full, finish_reason="stop")


class _OfflineSpeaker:
    """Always fails as if the endpoint were down."""

    async def reply(self, messages: Sequence[Mapping[str, str]]) -> str:
        raise RuntimeUnhealthyError("endpoint unreachable")

    async def reply_stream(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        stall_seconds: float | None = None,
    ) -> AsyncIterator[StreamEvent]:
        raise RuntimeUnhealthyError("endpoint unreachable")
        yield  # pragma: no cover — unreachable; makes this an async gen


class _SlowSpeaker:
    """Streams tokens with a controllable pause — used to test cancel."""

    def __init__(self, *, per_token_seconds: float, token_count: int) -> None:
        self._per_token = per_token_seconds
        self._token_count = token_count

    async def reply(self, messages: Sequence[Mapping[str, str]]) -> str:
        return "x" * self._token_count

    async def reply_stream(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        stall_seconds: float | None = None,
    ) -> AsyncIterator[StreamEvent]:
        chunks: list[str] = []
        for _ in range(self._token_count):
            await asyncio.sleep(self._per_token)
            chunks.append("x")
            yield TokenChunk(text="x")
        yield StreamDone(full_reply="".join(chunks), finish_reason="stop")


class _StalledSpeaker:
    """Yields one token then raises :class:`SpeakerStalledError`."""

    async def reply(self, messages: Sequence[Mapping[str, str]]) -> str:
        raise SpeakerStalledError("no tokens for 90s — wedged")

    async def reply_stream(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        stall_seconds: float | None = None,
    ) -> AsyncIterator[StreamEvent]:
        yield TokenChunk(text="half")
        raise SpeakerStalledError("no tokens for 90s — wedged")


# ── Fixtures ────────────────────────────────────────────────────────────────


type ClientFactory = Callable[[Speaker | None], TestClient]


@pytest.fixture
def make_client(tmp_path: Path) -> AsyncIterator[ClientFactory]:
    """Factory for context-managed TestClients (one persistent loop each).

    Entering the TestClient as a context manager keeps a single event
    loop alive for the whole test so ``POST /send``'s background
    generation task actually runs. Each client gets its own
    ``ReplayRegistry`` so the bounded replay buffer is isolated between
    test cases (the module-global :func:`default_registry` would
    otherwise leak talk envelopes across tests). Teardown cancels any
    in-flight generation on the portal loop before exit.
    """
    entered: list[tuple[TestClient, object]] = []

    def _factory(speaker: Speaker | None) -> TestClient:
        app = FastAPI()
        router = build_talk_router(
            talk_db_path=tmp_path / "talk" / "conversations.db",
            speaker=speaker,
            registry=ReplayRegistry(),
        )
        app.include_router(router)
        tc = TestClient(app)
        tc.__enter__()
        entered.append((tc, router.state))  # type: ignore[attr-defined]
        return tc

    yield _factory  # type: ignore[misc]

    for tc, state in entered:
        # Cancel in-flight streaming tasks on the portal's loop before
        # closing the client (avoids "Task was destroyed but pending").
        with contextlib.suppress(Exception):
            tc.portal.call(state.teardown)  # type: ignore[attr-defined]
        tc.__exit__(None, None, None)


def _wait_for_messages(
    client: TestClient,
    conversation_id: str,
    expected_count: int,
    *,
    timeout_seconds: float = 5.0,
) -> list[dict[str, object]]:
    """Poll the conversation thread until ``expected_count`` messages.

    Replaces the original synchronous-reply assertion pattern: under
    streaming the assistant message lands when the background task
    persists it, so the test waits for the store to reach that state.
    """
    deadline = time.monotonic() + timeout_seconds
    last_messages: list[dict[str, object]] = []
    while time.monotonic() < deadline:
        thread = client.get(
            f"/api/talk/conversations/{conversation_id}"
        ).json()
        last_messages = thread["messages"]
        if len(last_messages) >= expected_count:
            return last_messages
        time.sleep(0.02)
    msg = (
        f"timed out waiting for {expected_count} messages on {conversation_id}; "
        f"observed {len(last_messages)}: {last_messages!r}"
    )
    raise AssertionError(msg)


def _drain_until_event(
    ws: object,
    target_event_type: str,
    *,
    max_envelopes: int = 200,
    timeout_seconds: float = 5.0,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Receive frames until one of ``target_event_type`` arrives.

    Returns ``(preceding_envelopes, target_envelope)``. Raises on
    receiving more than ``max_envelopes`` or after ``timeout_seconds``.
    """
    deadline = time.monotonic() + timeout_seconds
    preceding: list[dict[str, object]] = []
    for _ in range(max_envelopes):
        if time.monotonic() > deadline:
            raise AssertionError(
                f"timed out waiting for {target_event_type}; "
                f"saw {[e['event_type'] for e in preceding]}"
            )
        env = json.loads(ws.receive_text())  # type: ignore[attr-defined]
        if env.get("event_type") == target_event_type:
            return preceding, env
        preceding.append(env)
    msg = (
        f"received {max_envelopes} envelopes without {target_event_type}; "
        f"types: {[e['event_type'] for e in preceding]}"
    )
    raise AssertionError(msg)


# ── Send ─────────────────────────────────────────────────────────────────────


class TestSend:
    def test_send_returns_streaming_immediately(
        self, make_client: ClientFactory
    ) -> None:
        """POST returns before the background generation persists."""
        client = make_client(_EchoSpeaker())
        r = client.post("/api/talk/send", json={"text": "hello jr"})
        assert r.status_code == 201
        body = r.json()
        assert body["conversation_id"]
        assert body["operator_message"]["role"] == "operator"
        assert body["operator_message"]["content"] == "hello jr"
        assert body["operator_message"]["seq"] == 1
        # ADR-011: the reply is *not* in the POST response.
        assert body["reply"] is None
        assert body["speaker_status"] == "streaming"
        assert isinstance(body["generation_id"], str)
        assert len(body["generation_id"]) > 0

    def test_reply_persists_via_background_task(
        self, make_client: ClientFactory
    ) -> None:
        """The streamed reply eventually lands on disk."""
        client = make_client(_EchoSpeaker())
        cid = client.post(
            "/api/talk/send", json={"text": "hello jr"}
        ).json()["conversation_id"]
        messages = _wait_for_messages(client, cid, expected_count=2)
        assert [m["content"] for m in messages] == [
            "hello jr",
            "echo: hello jr",
        ]
        assert messages[1]["role"] == "self_jr"
        assert messages[1]["seq"] == 2

    def test_continues_existing_conversation(
        self, make_client: ClientFactory
    ) -> None:
        client = make_client(_EchoSpeaker())
        cid = client.post(
            "/api/talk/send", json={"text": "one"}
        ).json()["conversation_id"]
        _wait_for_messages(client, cid, expected_count=2)
        client.post(
            "/api/talk/send",
            json={"conversation_id": cid, "text": "two"},
        )
        messages = _wait_for_messages(client, cid, expected_count=4)
        contents = [m["content"] for m in messages]
        assert contents == ["one", "echo: one", "two", "echo: two"]

    def test_empty_text_400(self, make_client: ClientFactory) -> None:
        client = make_client(_EchoSpeaker())
        r = client.post("/api/talk/send", json={"text": "   "})
        assert r.status_code == 400

    def test_unknown_conversation_404(self, make_client: ClientFactory) -> None:
        client = make_client(_EchoSpeaker())
        r = client.post(
            "/api/talk/send",
            json={
                "conversation_id": "00000000-0000-0000-0000-000000000000",
                "text": "hi",
            },
        )
        assert r.status_code == 404

    def test_invalid_conversation_id_400(
        self, make_client: ClientFactory
    ) -> None:
        client = make_client(_EchoSpeaker())
        r = client.post(
            "/api/talk/send",
            json={"conversation_id": "not-a-uuid", "text": "hi"},
        )
        assert r.status_code == 400

    def test_speaker_offline_persists_operator_message(
        self,
        make_client: ClientFactory,
    ) -> None:
        """Operator message survives even when the Speaker fails."""
        client = make_client(_OfflineSpeaker())
        r = client.post("/api/talk/send", json={"text": "anyone there"})
        assert r.status_code == 201
        body = r.json()
        assert body["operator_message"]["content"] == "anyone there"
        assert body["reply"] is None
        # Under S-Stream the POST returns "streaming" even when the
        # speaker will fail — the failure surfaces as a talk.error
        # envelope on the WS.
        assert body["speaker_status"] == "streaming"
        assert body["generation_id"]
        cid = body["conversation_id"]
        # Wait for the failing task to settle — poll a few times.
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            thread = client.get(f"/api/talk/conversations/{cid}").json()
            if len(thread["messages"]) == 1:
                time.sleep(0.05)
                continue
            break
        thread = client.get(f"/api/talk/conversations/{cid}").json()
        # Only the operator message — no fabricated reply.
        assert [m["content"] for m in thread["messages"]] == ["anyone there"]

    def test_no_speaker_reports_not_configured(
        self, make_client: ClientFactory
    ) -> None:
        client = make_client(None)
        body = client.post("/api/talk/send", json={"text": "hi"}).json()
        assert body["reply"] is None
        assert body["speaker_status"] == "not_configured"
        assert body["generation_id"] is None


# ── Conversations ─────────────────────────────────────────────────────────────


class TestConversations:
    def test_list_empty(self, make_client: ClientFactory) -> None:
        client = make_client(_EchoSpeaker())
        r = client.get("/api/talk/conversations")
        assert r.status_code == 200
        assert r.json() == []

    def test_list_after_send(self, make_client: ClientFactory) -> None:
        client = make_client(_EchoSpeaker())
        client.post(
            "/api/talk/send",
            json={"text": "hi", "workspace": "proj-x"},
        )
        listed = client.get("/api/talk/conversations").json()
        assert len(listed) == 1
        assert listed[0]["workspace_slug"] == "proj-x"
        assert listed[0]["title"] == "hi"

    def test_get_thread(self, make_client: ClientFactory) -> None:
        client = make_client(_EchoSpeaker())
        cid = client.post(
            "/api/talk/send", json={"text": "ping"}
        ).json()["conversation_id"]
        _wait_for_messages(client, cid, expected_count=2)
        r = client.get(f"/api/talk/conversations/{cid}")
        assert r.status_code == 200
        body = r.json()
        assert body["conversation"]["id"] == cid
        assert [m["content"] for m in body["messages"]] == [
            "ping",
            "echo: ping",
        ]

    def test_get_invalid_id_400(self, make_client: ClientFactory) -> None:
        client = make_client(_EchoSpeaker())
        r = client.get("/api/talk/conversations/not-a-uuid")
        assert r.status_code == 400

    def test_get_unknown_404(self, make_client: ClientFactory) -> None:
        client = make_client(_EchoSpeaker())
        r = client.get(
            "/api/talk/conversations/00000000-0000-0000-0000-000000000000",
        )
        assert r.status_code == 404


# ── WS streaming envelopes ───────────────────────────────────────────────────


class TestStream:
    def test_token_envelopes_then_message(
        self, make_client: ClientFactory
    ) -> None:
        """Each chunk is a ``talk.token`` framed by the final ``talk.message``."""
        client = make_client(_EchoSpeaker())
        cid = client.post(
            "/api/talk/send", json={"text": "stream test"}
        ).json()["conversation_id"]
        with client.websocket_connect(f"/api/talk/{cid}/stream") as ws:
            # Replay: operator message first.
            op_env = json.loads(ws.receive_text())
            assert op_env["event_type"] == "talk.message"
            assert op_env["payload"]["role"] == "operator"
            assert op_env["payload"]["content"] == "stream test"
            # Live: token envelopes from the streaming task; the
            # streamer's text-to-tokens fanout produces multiple
            # `talk.token`s before the final `talk.message`.
            tokens, message_env = _drain_until_event(ws, "talk.message")
            assert all(t["event_type"] == "talk.token" for t in tokens)
            assert tokens, "expected ≥1 talk.token before the final message"
            joined = "".join(str(t["payload"]["text"]) for t in tokens)
            assert "echo: stream test" in joined
            assert message_env["payload"]["role"] == "self_jr"
            assert message_env["payload"]["content"] == "echo: stream test"
            # Every token carries the same generation_id as the final
            # message — lets the cockpit dedup across reconnect.
            gid = str(message_env["payload"]["generation_id"])
            assert all(
                str(t["payload"]["generation_id"]) == gid for t in tokens
            )

    def test_speaker_offline_emits_error_envelope(
        self, make_client: ClientFactory
    ) -> None:
        client = make_client(_OfflineSpeaker())
        cid = client.post(
            "/api/talk/send", json={"text": "ring ring"}
        ).json()["conversation_id"]
        with client.websocket_connect(f"/api/talk/{cid}/stream") as ws:
            # Operator message first.
            op_env = json.loads(ws.receive_text())
            assert op_env["payload"]["role"] == "operator"
            # Then talk.error.
            _, error_env = _drain_until_event(ws, "talk.error")
            assert error_env["payload"]["kind"] == "unhealthy"
            assert "unreachable" in str(error_env["payload"]["detail"])

    def test_speaker_stalled_emits_stalled_error(
        self, make_client: ClientFactory
    ) -> None:
        client = make_client(_StalledSpeaker())
        cid = client.post(
            "/api/talk/send", json={"text": "watchdog test"}
        ).json()["conversation_id"]
        with client.websocket_connect(f"/api/talk/{cid}/stream") as ws:
            # Operator message + the half token + then talk.error(stalled).
            op_env = json.loads(ws.receive_text())
            assert op_env["payload"]["role"] == "operator"
            tokens, error_env = _drain_until_event(ws, "talk.error")
            assert any(t["event_type"] == "talk.token" for t in tokens)
            assert error_env["payload"]["kind"] == "stalled"

    def test_cancel_emits_cancelled_envelope(
        self, make_client: ClientFactory
    ) -> None:
        """A cancel call cancels the task + emits ``talk.cancelled``."""
        client = make_client(
            _SlowSpeaker(per_token_seconds=0.03, token_count=40),
        )
        send_resp = client.post(
            "/api/talk/send", json={"text": "slow ping"}
        ).json()
        cid = send_resp["conversation_id"]
        gid = send_resp["generation_id"]
        with client.websocket_connect(f"/api/talk/{cid}/stream") as ws:
            op_env = json.loads(ws.receive_text())
            assert op_env["payload"]["role"] == "operator"
            # Wait for at least one token to confirm the stream started.
            for _ in range(50):
                env = json.loads(ws.receive_text())
                if env["event_type"] == "talk.token":
                    break
            else:  # pragma: no cover — should never happen with _SlowSpeaker
                raise AssertionError("no talk.token observed before cancel")
            cancel_resp = client.post(
                f"/api/talk/conversations/{cid}/cancel-generation/{gid}"
            )
            assert cancel_resp.status_code == 200
            assert cancel_resp.json()["cancelled"] is True
            assert cancel_resp.json()["reason"] == "cancelled"
            # Continue draining tokens until the cancelled envelope arrives.
            _, cancelled_env = _drain_until_event(ws, "talk.cancelled")
            assert cancelled_env["payload"]["generation_id"] == gid
            # Partial text was persisted (non-empty) so the cockpit can
            # render the truncated reply with a cancelled badge.
            assert cancelled_env["payload"]["partial_text"]
            assert cancelled_env["payload"]["message"] is not None
            persisted = cancelled_env["payload"]["message"]
            assert persisted["role"] == "self_jr"
            assert "x" in str(persisted["content"])

    def test_cancel_unknown_generation_returns_reason(
        self, make_client: ClientFactory
    ) -> None:
        client = make_client(_EchoSpeaker())
        cid = client.post(
            "/api/talk/send", json={"text": "done quickly"}
        ).json()["conversation_id"]
        _wait_for_messages(client, cid, expected_count=2)
        # Cancel a non-existent generation_id — the past one has already
        # settled and removed itself from the active map.
        r = client.post(
            f"/api/talk/conversations/{cid}/cancel-generation/deadbeef"
        )
        assert r.status_code == 200
        body = r.json()
        assert body["cancelled"] is False
        assert body["reason"] == "unknown_generation"

    def test_cancel_invalid_conversation_id_400(
        self, make_client: ClientFactory
    ) -> None:
        client = make_client(_EchoSpeaker())
        r = client.post(
            "/api/talk/conversations/not-a-uuid/cancel-generation/x"
        )
        assert r.status_code == 400

    def test_unknown_conversation_closes(
        self, make_client: ClientFactory
    ) -> None:
        client = make_client(_EchoSpeaker())
        with (
            pytest.raises(WebSocketDisconnect),
            client.websocket_connect(
                "/api/talk/00000000-0000-0000-0000-000000000000/stream",
            ) as ws,
        ):
            ws.receive_text()

    def test_invalid_conversation_id_closes(
        self, make_client: ClientFactory
    ) -> None:
        client = make_client(_EchoSpeaker())
        with (
            pytest.raises(WebSocketDisconnect),
            client.websocket_connect("/api/talk/not-a-uuid/stream") as ws,
        ):
            ws.receive_text()

    def test_reconnect_replays_buffer(
        self, make_client: ClientFactory
    ) -> None:
        """Replay buffer survives reconnect within the same registry."""
        client = make_client(_EchoSpeaker())
        cid = client.post(
            "/api/talk/send", json={"text": "first"}
        ).json()["conversation_id"]
        _wait_for_messages(client, cid, expected_count=2)
        # First connect drains everything emitted so far.
        with client.websocket_connect(f"/api/talk/{cid}/stream") as ws:
            _drain_until_event(ws, "talk.message")  # operator first
            _drain_until_event(ws, "talk.message")  # self_jr final
        # Reconnect — replay buffer still holds those envelopes.
        with client.websocket_connect(f"/api/talk/{cid}/stream") as ws:
            envelopes: list[dict[str, object]] = []
            # Pull up to a few frames; we expect at least one talk.message.
            for _ in range(10):
                envelopes.append(json.loads(ws.receive_text()))
                if (
                    sum(
                        1
                        for e in envelopes
                        if e["event_type"] == "talk.message"
                    )
                    >= 2
                ):
                    break
        roles_seen = [
            e["payload"]["role"]
            for e in envelopes
            if e["event_type"] == "talk.message"
        ]
        assert "operator" in roles_seen
        assert "self_jr" in roles_seen


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
        body = sent.json()
        assert body["speaker_status"] == "not_configured"
        assert body["generation_id"] is None
