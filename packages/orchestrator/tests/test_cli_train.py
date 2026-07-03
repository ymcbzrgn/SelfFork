"""Tests for the ``selffork train`` CLI subcommand."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from selffork_orchestrator.cli import app
from selffork_reflex.data import validate_corpus_file


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_train_info_only_missing_manifest_prints_empty_state(
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    """Pre-M7 a missing manifest is the expected state; exit cleanly."""
    manifest = tmp_path / "absent.json"
    result = runner.invoke(
        app,
        ["train", "--info", "--adapter-manifest", str(manifest)],
    )
    assert result.exit_code == 0
    assert "No adapter manifest" in result.stdout


def test_train_info_only_with_real_manifest(
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        '{"version": "v0.3", "method": "QLoRA", '
        '"trained_at": "2026-05-01T00:00:00+00:00", "examples": 1234}',
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        ["train", "--info", "--adapter-manifest", str(manifest)],
    )
    assert result.exit_code == 0
    assert "v0.3" in result.stdout
    assert "QLoRA" in result.stdout


def test_train_plan_default_args_emits_m7_stub(
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    """Default invocation prints the would-be training plan."""
    manifest = tmp_path / "absent.json"
    # Point --audit-dir at an empty tmp dir so the default ``--dataset auto``
    # corpus step is hermetic (no real ~/.selffork/audit read) and skips.
    result = runner.invoke(
        app,
        ["train", "--adapter-manifest", str(manifest), "--audit-dir", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "QLoRA" in result.stdout
    assert "auto" in result.stdout.lower()
    assert "M7" in result.stdout


def test_train_custom_hyperparams_echoed(
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "absent.json"
    result = runner.invoke(
        app,
        [
            "train",
            "--adapter-manifest",
            str(manifest),
            "--audit-dir",
            str(tmp_path),
            "--method",
            "LoRA",
            "--lora-rank",
            "64",
            "--epochs",
            "5",
            "--target-modules",
            "attention+mlp",
        ],
    )
    assert result.exit_code == 0
    assert "LoRA" in result.stdout
    assert "64" in result.stdout
    assert " 5" in result.stdout
    assert "attention+mlp" in result.stdout


def test_train_rejects_invalid_method(
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "absent.json"
    result = runner.invoke(
        app,
        [
            "train",
            "--method",
            "NotARealMethod",
            "--adapter-manifest",
            str(manifest),
        ],
    )
    assert result.exit_code == 2


def test_train_rejects_invalid_target_modules(
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "absent.json"
    result = runner.invoke(
        app,
        [
            "train",
            "--target-modules",
            "all",
            "--adapter-manifest",
            str(manifest),
        ],
    )
    assert result.exit_code == 2


def test_train_rejects_zero_epochs(
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "absent.json"
    result = runner.invoke(
        app,
        ["train", "--epochs", "0", "--adapter-manifest", str(manifest)],
    )
    assert result.exit_code == 2


def test_train_rejects_negative_lora_rank(
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "absent.json"
    result = runner.invoke(
        app,
        ["train", "--lora-rank", "-1", "--adapter-manifest", str(manifest)],
    )
    assert result.exit_code == 2


def test_train_rejects_zero_lora_alpha(
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "absent.json"
    result = runner.invoke(
        app,
        ["train", "--lora-alpha", "0", "--adapter-manifest", str(manifest)],
    )
    assert result.exit_code == 2


def test_train_malformed_manifest_does_not_crash(
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    """A corrupted manifest must surface clean message and exit 0 on --info."""
    manifest = tmp_path / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text("{not json", encoding="utf-8")
    result = runner.invoke(
        app,
        ["train", "--info", "--adapter-manifest", str(manifest)],
    )
    assert result.exit_code == 0
    assert "invalid JSON" in result.stdout or "unreadable" in result.stdout


def _write_session(audit_dir: Path, session_id: str, texts: list[str]) -> None:
    """Write a synthetic session audit JSONL: a tool event + operator turn each."""
    ts = "2026-07-03T10:00:00+00:00"
    lines: list[str] = []
    for text in texts:
        lines.append(
            json.dumps(
                {
                    "ts": ts,
                    "category": "tool.call",
                    "event": "tool",
                    "payload": {"tool": "Read", "args": {"path": "a.py"}},
                }
            )
        )
        lines.append(
            json.dumps(
                {
                    "ts": ts,
                    "category": "selffork_jr.reply",
                    "event": "reply",
                    "payload": {"text": text},
                }
            )
        )
    (audit_dir / f"{session_id}.jsonl").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def test_train_dataset_auto_writes_validated_corpus(
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    """``--dataset auto`` assembles a schema-valid corpus + prints count/path."""
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir()
    _write_session(audit_dir, "sess_a", ["do the thing", "now ship it"])
    _write_session(audit_dir, "sess_b", ["review this"])
    out = tmp_path / "corpus" / "corpus.jsonl"
    manifest = tmp_path / "absent.json"

    result = runner.invoke(
        app,
        [
            "train",
            "--dataset",
            "auto",
            "--audit-dir",
            str(audit_dir),
            "--corpus-out",
            str(out),
            "--adapter-manifest",
            str(manifest),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "samples:" in result.stdout
    assert "corpus.jsonl" in result.stdout
    # Artifact exists and passes the T5 validator.
    assert out.is_file()
    report = validate_corpus_file(out)
    assert report.ok, report.errors
    assert report.sample_count == 3  # sess_a: 2 operator turns, sess_b: 1


def test_train_dataset_auto_empty_history_skips_gracefully(
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    """No session history -> skip assembly + still print the plan (exit 0)."""
    audit_dir = tmp_path / "empty_audit"
    audit_dir.mkdir()
    out = tmp_path / "c.jsonl"
    result = runner.invoke(
        app,
        [
            "train",
            "--dataset",
            "auto",
            "--audit-dir",
            str(audit_dir),
            "--corpus-out",
            str(out),
            "--adapter-manifest",
            str(tmp_path / "absent.json"),
        ],
    )
    assert result.exit_code == 0
    assert "M7" in result.stdout  # plan stub still printed
    assert not out.exists()  # nothing assembled -> no artifact written
