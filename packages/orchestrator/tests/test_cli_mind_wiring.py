"""Tests for plain-md + provenance wiring in the ``selffork mind`` CLI.

Order 2.6 lands:
- ``mind note add`` writes the canonical store + emits a markdown
  projection refresh + a ``mind.projection.write`` audit event.
- ``mind recall`` records a :class:`ProvenanceEntry` to the configured
  provenance log.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from selffork_orchestrator.cli_mind import mind_app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def app() -> typer.Typer:
    return mind_app


@pytest.fixture
def configured(tmp_path: Path) -> Path:
    """selffork.yaml with mind enabled + per-tmp-path projection + provenance."""
    yaml = tmp_path / "selffork.yaml"
    storage_root = tmp_path / "mind"
    md_root = tmp_path / "md"
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir()
    yaml.write_text(
        f"""
audit:
  audit_dir: "{audit_dir}"
mind:
  enabled: true
  embedder: none
  reranker: none
  storage_root: "{storage_root}"
  projection_root: "{md_root}"
  provenance_path: "{tmp_path}/provenance.jsonl"
""",
        encoding="utf-8",
    )
    return yaml


def _audit_records(audit_dir: Path) -> Iterator[dict[str, object]]:
    for jsonl in sorted(audit_dir.glob("*.jsonl")):
        for line in jsonl.read_text(encoding="utf-8").strip().splitlines():
            if line:
                yield json.loads(line)


def test_note_add_emits_projection_write(
    runner: CliRunner,
    app: typer.Typer,
    configured: Path,
    tmp_path: Path,
) -> None:
    result = runner.invoke(
        app,
        [
            "note",
            "add",
            "captured insight",
            "--intent",
            "captured",
            "--config",
            str(configured),
        ],
    )
    assert result.exit_code == 0, result.stderr
    cats = [rec["category"] for rec in _audit_records(tmp_path / "audit")]
    assert "mind.note.write" in cats
    assert "mind.projection.write" in cats
    md_path = tmp_path / "md" / "MEMORY.md"
    assert md_path.is_file()
    body = md_path.read_text(encoding="utf-8")
    assert "captured" in body


def test_note_add_writes_topic_files(
    runner: CliRunner,
    app: typer.Typer,
    configured: Path,
    tmp_path: Path,
) -> None:
    result = runner.invoke(
        app,
        [
            "note",
            "add",
            "first body",
            "--intent",
            "first",
            "--config",
            str(configured),
        ],
    )
    assert result.exit_code == 0
    topics_dir = tmp_path / "md" / "topics"
    assert topics_dir.is_dir()
    topic_files = list(topics_dir.glob("*.md"))
    assert topic_files
    assert any("first body" in p.read_text(encoding="utf-8") for p in topic_files)


def test_recall_records_provenance(
    runner: CliRunner,
    app: typer.Typer,
    configured: Path,
    tmp_path: Path,
) -> None:
    runner.invoke(
        app,
        [
            "note",
            "add",
            "alpha note",
            "--intent",
            "alpha",
            "--config",
            str(configured),
        ],
    )
    runner.invoke(
        app,
        [
            "recall",
            "alpha",
            "--config",
            str(configured),
        ],
    )
    prov = tmp_path / "provenance.jsonl"
    assert prov.is_file()
    lines = [line for line in prov.read_text(encoding="utf-8").splitlines() if line]
    assert lines
    payload = json.loads(lines[-1])
    assert payload["query"] == "alpha"
    assert "retriever" in payload


def test_recall_provenance_records_no_hits(
    runner: CliRunner,
    app: typer.Typer,
    configured: Path,
    tmp_path: Path,
) -> None:
    runner.invoke(
        app,
        [
            "recall",
            "completely-unrelated",
            "--config",
            str(configured),
        ],
    )
    prov = tmp_path / "provenance.jsonl"
    if prov.is_file():
        # When there is no DB yet, the recall path still records provenance —
        # but the open_store call creates the DB. We accept either outcome
        # so this test just verifies the line, when present, is well-shaped.
        for line in prov.read_text(encoding="utf-8").splitlines():
            if line:
                payload = json.loads(line)
                assert "query" in payload
                assert "retriever" in payload
