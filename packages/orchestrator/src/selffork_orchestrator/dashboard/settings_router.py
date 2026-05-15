"""Settings router — operator-driven runtime configuration (M5+).

Currently exposes :class:`selffork_shared.config.VisionConfig` so the
operator can swap MLX/Ollama model IDs without editing YAML by hand or
touching code. Future sub-routers (Mind, Audit) plug into the same
``/api/settings`` prefix.

Precedence (lowest → highest):

1. ``VisionConfig`` defaults (Gemma 4 E2B Q4 — MLX + Ollama Q4_K_M).
2. ``selffork.yaml`` ``vision:`` section.
3. Env vars ``SELFFORK_VISION__MLX_MODEL_ID`` etc.
4. ``POST /api/settings/vision`` (this module — writes back to YAML).
"""

from pathlib import Path

import httpx
import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from selffork_body.vision.runtime import MlxVlmAdapter, OllamaVisionAdapter
from selffork_shared.config import VisionConfig, load_settings


class VisionConfigUpdate(BaseModel):
    """Partial update payload for ``POST /api/settings/vision``.

    Any field set to a non-null value overrides the current config; the
    rest stays untouched. This lets the Cockpit UI submit only the
    dropdowns the operator actually changed.
    """

    mlx_model_id: str | None = None
    mlx_server_url: str | None = None
    ollama_model_tag: str | None = None
    ollama_host: str | None = None
    auto_detect: bool | None = None


class VisionDetectResponse(BaseModel):
    """Response of ``POST /api/settings/vision/detect``.

    Each adapter is probed independently; one being down does not block
    the other. The Cockpit UI uses ``*_available`` to gate the dropdown
    options and surfaces ``*_error`` as a small inline hint.
    """

    mlx_available: bool
    mlx_models: list[str]
    mlx_error: str | None = None
    ollama_available: bool
    ollama_models: list[str]
    ollama_error: str | None = None


def build_settings_router(*, config_path: Path | None = None) -> APIRouter:
    """Build the ``/api/settings`` router.

    ``config_path`` is the YAML file written when the operator clicks
    "Apply" in Cockpit Settings → Vision. When ``None``, ``POST /vision``
    returns 503 (read-only deployment — e.g. CI fixture).
    """

    router = APIRouter(prefix="/api/settings", tags=["settings"])

    def _load_vision() -> VisionConfig:
        # ``load_settings`` raises if a non-existent path is passed. When
        # the YAML file has not been written yet (first-run, fresh tmp),
        # fall back to defaults + env vars.
        path = config_path if (config_path and config_path.is_file()) else None
        return load_settings(path).vision

    @router.get("/vision", response_model=VisionConfig)
    async def get_vision() -> VisionConfig:
        return _load_vision()

    @router.post("/vision", response_model=VisionConfig)
    async def update_vision(payload: VisionConfigUpdate) -> VisionConfig:
        if config_path is None:
            raise HTTPException(
                status_code=503,
                detail="config_path not set; persistent updates disabled",
            )
        current = _load_vision()
        update = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
        merged = current.model_copy(update=update)
        _persist_vision(config_path, merged)
        return merged

    @router.post("/vision/detect", response_model=VisionDetectResponse)
    async def detect_vision() -> VisionDetectResponse:
        cfg = _load_vision()
        mlx = MlxVlmAdapter.from_config(cfg)
        ollama = OllamaVisionAdapter.from_config(cfg)
        mlx_ok, mlx_models, mlx_err = await _probe(mlx.list_models)
        ollama_ok, ollama_models, ollama_err = await _probe(ollama.list_models)
        return VisionDetectResponse(
            mlx_available=mlx_ok,
            mlx_models=mlx_models,
            mlx_error=mlx_err,
            ollama_available=ollama_ok,
            ollama_models=ollama_models,
            ollama_error=ollama_err,
        )

    return router


async def _probe(coro_fn) -> tuple[bool, list[str], str | None]:  # type: ignore[no-untyped-def]
    """Run an adapter ``list_models`` and return (ok, models, error_str)."""
    try:
        models = await coro_fn()
    except httpx.HTTPError as e:
        return False, [], f"{type(e).__name__}: {e}"
    except Exception as e:
        return False, [], f"{type(e).__name__}: {e}"
    return True, models, None


def _persist_vision(path: Path, vision: VisionConfig) -> None:
    """Write the ``vision:`` section into YAML without clobbering others."""
    data: dict[str, object] = {}
    if path.is_file():
        with path.open("r") as f:
            loaded = yaml.safe_load(f)
            if isinstance(loaded, dict):
                data = loaded
    data["vision"] = vision.model_dump()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
