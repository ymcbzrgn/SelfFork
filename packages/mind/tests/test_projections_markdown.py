"""Tests for :mod:`selffork_mind.projections.markdown`."""

from __future__ import annotations

import json
from pathlib import Path

from selffork_mind.memory.model import Note
from selffork_mind.projections.markdown import (
    MarkdownProjection,
    MarkdownProjectionConfig,
)


def test_writes_index_and_topic_files(tmp_path: Path) -> None:
    config = MarkdownProjectionConfig(root=tmp_path)
    proj = MarkdownProjection(config)
    notes = [
        Note(
            tier="episodic",
            kind="observation",
            content="Operator likes BGE-M3",
            intent="embedder choice",
            session_id="s1",
        ),
        Note(
            tier="procedural",
            kind="pattern",
            content="Always run pytest before push",
            intent="pre-push routine",
        ),
    ]
    proj.write(notes)
    index = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
    assert "MEMORY.md" in index
    assert "embedder choice" in index
    assert "pre-push routine" in index

    topic_dir = tmp_path / "topics"
    files = list(topic_dir.glob("*.md"))
    assert len(files) == 2


def test_topic_file_has_json_frontmatter(tmp_path: Path) -> None:
    config = MarkdownProjectionConfig(root=tmp_path)
    proj = MarkdownProjection(config)
    note = Note(
        tier="semantic_graph",
        kind="decision",
        content="Use Graphiti bi-temporal model",
        intent="graph backend",
        project_slug="selffork",
    )
    proj.write([note])
    topic = (tmp_path / "topics" / f"{note.id}.md").read_text(encoding="utf-8")
    assert topic.startswith("---json\n")
    fm_block = topic.split("---json\n", 1)[1].split("\n---\n", 1)[0]
    payload = json.loads(fm_block)
    assert payload["tier"] == "semantic_graph"
    assert payload["kind"] == "decision"
    assert payload["intent"] == "graph backend"
    assert payload["project_slug"] == "selffork"


def test_index_caps_at_configured_lines(tmp_path: Path) -> None:
    config = MarkdownProjectionConfig(root=tmp_path, index_line_cap=8)
    proj = MarkdownProjection(config)
    notes = [
        Note(tier="episodic", kind="observation", content=f"n{i}", session_id="s")
        for i in range(20)
    ]
    proj.write(notes)
    index_lines = (tmp_path / "MEMORY.md").read_text(encoding="utf-8").splitlines()
    # 4 header lines + at most cap-1 entry lines + overflow note
    assert len(index_lines) <= 8 + 1
    assert any("more" in line for line in index_lines)
    # Topic files for ALL 20 notes still exist on disk.
    assert len(list((tmp_path / "topics").glob("*.md"))) == 20


def test_atomic_write_no_partial_files(tmp_path: Path) -> None:
    config = MarkdownProjectionConfig(root=tmp_path)
    proj = MarkdownProjection(config)
    proj.write([Note(tier="working", kind="observation", content="x")])
    leftovers = list(tmp_path.glob(".MEMORY.md.*.tmp"))
    assert leftovers == []


def test_topic_path_for_returns_expected_layout(tmp_path: Path) -> None:
    config = MarkdownProjectionConfig(root=tmp_path)
    proj = MarkdownProjection(config)
    note = Note(tier="working", kind="observation", content="x")
    expected = tmp_path / "topics" / f"{note.id}.md"
    assert proj.topic_path_for(note.id) == expected
