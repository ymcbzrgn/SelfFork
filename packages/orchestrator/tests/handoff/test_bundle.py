"""Tests for :class:`HandoffBundle` schema."""

from __future__ import annotations

from datetime import UTC, datetime, timezone

import pytest
from pydantic import ValidationError

from selffork_orchestrator.handoff.bundle import (
    ActiveTask,
    HandoffBundle,
    MemorySubset,
    ToolState,
    TranscriptMessage,
)


def _ts() -> datetime:
    return datetime(2026, 5, 9, 14, 30, tzinfo=UTC)


def _bundle(**overrides: object) -> HandoffBundle:
    defaults: dict[str, object] = {
        "bundle_id": "handoff-1",
        "session_id": "session-abc",
        "from_cli": "claude-code",
        "to_cli": "codex",
        "active_task": ActiveTask(title="Wire M3 plan"),
        "tool_state": ToolState(cwd="/tmp/work"),
        "created_at": _ts(),
    }
    defaults.update(overrides)
    return HandoffBundle.model_validate(defaults)


# ── Component validation ──────────────────────────────────────────────────────


def test_active_task_requires_non_empty_title() -> None:
    with pytest.raises(ValidationError):
        ActiveTask(title="")


def test_transcript_message_round_index_must_be_non_negative() -> None:
    with pytest.raises(ValidationError):
        TranscriptMessage(role="operator", content="hi", round_index=-1)


def test_tool_state_requires_cwd() -> None:
    with pytest.raises(ValidationError):
        ToolState(cwd="")


def test_memory_subset_defaults() -> None:
    ms = MemorySubset()
    assert ms.t1_summary is None
    assert ms.t2_episode_ids == []
    assert ms.t3_relevant_facts == []


# ── HandoffBundle ────────────────────────────────────────────────────────────


def test_handoff_bundle_minimal_round_trip() -> None:
    b = _bundle()
    assert b.bundle_id == "handoff-1"
    assert b.from_cli == "claude-code"
    assert b.to_cli == "codex"
    assert b.created_at.tzinfo is UTC


def test_handoff_bundle_normalizes_non_utc_created_at() -> None:
    eastern = timezone.utcoffset.__self__ if False else None  # type: ignore[unreachable]
    from datetime import timedelta

    eastern = timezone(timedelta(hours=-5))
    b = _bundle(created_at=datetime(2026, 5, 9, 9, 30, tzinfo=eastern))
    assert b.created_at.tzinfo is UTC


def test_handoff_bundle_rejects_naive_created_at() -> None:
    with pytest.raises(ValidationError):
        _bundle(created_at=datetime(2026, 5, 9, 14, 30))


def test_handoff_bundle_rejects_self_handoff() -> None:
    with pytest.raises(ValidationError, match="must differ"):
        _bundle(from_cli="claude-code", to_cli="claude-code")


def test_handoff_bundle_rejects_unknown_cli() -> None:
    with pytest.raises(ValidationError):
        _bundle(to_cli="some-other-cli")


def test_handoff_bundle_with_transcript_round_trip() -> None:
    b = _bundle(
        transcript_recent=[
            TranscriptMessage(role="operator", content="hello", round_index=0),
            TranscriptMessage(role="cli", content="world", round_index=0),
        ],
        transcript_digest="Earlier rounds: built add().",
    )
    payload = b.model_dump_json()
    rehydrated = HandoffBundle.model_validate_json(payload)
    assert rehydrated == b


def test_handoff_bundle_metadata_optional() -> None:
    b = _bundle(metadata={"git_rev": "abc123", "mind_tier_revision": "v2"})
    assert b.metadata["git_rev"] == "abc123"


# ── Path-component sanitization (T3) ─────────────────────────────────────────


@pytest.mark.parametrize(
    "bad_id",
    [
        "../../../etc/passwd",
        "..",
        "abc/def",
        "abc\\def",
        "with space",
        "with.dot",
        "",
    ],
)
def test_handoff_bundle_rejects_path_traversal_in_bundle_id(bad_id: str) -> None:
    with pytest.raises(ValidationError):
        _bundle(bundle_id=bad_id)


@pytest.mark.parametrize("bad_id", ["../sneaky", "path/sep", "with space"])
def test_handoff_bundle_rejects_path_traversal_in_session_id(bad_id: str) -> None:
    with pytest.raises(ValidationError):
        _bundle(session_id=bad_id)


@pytest.mark.parametrize("bad_slug", ["../../etc", "with/slash", "path.dot"])
def test_handoff_bundle_rejects_path_traversal_in_project_slug(bad_slug: str) -> None:
    with pytest.raises(ValidationError):
        _bundle(project_slug=bad_slug)


def test_handoff_bundle_accepts_clean_identifiers() -> None:
    b = _bundle(
        bundle_id="handoff_42-rev_a",
        session_id="session-abc-123",
        project_slug="demo_v2",
    )
    assert b.bundle_id == "handoff_42-rev_a"
    assert b.session_id == "session-abc-123"
    assert b.project_slug == "demo_v2"


def test_handoff_bundle_project_slug_optional() -> None:
    b = _bundle(project_slug=None)
    assert b.project_slug is None


# ── env_whitelist secret denylist (T4) ───────────────────────────────────────


@pytest.mark.parametrize(
    "secret_key",
    [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GITHUB_TOKEN",
        "MY_SECRET",
        "OAUTH_TOKEN",
        "BEARER_TOKEN",
        "DB_PASSWORD",
        "DB_PASSWD",
        "USER_CREDENTIAL",
        "PRIVATE_KEY",
        "session_cookie",
        "openai_api_key",  # case-insensitive
    ],
)
def test_tool_state_rejects_secret_env_keys(secret_key: str) -> None:
    with pytest.raises(ValidationError, match="credential-keyword"):
        ToolState(cwd="/tmp/work", env_whitelist={secret_key: "super-secret"})


def test_tool_state_accepts_safe_env_keys() -> None:
    state = ToolState(
        cwd="/tmp/work",
        env_whitelist={"PATH": "/usr/bin", "HOME": "/Users/op", "CARGO_HOME": "/c"},
    )
    assert state.env_whitelist["PATH"] == "/usr/bin"


def test_tool_state_rejects_secret_even_when_other_keys_clean() -> None:
    """Single bad key in a whitelist of safe ones still fails (allow-list strict)."""
    with pytest.raises(ValidationError, match="credential-keyword"):
        ToolState(
            cwd="/tmp/work",
            env_whitelist={"PATH": "/usr/bin", "OPENAI_API_KEY": "sk-..."},
        )
