"""FastAPI router for the Reflex pillar — fine-tune trigger + status.

ADR-006 §7.1 — the cockpit Settings page lets the operator kick off
training from the UI (dataset path + hyperparams + training endpoint).
The Reflex package itself is M7 scope; this router lands the
**operator-facing surface** so the UI has somewhere to talk to.

S4 honesty pass (no-mock S4-S8 rule):

* ``/adapter`` no longer returns a hardcoded placeholder. It reads
  ``~/.selffork/reflex/adapters/<current>/manifest.json`` when the
  file exists; otherwise it returns ``adapter_trained=False`` with a
  message explaining the M7 dependency. No fake version numbers.
* ``/train`` no longer reports a fake ``estimated_seconds`` heuristic.
  Estimates come from the real worker (M7); pre-M7 the field stays
  ``None`` and the ``log_tail`` says so plainly.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "AdapterInfoResponse",
    "HyperParams",
    "StartTrainingRequest",
    "TrainingJobResponse",
    "build_reflex_router",
]

_log = logging.getLogger(__name__)

TrainStatus = Literal["queued", "running", "completed", "errored"]

ADAPTER_MANIFEST_PATH = Path(
    "~/.selffork/reflex/adapters/current/manifest.json"
).expanduser()
"""M7 worker writes the active adapter manifest here. Pre-M7 the path
does not exist — the GET ``/adapter`` endpoint returns an honest empty
state until the first training job lands."""


class HyperParams(BaseModel):
    method: Literal["QLoRA", "LoRA", "Full"] = "QLoRA"
    lora_rank: int = 32
    lora_alpha: int = 16
    learning_rate: str = "2e-4"
    epochs: int = 3
    target_modules: Literal["attention only", "attention + MLP"] = (
        "attention only"
    )


class StartTrainingRequest(BaseModel):
    dataset_source: Literal["auto", "manual"] = "auto"
    dataset_path: str | None = None
    hyperparams: HyperParams = HyperParams()
    training_endpoint: str | None = None  # None = use model endpoint


class TrainingJobResponse(BaseModel):
    job_id: str
    status: TrainStatus
    started_at: str
    estimated_seconds: int | None = None
    progress_percent: int = 0
    log_tail: list[str] = Field(default_factory=list)
    error: str | None = None


class AdapterInfoResponse(BaseModel):
    """Current-adapter metadata for the Settings UI.

    ``adapter_trained=False`` means no manifest exists yet (pre-M7);
    the UI shows a "No adapter trained yet" empty state instead of
    rendering version / age / examples. After M7 ships, the worker
    writes a real manifest and ``adapter_trained=True`` with the rest
    of the fields populated.
    """

    model_config = ConfigDict(extra="forbid")

    adapter_trained: bool
    version: str | None = None
    trained_at: str | None = None
    age_days: int | None = None
    examples: int | None = None
    method: str | None = None
    message: str | None = None


# Process-local job registry (no DB persistence yet — M7 wires this in).
_JOBS: dict[str, TrainingJobResponse] = {}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _compute_age_days(trained_at: str | None) -> int | None:
    if not trained_at:
        return None
    try:
        ts = datetime.fromisoformat(trained_at)
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    delta = datetime.now(UTC) - ts
    return max(0, delta.days)


def _read_adapter_manifest(
    path: Path = ADAPTER_MANIFEST_PATH,
) -> AdapterInfoResponse:
    """Read the active adapter manifest, or return an honest empty state."""
    if not path.is_file():
        return AdapterInfoResponse(
            adapter_trained=False,
            message=(
                "No adapter trained yet. Reflex fine-tune worker lands "
                "in M7 — once an adapter exists at "
                "~/.selffork/reflex/adapters/current/manifest.json this "
                "panel will show its real version and age."
            ),
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _log.warning(
            "reflex_adapter_manifest_unreadable",
            extra={"path": str(path), "error": str(exc)},
        )
        return AdapterInfoResponse(
            adapter_trained=False,
            message=f"manifest at {path} is unreadable: {exc}",
        )
    if not isinstance(data, dict):
        return AdapterInfoResponse(
            adapter_trained=False,
            message=f"manifest at {path} is not a JSON object",
        )
    return AdapterInfoResponse(
        adapter_trained=True,
        version=_str_or_none(data.get("version")),
        trained_at=_str_or_none(data.get("trained_at")),
        age_days=_compute_age_days(_str_or_none(data.get("trained_at"))),
        examples=_int_or_none(data.get("examples")),
        method=_str_or_none(data.get("method")),
    )


def _str_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _int_or_none(value: object) -> int | None:
    """Honest int extractor for the manifest reader.

    The reflex /adapter endpoint exists to **avoid** synthesised
    placeholders — so this helper refuses anything that isn't already
    a plain ``int``. Bool is rejected explicitly because it is a
    subclass of int (audit-god MAJOR #1: a manifest value of ``true``
    must not be reported as ``examples=1``). Floats and string-encoded
    ints are also rejected — the M7 worker is the sole writer of the
    manifest and should produce typed integers; anything else hints
    at corruption and should surface as an empty field rather than a
    permissive coercion.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def build_reflex_router() -> APIRouter:
    router = APIRouter(prefix="/api/reflex", tags=["reflex"])

    @router.post("/train", response_model=TrainingJobResponse, status_code=202)
    async def start_training(req: StartTrainingRequest) -> TrainingJobResponse:
        """Queue a fine-tune job.

        Pre-M7 this records the job intent in a process-local registry;
        no real training happens. The UI polls
        ``/training-status/<id>`` and renders ``status='queued'``.
        M7 replaces this with a real Reflex training worker (QLoRA on
        remote GPU per ADR-006 §9.6) that updates the same job row.
        """
        if req.dataset_source == "manual" and not req.dataset_path:
            raise HTTPException(
                status_code=400,
                detail=(
                    "dataset_path is required when "
                    "dataset_source='manual'"
                ),
            )
        job_id = uuid.uuid4().hex[:12]
        log_intro = (
            f"queued: method={req.hyperparams.method} "
            f"rank={req.hyperparams.lora_rank} "
            f"epochs={req.hyperparams.epochs}"
        )
        job = TrainingJobResponse(
            job_id=job_id,
            status="queued",
            started_at=_utc_now(),
            estimated_seconds=None,
            progress_percent=0,
            log_tail=[
                log_intro,
                "Real training worker lands in M7. Job stays queued.",
            ],
        )
        _JOBS[job_id] = job
        return job

    @router.get(
        "/training-status/{job_id}", response_model=TrainingJobResponse
    )
    async def training_status(job_id: str) -> TrainingJobResponse:
        job = _JOBS.get(job_id)
        if job is None:
            raise HTTPException(
                status_code=404, detail=f"unknown job {job_id}"
            )
        return job

    @router.get(
        "/training-status", response_model=list[TrainingJobResponse]
    )
    async def list_jobs() -> list[TrainingJobResponse]:
        return sorted(
            _JOBS.values(), key=lambda j: j.started_at, reverse=True
        )

    @router.get("/adapter", response_model=AdapterInfoResponse)
    async def adapter_info() -> AdapterInfoResponse:
        """Currently-loaded adapter metadata.

        Reads ``~/.selffork/reflex/adapters/current/manifest.json``
        when present; returns ``adapter_trained=False`` with a
        message otherwise. No hardcoded placeholders (no-mock rule).
        """
        return _read_adapter_manifest()

    return router
