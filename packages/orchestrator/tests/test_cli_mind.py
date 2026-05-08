"""Smoke + behavioural tests for the ``selffork mind`` typer sub-app.

Each test creates a real :class:`DuckDBMindStore` under tmp_path, points
the CLI at it via env vars + a stub config, and exercises the surface
through ``typer.testing.CliRunner``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
import typer
from typer.testing import CliRunner

from selffork_orchestrator.cli_mind import _validate_kind, _validate_tier, mind_app

# ── helpers ────────────────────────────────────────────────────────────────


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def app() -> typer.Typer:
    return mind_app


@pytest.fixture
def stub_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Write a selffork.yaml with mind enabled + per-tmp_path storage roots."""
    storage_root = tmp_path / "mind"
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir()
    yaml = tmp_path / "selffork.yaml"
    yaml.write_text(
        f"""
audit:
  audit_dir: "{audit_dir}"
mind:
  enabled: true
  embedder: none
  reranker: none
  storage_root: "{storage_root}"
  projection_root: "{tmp_path / "mind" / "markdown"}"
  provenance_path: "{tmp_path / "mind" / "provenance.jsonl"}"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))  # so ~/.selffork resolves under tmp_path
    return yaml


def _audit_records(audit_dir: Path) -> Iterator[dict[str, object]]:
    for jsonl in sorted(audit_dir.glob("*.jsonl")):
        for line in jsonl.read_text(encoding="utf-8").strip().splitlines():
            if line:
                yield json.loads(line)


# ── _validate_* helpers ────────────────────────────────────────────────────


def test_validate_tier_accepts_known() -> None:
    assert _validate_tier("episodic") == "episodic"


def test_validate_tier_rejects_unknown() -> None:
    with pytest.raises(typer.BadParameter):
        _validate_tier("unknown")


def test_validate_tier_none() -> None:
    assert _validate_tier(None) is None


def test_validate_kind_accepts_known() -> None:
    assert _validate_kind("decision") == "decision"


def test_validate_kind_rejects_unknown() -> None:
    with pytest.raises(typer.BadParameter):
        _validate_kind("unknown")


# ── note add ───────────────────────────────────────────────────────────────


def test_note_add_emits_audit_and_persists(
    runner: CliRunner,
    app: typer.Typer,
    stub_config: Path,
    tmp_path: Path,
) -> None:
    result = runner.invoke(
        app,
        [
            "note",
            "add",
            "decision body",
            "--tier",
            "episodic",
            "--kind",
            "decision",
            "--intent",
            "lock embedder",
            "--config",
            str(stub_config),
            "--tag",
            "topic=embedder",
            "--tag",
            "kind=decision",
            "--path-scope",
            "packages/mind/**/*.py",
            "--importance",
            "5.0",
        ],
    )
    assert result.exit_code == 0, result.stderr
    assert "id:" in result.stdout
    audit_dir = tmp_path / "audit"
    cats = [rec["category"] for rec in _audit_records(audit_dir)]
    assert "mind.note.write" in cats


def test_note_add_invalid_tag_format(
    runner: CliRunner,
    app: typer.Typer,
    stub_config: Path,
) -> None:
    result = runner.invoke(
        app,
        [
            "note",
            "add",
            "x",
            "--tier",
            "episodic",
            "--kind",
            "observation",
            "--config",
            str(stub_config),
            "--tag",
            "no-equals-sign",
        ],
    )
    assert result.exit_code != 0


def test_note_add_unknown_tier(
    runner: CliRunner,
    app: typer.Typer,
    stub_config: Path,
) -> None:
    result = runner.invoke(
        app,
        [
            "note",
            "add",
            "x",
            "--tier",
            "totally-bogus",
            "--config",
            str(stub_config),
        ],
    )
    assert result.exit_code != 0


def test_note_add_when_mind_disabled(
    runner: CliRunner,
    app: typer.Typer,
    tmp_path: Path,
) -> None:
    yaml = tmp_path / "selffork.yaml"
    yaml.write_text(
        f"""
audit:
  audit_dir: "{tmp_path}/audit"
mind:
  enabled: false
""",
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        [
            "note",
            "add",
            "x",
            "--config",
            str(yaml),
        ],
    )
    assert result.exit_code != 0
    assert "Mind is disabled" in result.stderr


# ── recall ────────────────────────────────────────────────────────────────


def test_recall_no_hits_text(
    runner: CliRunner,
    app: typer.Typer,
    stub_config: Path,
) -> None:
    result = runner.invoke(
        app,
        [
            "recall",
            "anything",
            "--config",
            str(stub_config),
        ],
    )
    assert result.exit_code == 0
    assert "no hits" in result.stdout


def test_recall_finds_added_note(
    runner: CliRunner,
    app: typer.Typer,
    stub_config: Path,
) -> None:
    add = runner.invoke(
        app,
        [
            "note",
            "add",
            "OAuth flow with bge-m3",
            "--tier",
            "episodic",
            "--kind",
            "decision",
            "--intent",
            "lock embedder",
            "--config",
            str(stub_config),
        ],
    )
    assert add.exit_code == 0, add.stderr
    result = runner.invoke(
        app,
        [
            "recall",
            "oauth",
            "--config",
            str(stub_config),
        ],
    )
    assert result.exit_code == 0
    assert "lock embedder" in result.stdout


def test_recall_json_emits_jsonl(
    runner: CliRunner,
    app: typer.Typer,
    stub_config: Path,
) -> None:
    runner.invoke(
        app,
        [
            "note",
            "add",
            "kanban moved",
            "--tier",
            "episodic",
            "--kind",
            "observation",
            "--intent",
            "kanban event",
            "--config",
            str(stub_config),
        ],
    )
    result = runner.invoke(
        app,
        [
            "recall",
            "kanban",
            "--json",
            "--config",
            str(stub_config),
        ],
    )
    assert result.exit_code == 0
    lines = [line for line in result.stdout.strip().splitlines() if line]
    assert lines
    payload = json.loads(lines[0])
    assert "id" in payload
    assert "tier" in payload
    UUID(payload["id"])  # parses


def test_recall_emits_audit_event(
    runner: CliRunner,
    app: typer.Typer,
    stub_config: Path,
    tmp_path: Path,
) -> None:
    runner.invoke(app, ["recall", "x", "--config", str(stub_config)])
    cats = [rec["category"] for rec in _audit_records(tmp_path / "audit")]
    assert "mind.recall.query" in cats


# ── list ──────────────────────────────────────────────────────────────────


def test_list_empty_message(
    runner: CliRunner,
    app: typer.Typer,
    stub_config: Path,
) -> None:
    result = runner.invoke(app, ["list", "--config", str(stub_config)])
    assert result.exit_code == 0
    assert "no notes" in result.stdout


def test_list_after_add(
    runner: CliRunner,
    app: typer.Typer,
    stub_config: Path,
) -> None:
    runner.invoke(
        app,
        [
            "note",
            "add",
            "first note",
            "--intent",
            "first",
            "--config",
            str(stub_config),
        ],
    )
    runner.invoke(
        app,
        [
            "note",
            "add",
            "second note",
            "--intent",
            "second",
            "--config",
            str(stub_config),
        ],
    )
    result = runner.invoke(app, ["list", "--config", str(stub_config), "--limit", "5"])
    assert result.exit_code == 0
    assert "first" in result.stdout
    assert "second" in result.stdout


# ── show ──────────────────────────────────────────────────────────────────


def test_show_invalid_uuid(
    runner: CliRunner,
    app: typer.Typer,
    stub_config: Path,
) -> None:
    result = runner.invoke(app, ["show", "not-a-uuid", "--config", str(stub_config)])
    assert result.exit_code != 0


def test_show_unknown_id(
    runner: CliRunner,
    app: typer.Typer,
    stub_config: Path,
) -> None:
    result = runner.invoke(
        app,
        ["show", "00000000-0000-0000-0000-000000000000", "--config", str(stub_config)],
    )
    assert result.exit_code != 0


def test_show_after_add(
    runner: CliRunner,
    app: typer.Typer,
    stub_config: Path,
) -> None:
    add = runner.invoke(
        app,
        [
            "note",
            "add",
            "show me",
            "--intent",
            "show me",
            "--config",
            str(stub_config),
        ],
    )
    assert add.exit_code == 0, add.stderr
    note_id = next(
        (
            line.split("id: ", 1)[1].strip()
            for line in add.stdout.splitlines()
            if line.startswith("id:")
        ),
        None,
    )
    assert note_id is not None
    result = runner.invoke(app, ["show", note_id, "--config", str(stub_config)])
    assert result.exit_code == 0
    assert "show me" in result.stdout
    assert "tier:" in result.stdout


# ── supersede ─────────────────────────────────────────────────────────────


def test_supersede_decision_chain(
    runner: CliRunner,
    app: typer.Typer,
    stub_config: Path,
    tmp_path: Path,
) -> None:
    add = runner.invoke(
        app,
        [
            "note",
            "add",
            "old decision",
            "--kind",
            "decision",
            "--intent",
            "old",
            "--config",
            str(stub_config),
        ],
    )
    assert add.exit_code == 0
    note_id = next(
        line.split("id: ", 1)[1].strip()
        for line in add.stdout.splitlines()
        if line.startswith("id:")
    )
    result = runner.invoke(
        app,
        [
            "supersede",
            note_id,
            "--new-content",
            "new decision body",
            "--new-intent",
            "new",
            "--config",
            str(stub_config),
        ],
    )
    assert result.exit_code == 0
    assert "superseded:" in result.stdout
    cats = [rec["category"] for rec in _audit_records(tmp_path / "audit")]
    assert "mind.note.supersede" in cats


def test_supersede_invalid_id(
    runner: CliRunner,
    app: typer.Typer,
    stub_config: Path,
) -> None:
    result = runner.invoke(
        app,
        [
            "supersede",
            "not-a-uuid",
            "--new-content",
            "x",
            "--config",
            str(stub_config),
        ],
    )
    assert result.exit_code != 0


# ── compact (dry-run only in Order 2) ─────────────────────────────────────


def test_compact_distill_dry_run_zero_mutations(
    runner: CliRunner,
    app: typer.Typer,
    stub_config: Path,
    tmp_path: Path,
) -> None:
    """Regression: ``--strategy distill --dry-run`` MUST NOT write Procedural notes.

    Audit caught the original bug where ProceduralDistiller.distil() ran
    unconditionally, mutating the store under --dry-run. This test pins
    the new behaviour.
    """
    # Seed an episodic note so distill has something to chew on.
    runner.invoke(
        app,
        [
            "note",
            "add",
            "operator picked bge-m3",
            "--kind",
            "decision",
            "--config",
            str(stub_config),
        ],
    )
    # Snapshot stat list BEFORE the dry-run.
    stats_before = runner.invoke(app, ["stats", "--config", str(stub_config)])
    assert stats_before.exit_code == 0

    result = runner.invoke(
        app,
        [
            "compact",
            "--strategy",
            "distill",
            "--dry-run",
            "--config",
            str(stub_config),
        ],
    )
    assert result.exit_code == 0
    assert "dry-run" in result.stdout.lower() or "applied" not in result.stdout.lower()

    stats_after = runner.invoke(app, ["stats", "--config", str(stub_config)])
    # Post-dry-run, the per-tier counts must equal pre-dry-run — no
    # Procedural rows written.
    assert stats_after.stdout == stats_before.stdout, (
        "compact --strategy distill --dry-run mutated the store"
    )


def test_compact_dry_run_emits_audit(
    runner: CliRunner,
    app: typer.Typer,
    stub_config: Path,
    tmp_path: Path,
) -> None:
    runner.invoke(
        app,
        [
            "note",
            "add",
            "x",
            "--config",
            str(stub_config),
        ],
    )
    result = runner.invoke(
        app,
        [
            "compact",
            "--strategy",
            "recency",
            "--dry-run",
            "--config",
            str(stub_config),
        ],
    )
    assert result.exit_code == 0
    cats = [rec["category"] for rec in _audit_records(tmp_path / "audit")]
    assert "mind.compact.run" in cats


def test_compact_apply_now_works(
    runner: CliRunner,
    app: typer.Typer,
    stub_config: Path,
) -> None:
    """Order 3 unlocked --apply for L1-L3 strategies."""
    result = runner.invoke(
        app,
        [
            "compact",
            "--strategy",
            "recency",
            "--apply",
            "--config",
            str(stub_config),
        ],
    )
    assert result.exit_code == 0
    assert "applied" in result.stdout.lower()


def test_compact_llm_apply_redirects_to_reflect(
    runner: CliRunner,
    app: typer.Typer,
    stub_config: Path,
) -> None:
    """LLM strategy is now delegated to `selffork mind reflect`.

    Audit caught the stale ``Order 5`` gating message; the Order 5
    landing wires reflect for the Anthropic Auto Dream cycle and the
    compact-strategy=llm path is intentionally a dry-run preview only.
    """
    result = runner.invoke(
        app,
        [
            "compact",
            "--strategy",
            "llm",
            "--apply",
            "--config",
            str(stub_config),
        ],
    )
    assert result.exit_code != 0
    assert "selffork mind reflect" in result.stderr


def test_compact_unknown_strategy(
    runner: CliRunner,
    app: typer.Typer,
    stub_config: Path,
) -> None:
    result = runner.invoke(
        app,
        ["compact", "--strategy", "bogus", "--config", str(stub_config)],
    )
    assert result.exit_code != 0


# ── stats ─────────────────────────────────────────────────────────────────


def test_stats_no_db_yet(
    runner: CliRunner,
    app: typer.Typer,
    stub_config: Path,
) -> None:
    result = runner.invoke(app, ["stats", "--config", str(stub_config)])
    assert result.exit_code == 0
    assert "enabled" in result.stdout
    assert "embedder:" in result.stdout


def test_stats_after_writes_show_per_tier_counts(
    runner: CliRunner,
    app: typer.Typer,
    stub_config: Path,
) -> None:
    runner.invoke(
        app,
        [
            "note",
            "add",
            "obs",
            "--kind",
            "observation",
            "--config",
            str(stub_config),
        ],
    )
    runner.invoke(
        app,
        [
            "note",
            "add",
            "dec",
            "--kind",
            "decision",
            "--config",
            str(stub_config),
        ],
    )
    result = runner.invoke(app, ["stats", "--config", str(stub_config)])
    assert result.exit_code == 0
    assert "episodic" in result.stdout


# ── export-corpus stub ────────────────────────────────────────────────────


def test_export_corpus_writes_jsonl(
    runner: CliRunner,
    app: typer.Typer,
    stub_config: Path,
    tmp_path: Path,
) -> None:
    """Order 6 unlocked export-corpus: writes a JSONL for the tier."""
    out_path = tmp_path / "corpus.jsonl"
    # Empty Mind → empty corpus (no error).
    result = runner.invoke(
        app,
        [
            "export-corpus",
            "--tier",
            "procedural",
            "--out",
            str(out_path),
            "--config",
            str(stub_config),
        ],
    )
    assert result.exit_code == 0
    assert out_path.is_file()
    assert "exported" in result.stdout.lower()
