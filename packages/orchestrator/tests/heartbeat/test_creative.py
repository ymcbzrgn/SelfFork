"""S-Auto Faz F — CreativeScopeGate + IdeationManager + IDEATE executor tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from selffork_orchestrator.heartbeat.actions import LegalAction
from selffork_orchestrator.heartbeat.creative import (
    DEFAULT_LARGE_KEYWORDS,
    DEFAULT_LARGE_WORD_COUNT,
    DEFAULT_MEDIUM_WORD_COUNT,
    CreativeScopeGate,
    IdeaSize,
    IdeationManager,
    default_lab_root,
)
from selffork_orchestrator.heartbeat.deliberation import ActionDecision
from selffork_orchestrator.heartbeat.executor import ActionExecutor
from selffork_orchestrator.heartbeat.filter import (
    DEFAULT_CLI_IDS,
    DEFAULT_QUOTA_EXHAUSTION_THRESHOLD_PCT,
    WorldState,
)


def _state(**overrides: object) -> WorldState:
    base: dict[str, object] = dict(
        pause_active=False,
        within_active_hours=True,
        active_concurrent_sessions=0,
        max_concurrent_sessions=1,
        creative_mode_enabled=True,
        cli_quota={cli: None for cli in DEFAULT_CLI_IDS},
        quota_exhaustion_threshold_pct=DEFAULT_QUOTA_EXHAUSTION_THRESHOLD_PCT,
        supervised_mode=False,
        last_active_workspace="alpha",
    )
    base.update(overrides)
    return WorldState(**base)  # type: ignore[arg-type]


# ── CreativeScopeGate.classify ────────────────────────────────────


def test_scope_gate_empty_text_is_small() -> None:
    gate = CreativeScopeGate()
    assert gate.classify("") is IdeaSize.SMALL
    assert gate.classify("   ") is IdeaSize.SMALL


def test_scope_gate_short_text_is_small() -> None:
    gate = CreativeScopeGate()
    assert gate.classify("Buton rengini değiştir") is IdeaSize.SMALL


def test_scope_gate_medium_word_count() -> None:
    gate = CreativeScopeGate(medium_word_count=10, large_word_count=20)
    text = " ".join(["word"] * 15)
    assert gate.classify(text) is IdeaSize.MEDIUM


def test_scope_gate_large_word_count() -> None:
    gate = CreativeScopeGate(medium_word_count=10, large_word_count=20)
    text = " ".join(["word"] * 25)
    assert gate.classify(text) is IdeaSize.LARGE


def test_scope_gate_large_keyword_forces_large() -> None:
    """Tiny text with a heavy keyword still classifies as large."""
    gate = CreativeScopeGate()
    assert gate.classify("new project: oauth") is IdeaSize.LARGE
    assert gate.classify("yeni proje açalım") is IdeaSize.LARGE


@pytest.mark.parametrize("keyword", list(DEFAULT_LARGE_KEYWORDS[:5]))
def test_scope_gate_default_keywords_force_large(keyword: str) -> None:
    gate = CreativeScopeGate()
    assert gate.classify(f"x {keyword} y") is IdeaSize.LARGE


def test_scope_gate_keyword_case_insensitive() -> None:
    gate = CreativeScopeGate()
    assert gate.classify("REWRITE everything") is IdeaSize.LARGE


def test_scope_gate_rejects_invalid_thresholds() -> None:
    with pytest.raises(ValueError):
        CreativeScopeGate(medium_word_count=0, large_word_count=1)
    with pytest.raises(ValueError):
        CreativeScopeGate(medium_word_count=10, large_word_count=10)


def test_scope_gate_defaults_are_sane() -> None:
    assert DEFAULT_MEDIUM_WORD_COUNT < DEFAULT_LARGE_WORD_COUNT


# ── IdeationManager.record_idea ───────────────────────────────────


def test_record_idea_writes_markdown(tmp_path: Path) -> None:
    manager = IdeationManager(lab_root=tmp_path / "lab")
    record = manager.record_idea(
        text="Add a dark mode toggle to the dashboard",
        project_slug="alpha",
    )
    assert record.path.is_file()
    body = record.path.read_text(encoding="utf-8")
    assert "Add a dark mode toggle to the dashboard" in body
    assert f"idea_id:** `{record.idea_id}`" in body
    assert f"size:** `{record.size.value}`" in body
    assert "project:** `alpha`" in body


def test_record_idea_creates_lab_root(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "lab"
    manager = IdeationManager(lab_root=target)
    record = manager.record_idea(text="tiny idea")
    assert record.path.parent == target
    assert target.is_dir()


def test_record_idea_filename_includes_size(tmp_path: Path) -> None:
    manager = IdeationManager(lab_root=tmp_path)
    record_small = manager.record_idea(text="small one")
    record_large = manager.record_idea(text="new project: huge")
    assert "small" in record_small.path.name
    assert "large" in record_large.path.name


def test_record_idea_title_first_line(tmp_path: Path) -> None:
    manager = IdeationManager(lab_root=tmp_path)
    record = manager.record_idea(text="My grand idea\nwith more details on subsequent lines")
    assert record.title == "My grand idea"


def test_record_idea_global_when_no_project(tmp_path: Path) -> None:
    manager = IdeationManager(lab_root=tmp_path)
    record = manager.record_idea(text="cross-project insight")
    assert record.project_slug is None
    body = record.path.read_text(encoding="utf-8")
    assert "project:** `(global)`" in body


def test_record_idea_size_propagates_to_record(tmp_path: Path) -> None:
    manager = IdeationManager(lab_root=tmp_path)
    record = manager.record_idea(text="new project: refactor everything")
    assert record.size is IdeaSize.LARGE


def test_list_ideas_returns_files_newest_first(tmp_path: Path) -> None:
    import time

    manager = IdeationManager(lab_root=tmp_path)
    first = manager.record_idea(text="first")
    time.sleep(0.01)  # ensure mtime differs
    second = manager.record_idea(text="second")
    listing = manager.list_ideas()
    assert listing[0] == second.path
    assert listing[1] == first.path


def test_list_ideas_empty_dir(tmp_path: Path) -> None:
    manager = IdeationManager(lab_root=tmp_path / "absent")
    assert manager.list_ideas() == []


def test_default_lab_root_under_selffork() -> None:
    root = default_lab_root()
    assert "selffork" in str(root)
    assert root.name == "ideas"


# ── ActionExecutor IDEATE handler ─────────────────────────────────


def _decision(reasoning: str) -> ActionDecision:
    return ActionDecision(action=LegalAction.IDEATE, reasoning=reasoning)


@pytest.mark.asyncio
async def test_ideate_without_manager_defers() -> None:
    executor = ActionExecutor(ideation_manager=None)
    result = await executor.execute(_decision("an idea"), _state())
    assert result.outcome == "deferred"


@pytest.mark.asyncio
async def test_ideate_empty_reasoning_skips(tmp_path: Path) -> None:
    executor = ActionExecutor(ideation_manager=IdeationManager(lab_root=tmp_path))
    result = await executor.execute(_decision(""), _state())
    assert result.outcome == "skipped"


@pytest.mark.asyncio
async def test_ideate_records_idea_and_returns_metadata(
    tmp_path: Path,
) -> None:
    executor = ActionExecutor(ideation_manager=IdeationManager(lab_root=tmp_path))
    result = await executor.execute(
        _decision("Magic-link auth flow düşünüyorum"),
        _state(last_active_workspace="auth-proj"),
    )
    assert result.outcome == "executed"
    assert result.action is LegalAction.IDEATE
    assert "idea_id" in result.metadata
    assert result.metadata["project_slug"] == "auth-proj"
    saved_path = Path(result.metadata["path"])  # type: ignore[arg-type]
    assert saved_path.is_file()


@pytest.mark.asyncio
async def test_ideate_large_keyword_size_reflected(tmp_path: Path) -> None:
    executor = ActionExecutor(ideation_manager=IdeationManager(lab_root=tmp_path))
    result = await executor.execute(
        _decision("new project: tamamen yeniden mimari"),
        _state(),
    )
    assert result.metadata["size"] == "large"
