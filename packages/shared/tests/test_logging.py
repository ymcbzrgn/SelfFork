"""Unit tests for :mod:`selffork_shared.logging`."""

from __future__ import annotations

import json

import pytest
import structlog

from selffork_shared.config import LoggingConfig
from selffork_shared.logging import (
    bind_correlation_id,
    bind_session_id,
    current_correlation_id,
    current_session_id,
    get_logger,
    setup_logging,
)


@pytest.fixture(autouse=True)
def _reset_contextvars() -> None:
    """Clear structlog contextvars between tests."""
    structlog.contextvars.clear_contextvars()


class TestSetup:
    def test_setup_idempotent(self) -> None:
        setup_logging(LoggingConfig())
        setup_logging(LoggingConfig())
        log = get_logger("test")
        log.info("ok")  # no error means OK

    def test_tty_mode_does_not_crash(self) -> None:
        setup_logging(LoggingConfig(json_output=False))
        log = get_logger("test")
        log.info("hello")


class TestCorrelationId:
    def test_bind_returns_generated_ulid(self) -> None:
        cid = bind_correlation_id()
        assert isinstance(cid, str)
        assert len(cid) == 26
        assert current_correlation_id() == cid

    def test_bind_with_explicit_value(self) -> None:
        cid = bind_correlation_id("01HJTESTABCDEFGHIJKLMNOPQR")
        assert cid == "01HJTESTABCDEFGHIJKLMNOPQR"
        assert current_correlation_id() == cid

    def test_unbound_returns_none(self) -> None:
        assert current_correlation_id() is None


class TestSessionId:
    def test_bind_session(self) -> None:
        bind_session_id("01HJSESSIONABCDEFGHIJKLMNO")
        assert current_session_id() == "01HJSESSIONABCDEFGHIJKLMNO"

    def test_unbound_returns_none(self) -> None:
        assert current_session_id() is None


class TestJsonOutput:
    def test_log_emits_json_with_ids(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        setup_logging(LoggingConfig(json_output=True, level="INFO"))
        bind_correlation_id("01HJTESTCORRELATIONIDXXXXX")
        bind_session_id("01HJTESTSESSIONIDXXXXXXXXX")
        log = get_logger("test")
        log.info("hello", foo=1)

        captured = capsys.readouterr().err.strip().splitlines()
        # Last non-empty line is our JSON record.
        record = json.loads(captured[-1])
        assert record["event"] == "hello"
        assert record["foo"] == 1
        assert record["correlation_id"] == "01HJTESTCORRELATIONIDXXXXX"
        assert record["session_id"] == "01HJTESTSESSIONIDXXXXXXXXX"
        assert record["level"] == "info"
        assert "ts" in record

    def test_log_without_correlation_id_omits_field(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        setup_logging(LoggingConfig(json_output=True, level="INFO"))
        log = get_logger("test")
        log.info("hello")

        captured = capsys.readouterr().err.strip().splitlines()
        record = json.loads(captured[-1])
        assert record["event"] == "hello"
        assert "correlation_id" not in record
        assert "session_id" not in record


class TestLevelFiltering:
    def test_debug_dropped_at_info_level(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        setup_logging(LoggingConfig(json_output=True, level="INFO"))
        log = get_logger("test")
        log.debug("noisy_debug")
        log.info("important_info")

        captured = capsys.readouterr().err.strip().splitlines()
        events = [json.loads(line)["event"] for line in captured if line]
        assert "noisy_debug" not in events
        assert "important_info" in events
