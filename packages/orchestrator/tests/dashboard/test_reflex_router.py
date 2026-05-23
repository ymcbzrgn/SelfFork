"""Tests for :mod:`selffork_orchestrator.dashboard.reflex_router`.

S4 honesty pass — confirms /adapter no longer returns hardcoded fake
values and /train no longer reports the fake "5h 18m" heuristic
estimate. Both surfaces must accurately reflect the pre-M7 state.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from selffork_orchestrator.dashboard import reflex_router as reflex_router_module
from selffork_orchestrator.dashboard.reflex_router import build_reflex_router


def _build() -> TestClient:
    app = FastAPI()
    app.include_router(build_reflex_router())
    return TestClient(app)


def test_adapter_returns_honest_empty_when_no_manifest(
    tmp_path: Path, monkeypatch
) -> None:
    """Pre-M7: no manifest file → adapter_trained=False + message."""
    missing = tmp_path / "manifest.json"  # never created
    monkeypatch.setattr(
        reflex_router_module, "ADAPTER_MANIFEST_PATH", missing
    )

    # The endpoint uses the module-level constant; rebuild the router
    # so the closure picks up the patched path. The helper that reads
    # the manifest takes the constant as a default arg, so we re-call.
    info = reflex_router_module._read_adapter_manifest(missing)
    assert info.adapter_trained is False
    assert info.version is None
    assert info.age_days is None
    assert info.examples is None
    assert info.method is None
    assert info.message is not None
    assert "No adapter trained yet" in info.message


def test_adapter_reads_real_manifest_when_present(tmp_path: Path) -> None:
    """When a manifest file exists, fields come from it (no placeholders)."""
    manifest = tmp_path / "manifest.json"
    trained_at = (
        datetime.now(UTC) - timedelta(days=12)
    ).isoformat()
    manifest.write_text(
        json.dumps(
            {
                "version": "v0.1",
                "trained_at": trained_at,
                "examples": 5000,
                "method": "QLoRA",
            }
        ),
        encoding="utf-8",
    )
    info = reflex_router_module._read_adapter_manifest(manifest)
    assert info.adapter_trained is True
    assert info.version == "v0.1"
    assert info.trained_at == trained_at
    assert info.age_days == 12
    assert info.examples == 5000
    assert info.method == "QLoRA"
    assert info.message is None


def test_adapter_handles_unreadable_manifest(tmp_path: Path) -> None:
    """A corrupt JSON file produces a non-trained empty + diagnostic."""
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{ not valid json", encoding="utf-8")
    info = reflex_router_module._read_adapter_manifest(manifest)
    assert info.adapter_trained is False
    assert info.message is not None
    assert "unreadable" in info.message


def test_train_queue_returns_no_fake_estimate() -> None:
    """``estimated_seconds`` MUST be None pre-M7 (no fake 5h 18m)."""
    client = _build()
    r = client.post(
        "/api/reflex/train",
        json={
            "dataset_source": "auto",
            "hyperparams": {
                "method": "QLoRA",
                "lora_rank": 32,
                "lora_alpha": 16,
                "learning_rate": "2e-4",
                "epochs": 3,
                "target_modules": "attention only",
            },
        },
    )
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued"
    assert body["estimated_seconds"] is None, (
        "Pre-M7 must not fabricate a training-time estimate"
    )
    assert any(
        "M7" in line for line in body["log_tail"]
    ), "log_tail must surface the M7 deferral"


def test_train_manual_requires_dataset_path() -> None:
    client = _build()
    r = client.post(
        "/api/reflex/train",
        json={
            "dataset_source": "manual",
            "hyperparams": {
                "method": "QLoRA",
                "lora_rank": 32,
                "lora_alpha": 16,
                "learning_rate": "2e-4",
                "epochs": 3,
                "target_modules": "attention only",
            },
        },
    )
    assert r.status_code == 400


def test_train_status_round_trip() -> None:
    client = _build()
    r = client.post(
        "/api/reflex/train",
        json={"dataset_source": "auto", "hyperparams": {}},
    )
    job_id = r.json()["job_id"]
    s = client.get(f"/api/reflex/training-status/{job_id}")
    assert s.status_code == 200
    assert s.json()["job_id"] == job_id

    listing = client.get("/api/reflex/training-status")
    assert listing.status_code == 200
    assert any(j["job_id"] == job_id for j in listing.json())


def test_adapter_endpoint_returns_no_hardcoded_values() -> None:
    """End-to-end via the router itself; no fake v1.2 / 8432 / 47d."""
    client = _build()
    r = client.get("/api/reflex/adapter")
    assert r.status_code == 200
    body = r.json()
    # Regression guard for the previous sahte placeholder.
    if body["adapter_trained"] is False:
        assert body["version"] is None
        assert body["examples"] is None
        assert body["age_days"] is None
    # If a real manifest happens to exist on the dev machine, those
    # values are real — the test still passes because the guard only
    # blocks the synthesized v1.2/47d/8432 triplet.
    assert body.get("version") != "v1.2"
    assert body.get("examples") != 8432
    assert body.get("age_days") != 47


def test_int_or_none_rejects_bool_as_examples_count(tmp_path: Path) -> None:
    """audit-god MAJOR #1 regression: a manifest ``"examples": true``
    must NOT be reported as ``examples=1``. Bool is a subclass of int
    in Python so the helper must guard explicitly."""
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "v0.1",
                "trained_at": None,
                "examples": True,
                "method": "QLoRA",
            }
        ),
        encoding="utf-8",
    )
    info = reflex_router_module._read_adapter_manifest(manifest)
    assert info.adapter_trained is True
    assert info.examples is None  # NOT 1


def test_int_or_none_rejects_string_examples(tmp_path: Path) -> None:
    """audit-god MINOR #6 regression: string-encoded numbers must be
    rejected (no permissive coercion masquerading as real values)."""
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "v0.1",
                "trained_at": None,
                "examples": "5000",
                "method": "QLoRA",
            }
        ),
        encoding="utf-8",
    )
    info = reflex_router_module._read_adapter_manifest(manifest)
    assert info.examples is None


def test_int_or_none_rejects_float_examples(tmp_path: Path) -> None:
    """audit-god MINOR #6 regression: float values must not silently
    truncate to int."""
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "v0.1",
                "trained_at": None,
                "examples": 5000.7,
                "method": "QLoRA",
            }
        ),
        encoding="utf-8",
    )
    info = reflex_router_module._read_adapter_manifest(manifest)
    assert info.examples is None
