"""Unit tests for :mod:`selffork_shared.audit`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import structlog

from selffork_shared.audit import AuditLogger
from selffork_shared.config import AuditConfig
from selffork_shared.logging import bind_correlation_id


@pytest.fixture(autouse=True)
def _reset_contextvars() -> None:
    structlog.contextvars.clear_contextvars()


class TestDisabled:
    def test_no_path_when_disabled(self, tmp_path: Path) -> None:
        cfg = AuditConfig(enabled=False, audit_dir=str(tmp_path))
        logger = AuditLogger(cfg, session_id="01HJ12345ABCDEFGHIJKLMNOPQ")
        assert logger.path is None

    def test_emit_no_op_when_disabled(self, tmp_path: Path) -> None:
        cfg = AuditConfig(enabled=False, audit_dir=str(tmp_path))
        logger = AuditLogger(cfg, session_id="01HJ12345ABCDEFGHIJKLMNOPQ")
        logger.emit("session.state", payload={"to": "RUNNING"})
        # No file produced
        assert list(tmp_path.iterdir()) == []


class TestEnabled:
    def test_writes_jsonl_record(self, tmp_path: Path) -> None:
        cfg = AuditConfig(
            enabled=True,
            audit_dir=str(tmp_path),
            redact_secrets=False,
        )
        logger = AuditLogger(cfg, session_id="01HJSESSION1234567890ABCDE")
        bind_correlation_id("01HJCORRELATIONABCDEFGHIJK")

        logger.emit("runtime.spawn", payload={"backend": "mlx-server", "port": 8001})

        assert logger.path is not None
        line = logger.path.read_text(encoding="utf-8").strip()
        record = json.loads(line)
        assert record["category"] == "runtime.spawn"
        assert record["session_id"] == "01HJSESSION1234567890ABCDE"
        assert record["correlation_id"] == "01HJCORRELATIONABCDEFGHIJK"
        assert record["payload"] == {"backend": "mlx-server", "port": 8001}
        assert record["level"] == "INFO"
        assert "ts" in record
        assert record["ts"].endswith("Z")

    def test_appends_subsequent_events(self, tmp_path: Path) -> None:
        cfg = AuditConfig(enabled=True, audit_dir=str(tmp_path), redact_secrets=False)
        logger = AuditLogger(cfg, session_id="01HJTESTSESSIONABCDEFGHIJK")
        logger.emit("session.state", payload={"to": "PREPARING"})
        logger.emit("session.state", payload={"to": "RUNNING"})
        logger.emit("session.state", payload={"to": "COMPLETED"})
        assert logger.path is not None

        lines = logger.path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3
        states = [json.loads(line)["payload"]["to"] for line in lines]
        assert states == ["PREPARING", "RUNNING", "COMPLETED"]

    def test_session_id_in_filename(self, tmp_path: Path) -> None:
        cfg = AuditConfig(enabled=True, audit_dir=str(tmp_path))
        sid = "01HJTESTUNIQUESESSIONIDXYZ"
        logger = AuditLogger(cfg, session_id=sid)
        logger.emit("session.state", payload={"to": "PREPARING"})
        assert logger.path is not None
        assert logger.path.name == f"{sid}.jsonl"


class TestRedaction:
    def test_redacts_known_secret_keys(self, tmp_path: Path) -> None:
        cfg = AuditConfig(enabled=True, audit_dir=str(tmp_path), redact_secrets=True)
        logger = AuditLogger(cfg, session_id="01HJTESTABCDEFGHIJKLMNOPQR")
        logger.emit(
            "agent.spawn",
            payload={
                "OPENAI_API_KEY": "sk-secret",
                "ANTHROPIC_AUTH_TOKEN": "abc",
                "user_password": "p4ssw0rd",
                "private_key_path": "/secret/key.pem",
                "port": 8001,
                "model": "gemma",
            },
        )
        assert logger.path is not None
        record = json.loads(logger.path.read_text(encoding="utf-8").strip())
        payload = record["payload"]
        assert payload["OPENAI_API_KEY"] == "<redacted>"
        assert payload["ANTHROPIC_AUTH_TOKEN"] == "<redacted>"
        assert payload["user_password"] == "<redacted>"
        assert payload["private_key_path"] == "<redacted>"
        # Non-secret keys preserved
        assert payload["port"] == 8001
        assert payload["model"] == "gemma"

    def test_redaction_disabled(self, tmp_path: Path) -> None:
        cfg = AuditConfig(enabled=True, audit_dir=str(tmp_path), redact_secrets=False)
        logger = AuditLogger(cfg, session_id="01HJTESTNOREDACT0123456789")
        logger.emit("agent.spawn", payload={"OPENAI_API_KEY": "sk-secret"})
        assert logger.path is not None
        record = json.loads(logger.path.read_text(encoding="utf-8").strip())
        assert record["payload"]["OPENAI_API_KEY"] == "sk-secret"

    def test_redaction_recursive(self, tmp_path: Path) -> None:
        cfg = AuditConfig(enabled=True, audit_dir=str(tmp_path), redact_secrets=True)
        logger = AuditLogger(cfg, session_id="01HJTESTREDACTNESTED012345")
        logger.emit(
            "agent.spawn",
            payload={
                "env": {"API_KEY": "leak", "PORT": "8001"},
                "configs": [{"token": "x", "name": "y"}],
            },
        )
        assert logger.path is not None
        record = json.loads(logger.path.read_text(encoding="utf-8").strip())
        assert record["payload"]["env"]["API_KEY"] == "<redacted>"
        assert record["payload"]["env"]["PORT"] == "8001"
        assert record["payload"]["configs"][0]["token"] == "<redacted>"
        assert record["payload"]["configs"][0]["name"] == "y"


class TestValidation:
    def test_invalid_level_rejected(self, tmp_path: Path) -> None:
        cfg = AuditConfig(enabled=True, audit_dir=str(tmp_path))
        logger = AuditLogger(cfg, session_id="01HJTESTLEVELABCDEFGHIJKLM")
        with pytest.raises(ValueError, match="invalid audit level"):
            logger.emit("session.state", level="TRACE")  # type: ignore[arg-type]
