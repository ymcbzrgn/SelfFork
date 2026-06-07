"""Integration tests for S3 dashboard wiring (Phase E).

Covers the new ``/api/pending-confirmations/count``, ``/extend``,
``/api/talk/drafts`` (+ ``/claim``), and the upgraded
``/api/telegram/*`` surface (status reports "not_configured" without
a bot token, ``/test`` 503s when bridge is Null, activity log
returns empty arrays).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from selffork_orchestrator.dashboard.server import DashboardConfig, build_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("SELFFORK_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    # Each test gets its own pending-audit file so the cross-process
    # JSONL replay path has nothing pre-existing.
    pending_path = tmp_path / "pending.jsonl"
    monkeypatch.setenv("SELFFORK_PENDING_AUDIT_PATH", str(pending_path))
    config = DashboardConfig(
        audit_dir=tmp_path / "audit",
        resume_dir=tmp_path / "resume",
        projects_root=tmp_path / "projects",
        selffork_script=Path("/usr/bin/true"),
        chat_db_path=tmp_path / "chat.db",
        talk_db_path=tmp_path / "talk.db",
    )
    with TestClient(build_app(config)) as c:
        yield c


def test_pending_count_zero_initially(client: TestClient) -> None:
    res = client.get("/api/pending-confirmations/count")
    assert res.status_code == 200
    assert res.json() == 0


def test_extend_404_for_unknown_id(client: TestClient) -> None:
    res = client.post(
        "/api/pending-confirmations/does-not-exist/extend",
        json={"hours": 2},
    )
    assert res.status_code == 404


def test_extend_rejects_nonpositive_hours(client: TestClient) -> None:
    res = client.post(
        "/api/pending-confirmations/anything/extend",
        json={"hours": 0},
    )
    assert res.status_code == 400


def test_telegram_status_not_configured(client: TestClient) -> None:
    res = client.get("/api/telegram/status")
    assert res.status_code == 200
    body = res.json()
    assert body["state"] == "not_configured"
    assert body["mode"] == "polling"


def test_telegram_test_503_without_bridge(client: TestClient) -> None:
    res = client.post("/api/telegram/test", json={"body": "hi"})
    assert res.status_code == 503


def test_telegram_activity_empty(client: TestClient) -> None:
    res = client.get("/api/telegram/activity")
    assert res.status_code == 200
    assert res.json() == {"inbound": [], "outbound": []}


def test_drafts_list_and_claim_cycle(
    client: TestClient,
    tmp_path: Path,
) -> None:
    # Inject a draft directly via the in-process store (mirrors what the
    # Telegram InboundRouter would do for a no-active-workspace message).
    store = client.app.state.telegram_drafts_store
    draft = store.add(chat_id=1, text="hello jr", sender="yamac")

    res = client.get("/api/talk/drafts")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["text"] == "hello jr"

    claim = client.post("/api/talk/drafts/claim", json={"ids": [draft.id]})
    assert claim.status_code == 200
    assert claim.json() == {"claimed": 1}

    after = client.get("/api/talk/drafts")
    assert after.json() == []


def test_cross_process_pending_reload(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """A request written by an external process (here: a JSON line on
    disk) becomes visible to the dashboard's pending list after one
    GET — proving the cross-process replay (``reload_from_disk``) works.
    """
    path = Path(client.app.state.pending_confirmation_store._audit_path)  # type: ignore[arg-type]
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "op": "request",
        "entry": {
            "id": "ext-xyz",
            "workspace_slug": "demo",
            "category_id": "prod_deploy",
            "category_description": "PROD push",
            "command_summary": "git push origin main",
            "action_payload": {"tool": "git"},
            "asked_at": "2099-01-01T00:00:00+00:00",
            "expires_at": "2099-01-01T04:00:00+00:00",
            "status": "pending",
            "decided_at": None,
            "decided_by": None,
        },
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    res = client.get("/api/pending-confirmations")
    assert res.status_code == 200
    body = res.json()
    assert any(item["id"] == "ext-xyz" for item in body)
