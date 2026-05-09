"""Cross-CLI handoff bundle schema (Letta ``.af`` esinli).

The :class:`HandoffBundle` is a fully self-contained snapshot of the
in-flight session state, suitable for re-injection into a different
CLI agent. Components:

- :class:`ActiveTask` — operator's PRD restated for the receiving CLI.
- :class:`TranscriptMessage` — one round in the operator/cli loop.
- :class:`MemorySubset` — Mind tier references (NOT payload duplication;
  Mind T2 stays the source of truth, the bundle carries IDs/queries).
- :class:`ToolState` — cwd + env whitelist + open files. ``env_whitelist``
  is enforced as a secret-free allow-list at schema level (see
  ``_ENV_DENYLIST_RE``); attempts to ship credentials are rejected.

Identifier path-components (``bundle_id``, ``session_id``, ``project_slug``)
are constrained to ``[A-Za-z0-9_\\-]+`` so the on-disk store
(``HandoffBundleStore``) cannot be tricked into writing outside its
root via path traversal.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "ActiveTask",
    "CliId",
    "HandoffBundle",
    "MemorySubset",
    "ToolState",
    "TranscriptMessage",
]


CliId = Literal[
    "opencode",
    "claude-code",
    "codex",
    "gemini-cli",
    "minimax-cli",
]


# Path-component pattern: only ASCII alphanumerics, hyphen, underscore.
# Rejects ``/``, ``..``, control chars, whitespace — closes path traversal
# vector for HandoffBundleStore on-disk layout.
_PATH_COMPONENT_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


# Substrings (case-insensitive) that disqualify an env-var key from
# travelling in a HandoffBundle. The receiving CLI uses its own auth
# (OAuth dance) — it never inherits the producer's credentials.
_ENV_DENYLIST_RE = re.compile(
    r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|OAUTH|BEARER|CREDENTIAL|"
    r"API_PASS|PRIVATE|SESSION_ID|COOKIE)",
    re.IGNORECASE,
)


class TranscriptMessage(BaseModel):
    """One message in the round-loop transcript."""

    model_config = ConfigDict(frozen=True, strict=True)

    role: Literal["operator", "cli"]
    content: str
    round_index: int = Field(ge=0)


class ActiveTask(BaseModel):
    """Description of the work in flight."""

    model_config = ConfigDict(frozen=True, strict=True)

    title: str = Field(..., min_length=1)
    description: str = ""
    checklist: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)


class MemorySubset(BaseModel):
    """Scoped Mind tier references (IDs / queries, not payload).

    The receiving CLI's session is expected to call ``mind_recall`` with
    these IDs/queries to fetch the actual content on demand — this keeps
    bundle size bounded regardless of how rich Mind has become.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    t1_summary: str | None = None
    t2_episode_ids: list[str] = Field(default_factory=list)
    t3_relevant_facts: list[str] = Field(default_factory=list)
    t4_procedural_refs: list[str] = Field(default_factory=list)


class ToolState(BaseModel):
    """Cross-CLI portable tool state.

    ``env_whitelist`` is enforced as a secret-free allow-list at validation
    time: any key containing a credential-keyword substring (``KEY``,
    ``TOKEN``, ``SECRET``, ``PASSWORD``, ``OAUTH``, ``BEARER``,
    ``CREDENTIAL``, ``COOKIE``, ``PRIVATE``) is rejected. The receiving
    CLI uses its own auth — it never inherits the producer's credentials.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    cwd: str = Field(..., min_length=1)
    env_whitelist: dict[str, str] = Field(default_factory=dict)
    open_files: list[str] = Field(default_factory=list)
    active_branch: str | None = None
    recent_commands: list[str] = Field(default_factory=list)

    @field_validator("env_whitelist")
    @classmethod
    def _reject_secret_keys(cls, value: dict[str, str]) -> dict[str, str]:
        for key in value:
            if _ENV_DENYLIST_RE.search(key):
                raise ValueError(
                    f"env_whitelist key {key!r} matches a credential-keyword "
                    f"pattern; secrets must NOT travel in a HandoffBundle. "
                    f"The receiving CLI uses its own auth.",
                )
        return value


class HandoffBundle(BaseModel):
    """Normalized cross-CLI session state for handoff."""

    model_config = ConfigDict(frozen=True, strict=True)

    schema_version: str = "1"
    bundle_id: str = Field(..., min_length=1)
    project_slug: str | None = None
    session_id: str = Field(..., min_length=1)
    from_cli: CliId
    to_cli: CliId
    active_task: ActiveTask
    transcript_recent: list[TranscriptMessage] = Field(default_factory=list)
    transcript_digest: str | None = None
    memory_subset: MemorySubset = Field(default_factory=MemorySubset)
    tool_state: ToolState
    created_at: datetime
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("bundle_id", "session_id")
    @classmethod
    def _safe_path_component(cls, v: str) -> str:
        if not _PATH_COMPONENT_RE.fullmatch(v):
            raise ValueError(
                f"identifier {v!r} must match [A-Za-z0-9_-]+ "
                f"(no slashes, dots, or whitespace).",
            )
        return v

    @field_validator("project_slug")
    @classmethod
    def _safe_optional_slug(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not _PATH_COMPONENT_RE.fullmatch(v):
            raise ValueError(
                f"project_slug {v!r} must match [A-Za-z0-9_-]+ "
                f"(no slashes, dots, or whitespace).",
            )
        return v

    @field_validator("created_at")
    @classmethod
    def _ensure_tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("HandoffBundle.created_at must be timezone-aware (UTC).")
        return v.astimezone(UTC)

    @model_validator(mode="after")
    def _from_to_differ(self) -> Self:
        # Single source of truth for "no self-handoff". Replaces the old
        # field-order-fragile field_validator pair (one no-op, one using
        # ``info.data``); model_validator runs after every field is set,
        # so the check is robust regardless of field declaration order.
        if self.from_cli == self.to_cli:
            raise ValueError(
                f"HandoffBundle.to_cli must differ from from_cli "
                f"(both = {self.from_cli!r})",
            )
        return self
