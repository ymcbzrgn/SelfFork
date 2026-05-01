"""Structured logging with correlation and session IDs.

Every log event is JSON by default with:

    ts, level, correlation_id, session_id, event, payload

Correlation and session IDs propagate via :mod:`structlog.contextvars`,
so every log emitted within a bound context inherits them automatically.

Call :func:`setup_logging` once at process startup. Anywhere else just use
``log = get_logger(__name__); log.info("event", key=value)`` — never call
:func:`logging.basicConfig` or :func:`print` from SelfFork code.

See: ``docs/decisions/ADR-001_MVP_v0.md`` §8.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, cast

import structlog
from structlog.contextvars import bind_contextvars, get_contextvars

from selffork_shared.config import LoggingConfig
from selffork_shared.ulid import new_ulid

__all__ = [
    "bind_correlation_id",
    "bind_session_id",
    "current_correlation_id",
    "current_session_id",
    "get_logger",
    "setup_logging",
]


def setup_logging(config: LoggingConfig) -> None:
    """Configure structlog + stdlib logging for the entire process.

    Idempotent — safe to call multiple times. Reads JSON vs TTY mode from
    :attr:`LoggingConfig.json_output`.
    """
    level = getattr(logging, config.level)

    logging.basicConfig(
        level=level,
        format="%(message)s",
        stream=sys.stderr,
        force=True,
    )

    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if config.json_output:
        processors.append(structlog.processors.JSONRenderer(sort_keys=True))
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        context_class=dict,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "") -> structlog.stdlib.BoundLogger:
    """Return a structured logger bound to ``name``."""
    return cast("structlog.stdlib.BoundLogger", structlog.get_logger(name))


def bind_correlation_id(correlation_id: str | None = None) -> str:
    """Bind a correlation ID to the current logging context.

    Generates a new ULID if ``correlation_id`` is None. Returns the ID
    actually bound, so the caller can record it (e.g. for the audit log).
    """
    cid = correlation_id or new_ulid()
    bind_contextvars(correlation_id=cid)
    return cid


def bind_session_id(session_id: str) -> None:
    """Bind a session ID to the current logging context."""
    bind_contextvars(session_id=session_id)


def current_correlation_id() -> str | None:
    """Return the correlation ID currently bound to context, if any."""
    value: Any = get_contextvars().get("correlation_id")
    return value if isinstance(value, str) else None


def current_session_id() -> str | None:
    """Return the session ID currently bound to context, if any."""
    value: Any = get_contextvars().get("session_id")
    return value if isinstance(value, str) else None
