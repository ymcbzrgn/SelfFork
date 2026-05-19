"""FastAPI router for the Reflex pillar — fine-tune trigger + status.

ADR-006 §7.1 — the cockpit Settings page lets the operator kick off
training from the UI (dataset path + hyperparams + training endpoint).
The Reflex package itself is M7 scope; this router lands the
**operator-facing surface** so the UI has somewhere to talk to.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

TrainStatus = Literal["queued", "running", "completed", "errored"]


class HyperParams(BaseModel):
    method: Literal["QLoRA", "LoRA", "Full"] = "QLoRA"
    lora_rank: int = 32
    lora_alpha: int = 16
    learning_rate: str = "2e-4"
    epochs: int = 3
    target_modules: Literal["attention only", "attention + MLP"] = "attention only"


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
    log_tail: list[str] = []
    error: str | None = None


# Process-local job registry (no DB persistence yet — M7 wires this in).
_JOBS: dict[str, TrainingJobResponse] = {}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def build_reflex_router() -> APIRouter:
    router = APIRouter(prefix="/api/reflex", tags=["reflex"])

    @router.post("/train", response_model=TrainingJobResponse, status_code=202)
    async def start_training(req: StartTrainingRequest) -> TrainingJobResponse:
        """Queue a fine-tune job.

        MV does NOT actually train — it registers a job row in
        ``_JOBS`` with ``status='queued'`` so the UI can poll. M7
        replaces this with a real Reflex training worker (QLoRA on
        remote GPU per ADR-006 §9.6).
        """
        if req.dataset_source == "manual" and not req.dataset_path:
            raise HTTPException(
                status_code=400,
                detail="dataset_path is required when dataset_source='manual'",
            )
        job_id = uuid.uuid4().hex[:12]
        job = TrainingJobResponse(
            job_id=job_id,
            status="queued",
            started_at=_utc_now(),
            estimated_seconds=5 * 3600 + 18 * 60,  # 5h 18m heuristic
            progress_percent=0,
            log_tail=[
                f"queued: method={req.hyperparams.method} rank={req.hyperparams.lora_rank} "
                f"epochs={req.hyperparams.epochs}",
                "M7 worker not yet implemented — job stays queued.",
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
            raise HTTPException(status_code=404, detail=f"unknown job {job_id}")
        return job

    @router.get(
        "/training-status", response_model=list[TrainingJobResponse]
    )
    async def list_jobs() -> list[TrainingJobResponse]:
        return sorted(
            _JOBS.values(), key=lambda j: j.started_at, reverse=True
        )

    @router.get("/adapter")
    async def adapter_info() -> dict[str, str | int | None]:
        """Currently-loaded adapter metadata.

        MV: returns placeholder. M7 reads from
        ``~/.selffork/reflex/adapters/<current>/manifest.json``.
        """
        return {
            "version": "v1.2",
            "trained_at": None,
            "age_days": 47,
            "examples": 8432,
            "method": "QLoRA",
        }

    return router
