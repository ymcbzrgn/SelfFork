"""Tests for the S5 ``/api/telegram/setup`` wizard upgrade.

The S3 endpoint mutated ``os.environ`` to persist the operator's
bot token. S5 swaps that for a YAML store at
``~/.selffork/settings/telegram.yaml`` plus an optional
``setWebhook`` API call when the operator picks webhook mode.

These tests pin the ``YamlSettingsStore`` to a ``tmp_path``-rooted
file so the operator's real ``~/.selffork/`` is never touched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from selffork_orchestrator.dashboard.settings import (
    TelegramConfig,
    YamlSettingsStore,
)
from selffork_orchestrator.dashboard.telegram_router import (
    TelegramActivityLog,
    build_telegram_router,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "SELFFORK_TELEGRAM_BOT_TOKEN",
        "TELEGRAM_BOT_TOKEN",
        "SELFFORK_TELEGRAM_WEBHOOK_URL",
        "TELEGRAM_WEBHOOK_URL",
        "SELFFORK_TELEGRAM_WEBHOOK_SECRET",
        "SELFFORK_TELEGRAM_MODE",
        "SELFFORK_SOFT_CONFIRM_HOURS",
    ):
        monkeypatch.delenv(key, raising=False)


def _build(
    tmp_path: Path,
) -> tuple[TestClient, YamlSettingsStore[TelegramConfig], Path]:
    yaml_path = tmp_path / "telegram.yaml"
    store: YamlSettingsStore[TelegramConfig] = YamlSettingsStore(
        path=yaml_path,
        schema=TelegramConfig,
        default_factory=TelegramConfig,
    )
    app = FastAPI()
    app.include_router(
        build_telegram_router(
            activity_log=TelegramActivityLog(),
            store=store,
        ),
    )
    return TestClient(app), store, yaml_path


def test_setup_polling_persists_to_yaml(tmp_path: Path) -> None:
    client, _store, yaml_path = _build(tmp_path)
    r = client.post(
        "/api/telegram/setup",
        json={
            "bot_token": "123:abc",
            "chat_id": "456",
            "mode": "polling",
            "soft_confirm_window_hours": 6,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "polling"
    assert body["soft_confirm_window_hours"] == 6
    assert yaml_path.is_file()
    on_disk = yaml.safe_load(yaml_path.read_text())
    assert on_disk["bot_token"] == "123:abc"
    assert on_disk["chat_id"] == "456"
    assert on_disk["mode"] == "polling"
    assert on_disk["soft_confirm_window_hours"] == 6


def test_setup_rejects_empty_bot_token(tmp_path: Path) -> None:
    client, _store, _yaml = _build(tmp_path)
    r = client.post("/api/telegram/setup", json={"bot_token": "   "})
    assert r.status_code == 400


def test_setup_webhook_mode_requires_webhook_url(tmp_path: Path) -> None:
    client, _store, _yaml = _build(tmp_path)
    r = client.post(
        "/api/telegram/setup",
        json={
            "bot_token": "123:abc",
            "mode": "webhook",
            "webhook_url": "",
        },
    )
    assert r.status_code == 400
    assert "webhook_url" in r.json()["detail"]


def test_setup_webhook_mode_calls_telegram_api(tmp_path: Path) -> None:
    """When mode='webhook', the wizard hits Telegram's setWebhook API."""
    client, _store, yaml_path = _build(tmp_path)
    fake_response = {"ok": True, "result": True, "description": "ok"}
    captured: dict[str, Any] = {}

    class _FakeResp:
        status_code = 200
        text = "ok"

        def __init__(self, payload: Any) -> None:
            self._payload = payload
            self.request = None

        def json(self) -> Any:
            return self._payload

    class _FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def post(self, url: str, json: Any) -> _FakeResp:
            captured["url"] = url
            captured["json"] = json
            return _FakeResp(fake_response)

    with patch(
        "selffork_orchestrator.dashboard.telegram_router.httpx.AsyncClient",
        _FakeClient,
    ):
        r = client.post(
            "/api/telegram/setup",
            json={
                "bot_token": "123:abc",
                "mode": "webhook",
                "webhook_url": "https://selffork.example.com/api/telegram/webhook",
                "webhook_secret": "secret123",
            },
        )

    assert r.status_code == 200
    assert (
        captured["url"]
        == "https://api.telegram.org/bot123:abc/setWebhook"
    )
    assert (
        captured["json"]["url"]
        == "https://selffork.example.com/api/telegram/webhook"
    )
    assert captured["json"]["secret_token"] == "secret123"
    on_disk = yaml.safe_load(yaml_path.read_text())
    assert on_disk["mode"] == "webhook"
    assert on_disk["webhook_secret"] == "secret123"


def test_setup_webhook_failure_returns_502(tmp_path: Path) -> None:
    """A Telegram API failure surfaces as 502, YAML stays persisted."""
    client, _store, yaml_path = _build(tmp_path)

    class _FailingClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> _FailingClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def post(self, url: str, json: Any) -> Any:
            import httpx

            raise httpx.ConnectError("connection refused")

    with patch(
        "selffork_orchestrator.dashboard.telegram_router.httpx.AsyncClient",
        _FailingClient,
    ):
        r = client.post(
            "/api/telegram/setup",
            json={
                "bot_token": "123:abc",
                "mode": "webhook",
                "webhook_url": "https://selffork.example.com/webhook",
            },
        )

    assert r.status_code == 502
    detail = r.json()["detail"]
    assert "setWebhook" in detail
    # Even though the webhook call failed, the YAML is already
    # persisted — operator can retry setWebhook manually or fix
    # the URL and resubmit.
    assert yaml_path.is_file()


def test_setup_ok_false_returns_502(tmp_path: Path) -> None:
    """Telegram returns 200 + ok=false for app-level errors (bad URL)."""
    client, _store, _yaml = _build(tmp_path)

    class _NotOkResp:
        status_code = 200
        text = '{"ok": false, "description": "Bad webhook"}'
        request = None

        def json(self) -> Any:
            return {"ok": False, "description": "Bad webhook"}

    class _NotOkClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> _NotOkClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def post(self, url: str, json: Any) -> _NotOkResp:
            return _NotOkResp()

    with patch(
        "selffork_orchestrator.dashboard.telegram_router.httpx.AsyncClient",
        _NotOkClient,
    ):
        r = client.post(
            "/api/telegram/setup",
            json={
                "bot_token": "123:abc",
                "mode": "webhook",
                "webhook_url": "https://example.com",
            },
        )
    assert r.status_code == 502


def test_status_reads_yaml_persisted_config(tmp_path: Path) -> None:
    """After setup, /status reflects the YAML config (not env)."""
    client, store, _yaml = _build(tmp_path)
    store.write(
        TelegramConfig(
            bot_token="999:zzz",
            chat_id="42",
            mode="polling",
            soft_confirm_window_hours=2,
        ),
    )
    r = client.get("/api/telegram/status")
    assert r.status_code == 200
    body = r.json()
    assert body["soft_confirm_window_hours"] == 2
    assert body["mode"] == "polling"
    # state is "errored" because we passed no bridge — but the
    # token is configured (NOT "not_configured")
    assert body["state"] != "not_configured"


def test_status_not_configured_when_no_yaml_no_env(tmp_path: Path) -> None:
    client, _store, _yaml = _build(tmp_path)
    r = client.get("/api/telegram/status")
    assert r.status_code == 200
    assert r.json()["state"] == "not_configured"


def test_setup_with_chat_id_merges_into_operators_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Audit-god HIGH #3 regression: wizard chat_id must land in the
    AllowList source-of-truth (``~/.selffork/operators.json``); without
    this the bridge comes up 'connected' but every notify is dropped."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("SELFFORK_PENDING_AUDIT_PATH", raising=False)
    client, _store, _yaml = _build(tmp_path)
    r = client.post(
        "/api/telegram/setup",
        json={
            "bot_token": "123:abc",
            "chat_id": "98765",
            "mode": "polling",
        },
    )
    assert r.status_code == 200
    operators_path = tmp_path / ".selffork" / "operators.json"
    assert operators_path.is_file()
    import json as _json

    body = _json.loads(operators_path.read_text())
    assert 98765 in body["chat_ids"]


def test_setup_chat_id_non_numeric_no_op(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-numeric chat_id skips the allowlist merge (defensive)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    client, _store, _yaml = _build(tmp_path)
    r = client.post(
        "/api/telegram/setup",
        json={
            "bot_token": "123:abc",
            "chat_id": "not-a-number",
            "mode": "polling",
        },
    )
    assert r.status_code == 200
    operators_path = tmp_path / ".selffork" / "operators.json"
    # Either absent or has no chat_ids — but not crashing the wizard.
    if operators_path.is_file():
        import json as _json

        body = _json.loads(operators_path.read_text())
        assert "not-a-number" not in str(body)


def test_setup_chat_id_preserves_existing_operators(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Merge — don't clobber — existing operators.json content."""
    monkeypatch.setenv("HOME", str(tmp_path))
    operators_path = tmp_path / ".selffork" / "operators.json"
    operators_path.parent.mkdir(parents=True, exist_ok=True)
    import json as _json

    operators_path.write_text(
        _json.dumps(
            {"chat_ids": [111, 222], "default_project_slug": "demo"}
        ),
        encoding="utf-8",
    )
    client, _store, _yaml = _build(tmp_path)
    r = client.post(
        "/api/telegram/setup",
        json={
            "bot_token": "123:abc",
            "chat_id": "98765",
            "mode": "polling",
        },
    )
    assert r.status_code == 200
    body = _json.loads(operators_path.read_text())
    assert sorted(body["chat_ids"]) == [111, 222, 98765]
    assert body["default_project_slug"] == "demo"


def test_settings_telegram_get_yaml_env_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``/api/settings/telegram`` returns effective config (YAML > env)."""
    from fastapi import FastAPI as _FastAPI
    from fastapi.testclient import TestClient as _TestClient

    from selffork_orchestrator.dashboard.settings_router import (
        build_settings_router,
    )

    yaml_path = tmp_path / "telegram.yaml"
    store: YamlSettingsStore[TelegramConfig] = YamlSettingsStore(
        path=yaml_path,
        schema=TelegramConfig,
        default_factory=TelegramConfig,
    )

    app = _FastAPI()
    app.include_router(
        build_settings_router(
            config_path=tmp_path / "selffork.yaml",
            telegram_store=store,
        ),
    )
    client = _TestClient(app)

    # Env-only: YAML absent, env vars fall back.
    monkeypatch.setenv("SELFFORK_TELEGRAM_BOT_TOKEN", "env-token")
    monkeypatch.setenv("SELFFORK_TELEGRAM_MODE", "webhook")
    monkeypatch.setenv(
        "SELFFORK_TELEGRAM_WEBHOOK_URL", "https://env.example/w"
    )
    r1 = client.get("/api/settings/telegram")
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1["bot_token"] == "env-token"
    assert body1["mode"] == "webhook"
    assert body1["webhook_url"] == "https://env.example/w"

    # YAML wins after operator runs setup.
    store.write(
        TelegramConfig(
            bot_token="yaml-token",
            mode="polling",
            soft_confirm_window_hours=8,
        ),
    )
    r2 = client.get("/api/settings/telegram")
    body2 = r2.json()
    assert body2["bot_token"] == "yaml-token"
    assert body2["mode"] == "polling"
    assert body2["soft_confirm_window_hours"] == 8
