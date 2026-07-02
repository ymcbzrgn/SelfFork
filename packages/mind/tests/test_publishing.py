"""Tests for :mod:`selffork_mind.publishing.markdown_block`.

All filesystem tests use ``tmp_path`` -- nothing ever touches the real
repo-root agent files (ADR-009 §9 / ADR-002 §13).
"""

from __future__ import annotations

from pathlib import Path

from selffork_mind.publishing import (
    BEGIN_MARKER,
    DEFAULT_AGENT_FILENAMES,
    DEFAULT_MIND_BLOCK,
    END_MARKER,
    default_agent_files,
    publish_mind_block,
    publish_to_file,
    strip_block,
    upsert_block,
)

BLOCK = DEFAULT_MIND_BLOCK


# --------------------------------------------------------------------------
# Pure-function behaviour
# --------------------------------------------------------------------------


def test_fresh_insert_into_empty_text() -> None:
    out = upsert_block("", block=BLOCK)
    assert out.startswith(BEGIN_MARKER)
    assert out.rstrip("\n").endswith(END_MARKER)
    assert BLOCK in out
    # Exactly one sentinel pair.
    assert out.count(BEGIN_MARKER) == 1
    assert out.count(END_MARKER) == 1


def test_insert_appends_after_existing_content_with_blank_line() -> None:
    existing = "# My Project\n\nSome notes here.\n"
    out = upsert_block(existing, block=BLOCK)
    # Original content preserved verbatim at the front.
    assert out.startswith("# My Project\n\nSome notes here.")
    # Blank-line separator between content and the block.
    assert f"Some notes here.\n\n{BEGIN_MARKER}" in out


def test_idempotent_rerun_is_byte_identical() -> None:
    once = upsert_block("# Doc\n\nbody\n", block=BLOCK)
    twice = upsert_block(once, block=BLOCK)
    assert once == twice
    # And a third time, for good measure.
    assert upsert_block(twice, block=BLOCK) == once


def test_content_update_in_place_preserves_surroundings() -> None:
    before = "intro\n"
    after = "outro\n"
    doc = upsert_block(before, block="## Old\n\nold body")
    doc = doc.rstrip("\n") + "\n\n" + after  # content on both sides of block
    updated = upsert_block(doc, block="## New\n\nnew body")
    assert "old body" not in updated
    assert "new body" in updated
    # Surrounding text on both sides survives, still one block.
    assert updated.startswith("intro")
    assert "outro" in updated
    assert updated.count(BEGIN_MARKER) == 1
    assert updated.count(END_MARKER) == 1


def test_update_does_not_move_block_position() -> None:
    doc = "top\n\n" + upsert_block("", block="## A\n\naaa").rstrip("\n") + "\n\nbottom\n"
    updated = upsert_block(doc, block="## B\n\nbbb")
    # Block stays between "top" and "bottom" rather than jumping to EOF.
    top_idx = updated.index("top")
    begin_idx = updated.index(BEGIN_MARKER)
    bottom_idx = updated.index("bottom")
    assert top_idx < begin_idx < bottom_idx


# --------------------------------------------------------------------------
# strip / round-trip
# --------------------------------------------------------------------------


def test_strip_round_trip_restores_eof_text() -> None:
    original = "# Title\n\nSome content.\n"
    with_block = upsert_block(original, block=BLOCK)
    assert BEGIN_MARKER in with_block
    stripped = strip_block(with_block)
    assert BEGIN_MARKER not in stripped
    assert END_MARKER not in stripped
    # Block appended at EOF -> strip restores byte-for-byte.
    assert stripped == original


def test_strip_is_noop_when_absent() -> None:
    text = "# Nothing to strip here\n"
    assert strip_block(text) == text


def test_strip_is_idempotent() -> None:
    with_block = upsert_block("# Doc\n\nbody\n", block=BLOCK)
    once = strip_block(with_block)
    twice = strip_block(once)
    assert once == twice


def test_strip_preserves_content_after_a_mid_document_block() -> None:
    doc = "A\n\n" + upsert_block("", block="## Mid\n\nx").rstrip("\n") + "\n\nB\n"
    stripped = strip_block(doc)
    assert "A" in stripped
    assert "B" in stripped
    assert BEGIN_MARKER not in stripped


# --------------------------------------------------------------------------
# Half / malformed markers
# --------------------------------------------------------------------------


def test_half_marker_only_begin_is_left_untouched_and_new_block_appended() -> None:
    text = f"prefix\n{BEGIN_MARKER}\ndangling begin, no end\n"
    out = upsert_block(text, block=BLOCK)
    # The stray BEGIN is not treated as a region: a fresh full block appears.
    assert out.count(END_MARKER) == 1
    assert "dangling begin, no end" in out
    assert BLOCK in out


def test_half_marker_only_end_is_left_untouched_by_strip() -> None:
    text = f"prefix\n{END_MARKER}\norphan end\n"
    # No full region -> strip is a no-op.
    assert strip_block(text) == text


# --------------------------------------------------------------------------
# default_agent_files
# --------------------------------------------------------------------------


def test_default_agent_files_returns_four_repo_root_files(tmp_path: Path) -> None:
    files = default_agent_files(tmp_path)
    assert [f.name for f in files] == list(DEFAULT_AGENT_FILENAMES)
    assert [f.name for f in files] == ["AGENTS.md", "CLAUDE.md", "GEMINI.md", "AGENT.md"]
    assert all(f.parent == tmp_path for f in files)


# --------------------------------------------------------------------------
# publish_to_file
# --------------------------------------------------------------------------


def test_publish_to_file_creates_missing_file_and_parents(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "dir" / "AGENTS.md"
    assert not target.exists()
    changed = publish_to_file(target, BLOCK)
    assert changed is True
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    assert BEGIN_MARKER in content
    assert END_MARKER in content


def test_publish_to_file_is_idempotent_second_call_returns_false(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    first = publish_to_file(target, BLOCK)
    before = target.read_text(encoding="utf-8")
    second = publish_to_file(target, BLOCK)
    after = target.read_text(encoding="utf-8")
    assert first is True
    assert second is False
    assert before == after


def test_publish_to_file_updates_changed_block(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    publish_to_file(target, "## v1\n\nfirst")
    changed = publish_to_file(target, "## v2\n\nsecond")
    assert changed is True
    content = target.read_text(encoding="utf-8")
    assert "second" in content
    assert "first" not in content
    assert content.count(BEGIN_MARKER) == 1


def test_publish_to_file_preserves_pre_existing_content(tmp_path: Path) -> None:
    target = tmp_path / "CLAUDE.md"
    target.write_text("# Hand-written\n\nOperator notes.\n", encoding="utf-8")
    publish_to_file(target, BLOCK)
    content = target.read_text(encoding="utf-8")
    assert content.startswith("# Hand-written\n\nOperator notes.")
    assert BEGIN_MARKER in content


def test_publish_to_file_handles_empty_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "AGENT.md"
    target.write_text("", encoding="utf-8")
    changed = publish_to_file(target, BLOCK)
    assert changed is True
    assert BEGIN_MARKER in target.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# publish_mind_block (multi-file)
# --------------------------------------------------------------------------


def test_publish_mind_block_writes_all_default_files(tmp_path: Path) -> None:
    result = publish_mind_block(tmp_path, BLOCK)
    assert set(result.keys()) == set(default_agent_files(tmp_path))
    assert all(result.values())  # every file created
    for path in default_agent_files(tmp_path):
        assert path.exists()
        assert BEGIN_MARKER in path.read_text(encoding="utf-8")


def test_publish_mind_block_second_run_reports_no_changes(tmp_path: Path) -> None:
    publish_mind_block(tmp_path, BLOCK)
    snapshot = {
        p: p.read_text(encoding="utf-8") for p in default_agent_files(tmp_path)
    }
    result = publish_mind_block(tmp_path, BLOCK)
    assert not any(result.values())  # nothing changed
    for path in default_agent_files(tmp_path):
        assert path.read_text(encoding="utf-8") == snapshot[path]
