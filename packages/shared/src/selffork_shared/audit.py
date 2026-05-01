"""Append-only JSONL audit log for SelfFork sessions.

One file per session: ``<audit_dir>/<session_id>.jsonl``. Every event has

    {ts, correlation_id, session_id, category, level, event, payload}

Categories are a closed set (see :data:`AuditCategory`). Secrets matching
common key/token/secret patterns are redacted before write when
``audit.redact_secrets=true`` (default).

See: ``docs/decisions/ADR-001_MVP_v0.md`` §10.
"""

from __future__ import annotations

import json
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, get_args

from selffork_shared.config import AuditConfig
from selffork_shared.logging import current_correlation_id

__all__ = ["AuditCategory", "AuditLevel", "AuditLogger"]

AuditCategory = Literal[
    "session.state",
    "runtime.spawn",
    "runtime.health",
    "runtime.stop",
    "sandbox.spawn",
    "sandbox.exec",
    "sandbox.teardown",
    "agent.spawn",
    "agent.event",  # legacy — pre-round-loop architecture; kept for compat
    "agent.invoke",  # one CLI subprocess invocation in the round loop
    "agent.output",  # captured stdout from one CLI invocation
    "agent.done",
    "agent.rate_limited",  # subscription quota hit; session paused
    "agent.auth_required",  # subscription auth invalid; user must re-login
    "agent.spawn_request",  # parent Jr asked to spawn a child session
    "agent.spawn_complete",  # child session finished; aggregated back to parent
    "tool.call",  # Jr emitted a <selffork-tool-call> block; we're invoking it
    "tool.result",  # corresponding result returned to Jr's next round
    "selffork_jr.reply",  # SelfFork Jr's chat completion output for one round
    "plan.load",
    "plan.save",
    "plan.update",
    "error",
]

AuditLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]

_VALID_LEVELS: frozenset[str] = frozenset(get_args(AuditLevel))

# Sensitive keys: redact value when match found. Pattern intentionally broad
# (api_key, API-KEY, AUTH_TOKEN, secret, password, etc.).
_SENSITIVE_KEY = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|passwd|auth|cred|private[_-]?key)",
)
_REDACTED = "<redacted>"


class AuditLogger:
    """Thread-safe JSONL audit logger for one session.

    Construct once per session; call :meth:`emit` for every state transition
    or significant action. Quietly drops events when ``config.enabled`` is
    False, so call sites never need ``if config.audit.enabled``.

    Example::

        logger = AuditLogger(config.audit, session_id="01HJ...")
        logger.emit("runtime.spawn", payload={"backend": "mlx-server", "port": 8001})
    """

    def __init__(self, config: AuditConfig, session_id: str) -> None:
        self._config = config
        self._session_id = session_id
        self._lock = threading.Lock()

        if config.enabled:
            audit_dir = Path(config.audit_dir).expanduser()
            audit_dir.mkdir(parents=True, exist_ok=True)
            self._path: Path | None = audit_dir / f"{session_id}.jsonl"
        else:
            self._path = None

    @property
    def path(self) -> Path | None:
        """Filesystem path of the audit file, or ``None`` when disabled."""
        return self._path

    @property
    def session_id(self) -> str:
        return self._session_id

    def emit(
        self,
        category: AuditCategory,
        *,
        event: str = "event",
        level: AuditLevel = "INFO",
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Append a single audit event.

        No-op when auditing is disabled. Raises :class:`ValueError` for an
        invalid level (other validation is type-checked at call sites).
        Filesystem errors propagate as :class:`OSError`.
        """
        if self._path is None:
            return

        if level not in _VALID_LEVELS:
            raise ValueError(f"invalid audit level: {level!r}")

        record: dict[str, Any] = {
            "ts": _utc_now_iso(),
            "correlation_id": current_correlation_id(),
            "session_id": self._session_id,
            "category": category,
            "level": level,
            "event": event,
            "payload": _redact(payload or {}, redact=self._config.redact_secrets),
        }

        line = json.dumps(record, default=str, sort_keys=True, ensure_ascii=False)
        with self._lock, self._path.open("a", encoding="utf-8") as fp:
            fp.write(line)
            fp.write("\n")


def _utc_now_iso() -> str:
    """ISO-8601 UTC timestamp, millisecond precision, ``Z`` suffix."""
    raw = datetime.now(UTC).isoformat(timespec="milliseconds")
    return raw.replace("+00:00", "Z")


def _redact(value: Any, *, redact: bool) -> Any:
    """Recursively redact sensitive keys when ``redact`` is True."""
    if not redact:
        return value
    if isinstance(value, dict):
        return {
            k: (_REDACTED if _SENSITIVE_KEY.search(str(k)) else _redact(v, redact=redact))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(item, redact=redact) for item in value]
    return value
