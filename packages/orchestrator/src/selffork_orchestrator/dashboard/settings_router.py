"""Settings router — operator-driven runtime configuration.

Mounts under ``/api/settings`` and bundles three classes of operator
knob:

* **Vision adapter** (M5+) — ``/vision`` GET/POST + ``/vision/detect``.
  Persisted to ``selffork.yaml`` ``vision:`` section. Pre-S4 surface;
  Cockpit Settings → Vision (separate page) talks here.
* **Self Jr model endpoint** (S4) — ``/model-endpoint`` GET/PUT + the
  ``/model-endpoint/test`` health ping. Persisted to
  ``~/.selffork/settings/model-endpoint.yaml``.
* **Destructive whitelist** (S4) — ``/destructive-whitelist`` GET/PUT
  + ``/{id}/window`` PATCH-style. Persisted to
  ``~/.selffork/settings/destructive-whitelist.yaml`` (operator
  override; falls back to bundled ADR-006 §4.5 default).
* **CodexBar user knobs** (S4) — ``/codexbar`` GET/PUT (version pin,
  auto-update toggle, binary path override). Persisted to
  ``~/.selffork/settings/codexbar.yaml``.

Vision precedence (lowest → highest):

1. :class:`VisionConfig` defaults (Gemma 4 E2B Q4 — MLX + Ollama Q4_K_M).
2. ``selffork.yaml`` ``vision:`` section.
3. Env vars ``SELFFORK_VISION__MLX_MODEL_ID`` etc.
4. ``POST /api/settings/vision`` (this module — writes back to YAML).

Per-topic S4 stores follow the AutonomyStore pattern: separate
``~/.selffork/settings/<topic>.yaml`` files with atomic temp+rename
writes. Effects take place on next dashboard boot — hot-reload is
deferred (S4 keeps surgical scope).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Literal

import httpx
import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from selffork_body.sandbox.destructive_whitelist import DestructiveWhitelist
from selffork_body.vision.runtime import MlxVlmAdapter, OllamaVisionAdapter
from selffork_orchestrator.dashboard.settings import (
    DEFAULT_DESTRUCTIVE_OVERRIDE_PATH as _DEFAULT_DW_OVERRIDE,
)
from selffork_orchestrator.dashboard.settings import (
    CodexBarUserConfig,
    ModelEndpointConfig,
    ModelEndpointHealth,
    YamlSettingsStore,
    default_codexbar_user_store,
    default_model_endpoint_store,
    destructive_whitelist_source,
    resolve_destructive_whitelist_path,
)
from selffork_shared.config import VisionConfig, load_settings

# ── Vision (M5+) — pre-S4 surface, untouched ───────────────────────────────


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


# ── Destructive whitelist (S4) ─────────────────────────────────────────────


class DestructiveCategoryView(BaseModel):
    """One destructive category in the effective whitelist response."""

    model_config = ConfigDict(extra="forbid")

    id: str
    description: str
    confirm_window_hours: int
    rule_count: int


class DestructiveWhitelistResponse(BaseModel):
    """The effective whitelist + raw YAML for the editor round-trip."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["override", "default", "env"]
    """Whether the operator override is in effect, the bundled
    default, or an env-pinned custom path."""

    path: str
    """Absolute path the warden is currently loading from."""

    categories: list[DestructiveCategoryView]
    """Decoded category summaries (id / description / window /
    rule count) — UI uses for the per-category override row list."""

    raw_yaml: str
    """Verbatim YAML text from the file. The Settings full-editor
    uses this for round-trip; the operator pastes it back via PUT."""


class DestructiveWhitelistUpdate(BaseModel):
    """Full-body operator edit of the destructive whitelist YAML."""

    model_config = ConfigDict(extra="forbid")

    yaml_body: str
    """Raw YAML text the operator wants to persist. Validated by
    :meth:`DestructiveWhitelist.from_raw` before write."""


class DestructiveWindowUpdate(BaseModel):
    """Per-category ``confirm_window_hours`` override."""

    model_config = ConfigDict(extra="forbid")

    confirm_window_hours: int = Field(ge=1, le=72)


def build_settings_router(
    *,
    config_path: Path | None = None,
    model_endpoint_store: YamlSettingsStore[ModelEndpointConfig] | None = None,
    codexbar_user_store: YamlSettingsStore[CodexBarUserConfig] | None = None,
    destructive_override_path: Path | None = None,
) -> APIRouter:
    """Build the ``/api/settings`` router.

    Args:
        config_path: ``selffork.yaml`` path for the legacy ``vision:``
            section. ``None`` makes ``POST /vision`` return 503
            (read-only deployment — e.g. CI fixture).
        model_endpoint_store: Override the default model endpoint
            store (test injection point).
        codexbar_user_store: Override the default CodexBar user
            settings store.
        destructive_override_path: Override the operator-edit path for
            the destructive whitelist. Defaults to
            ``~/.selffork/settings/destructive-whitelist.yaml``.
    """

    router = APIRouter(prefix="/api/settings", tags=["settings"])
    me_store = model_endpoint_store or default_model_endpoint_store()
    cx_store = codexbar_user_store or default_codexbar_user_store()
    dw_override = destructive_override_path or _DEFAULT_DW_OVERRIDE

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
        update = {
            k: v for k, v in payload.model_dump(exclude_none=True).items()
        }
        merged = current.model_copy(update=update)
        _persist_vision(config_path, merged)
        return merged

    @router.post("/vision/detect", response_model=VisionDetectResponse)
    async def detect_vision() -> VisionDetectResponse:
        cfg = _load_vision()
        mlx = MlxVlmAdapter.from_config(cfg)
        ollama = OllamaVisionAdapter.from_config(cfg)
        mlx_ok, mlx_models, mlx_err = await _probe(mlx.list_models)
        ollama_ok, ollama_models, ollama_err = await _probe(
            ollama.list_models
        )
        return VisionDetectResponse(
            mlx_available=mlx_ok,
            mlx_models=mlx_models,
            mlx_error=mlx_err,
            ollama_available=ollama_ok,
            ollama_models=ollama_models,
            ollama_error=ollama_err,
        )

    # ── Model endpoint (S4) ───────────────────────────────────────────────

    @router.get("/model-endpoint", response_model=ModelEndpointConfig)
    def get_model_endpoint() -> ModelEndpointConfig:
        return me_store.read_or_default()

    @router.put("/model-endpoint", response_model=ModelEndpointConfig)
    def put_model_endpoint(payload: ModelEndpointConfig) -> ModelEndpointConfig:
        me_store.write(payload)
        return payload

    @router.post(
        "/model-endpoint/test", response_model=ModelEndpointHealth
    )
    async def test_model_endpoint(
        payload: ModelEndpointConfig | None = None,
    ) -> ModelEndpointHealth:
        """Probe the endpoint for liveness.

        When ``payload`` is omitted, the persisted config is probed
        (UI "Test connection" pre-save). When supplied, the supplied
        shape is probed (UI lets the operator validate an unsaved
        edit before clicking "Save & restart").
        """
        cfg = payload if payload is not None else me_store.read_or_default()
        return await _probe_model_endpoint(cfg)

    # ── Destructive whitelist (S4) ────────────────────────────────────────

    @router.get(
        "/destructive-whitelist",
        response_model=DestructiveWhitelistResponse,
    )
    def get_destructive_whitelist() -> DestructiveWhitelistResponse:
        return _build_destructive_whitelist_response(dw_override)

    @router.put(
        "/destructive-whitelist",
        response_model=DestructiveWhitelistResponse,
    )
    def put_destructive_whitelist(
        payload: DestructiveWhitelistUpdate,
    ) -> DestructiveWhitelistResponse:
        _refuse_when_env_pinned()
        try:
            data = yaml.safe_load(payload.yaml_body) or {}
        except yaml.YAMLError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"invalid YAML: {exc}",
            ) from exc
        if not isinstance(data, dict):
            raise HTTPException(
                status_code=400,
                detail="YAML root must be a mapping",
            )
        try:
            DestructiveWhitelist.from_raw(data)
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=400,
                detail=f"invalid whitelist schema: {exc}",
            ) from exc
        dw_override.parent.mkdir(parents=True, exist_ok=True)
        temp = dw_override.with_suffix(dw_override.suffix + ".tmp")
        temp.write_text(payload.yaml_body, encoding="utf-8")
        temp.replace(dw_override)
        return _build_destructive_whitelist_response(dw_override)

    @router.put(
        "/destructive-whitelist/{category_id}/window",
        response_model=DestructiveWhitelistResponse,
    )
    def put_destructive_window(
        category_id: str, payload: DestructiveWindowUpdate
    ) -> DestructiveWhitelistResponse:
        _refuse_when_env_pinned()
        source_path = resolve_destructive_whitelist_path(dw_override)
        if not source_path.is_file():
            raise HTTPException(
                status_code=500,
                detail=(
                    "no destructive whitelist file present "
                    f"(expected at {source_path}); reinstall package"
                ),
            )
        with source_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            raise HTTPException(
                status_code=500,
                detail=f"corrupt whitelist file at {source_path}",
            )
        raw_cats = data.get("destructive_actions") or []
        found = False
        for cat in raw_cats:
            if isinstance(cat, dict) and str(cat.get("id")) == category_id:
                cat["confirm_window_hours"] = payload.confirm_window_hours
                found = True
                break
        if not found:
            raise HTTPException(
                status_code=404,
                detail=f"category {category_id!r} not in whitelist",
            )
        # Validate the mutated structure roundtrips before persisting.
        try:
            DestructiveWhitelist.from_raw(data)
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=400,
                detail=f"mutation produced invalid schema: {exc}",
            ) from exc
        dw_override.parent.mkdir(parents=True, exist_ok=True)
        temp = dw_override.with_suffix(dw_override.suffix + ".tmp")
        with temp.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)
        temp.replace(dw_override)
        return _build_destructive_whitelist_response(dw_override)

    # ── CodexBar user knobs (S4) ──────────────────────────────────────────

    @router.get("/codexbar", response_model=CodexBarUserConfig)
    def get_codexbar_settings() -> CodexBarUserConfig:
        return cx_store.read_or_default()

    @router.put("/codexbar", response_model=CodexBarUserConfig)
    def put_codexbar_settings(
        payload: CodexBarUserConfig,
    ) -> CodexBarUserConfig:
        cx_store.write(payload)
        return payload

    return router


# ── Helpers ────────────────────────────────────────────────────────────────


def _refuse_when_env_pinned() -> None:
    """Reject destructive-whitelist writes when env-pin is active.

    Audit-god MINOR #2: when ``SELFFORK_DESTRUCTIVE_WHITELIST_PATH``
    is set, the resolver returns the env path (env > override >
    bundled default), so writes to the override file are silently
    shadowed — the operator's edits land on disk but the warden + GET
    response keep reading from the env path. Refuse with 409 so the
    operator notices.
    """
    env = os.environ.get("SELFFORK_DESTRUCTIVE_WHITELIST_PATH")
    if env:
        raise HTTPException(
            status_code=409,
            detail=(
                "SELFFORK_DESTRUCTIVE_WHITELIST_PATH is set "
                f"({env!r}); the env-pinned whitelist takes precedence "
                "over the override file. Unset the env var to edit "
                "the override via this endpoint."
            ),
        )


def _build_destructive_whitelist_response(
    override_path: Path,
) -> DestructiveWhitelistResponse:
    """Compose the GET response from the currently-effective file."""
    path = resolve_destructive_whitelist_path(override_path)
    source = destructive_whitelist_source(override_path)
    raw_yaml = (
        path.read_text(encoding="utf-8") if path.is_file() else ""
    )
    wl = DestructiveWhitelist.load(path)
    categories = [
        DestructiveCategoryView(
            id=cat.id,
            description=cat.description,
            confirm_window_hours=cat.confirm_window_hours,
            rule_count=len(cat.match_any),
        )
        for cat in wl.categories
    ]
    return DestructiveWhitelistResponse(
        source=source,  # type: ignore[arg-type]
        path=str(path),
        categories=categories,
        raw_yaml=raw_yaml,
    )


async def _probe_model_endpoint(
    cfg: ModelEndpointConfig,
) -> ModelEndpointHealth:
    """Probe the endpoint with the protocol-appropriate ping URL."""
    url_base = cfg.url.rstrip("/")
    probe_url = (
        f"{url_base}/api/tags"
        if cfg.protocol == "ollama"
        else f"{url_base}/v1/models"
    )
    headers: dict[str, str] = {}
    if cfg.auth_kind != "none" and cfg.auth_secret:
        headers["Authorization"] = f"Bearer {cfg.auth_secret}"

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(probe_url, headers=headers)
        latency_ms = int((time.monotonic() - start) * 1000)
        ok = 200 <= resp.status_code < 300
        server = resp.headers.get("server", "")
        detail = (
            f"server={server}"
            if server
            else f"status={resp.status_code}"
        )
        return ModelEndpointHealth(
            ok=ok,
            status_code=resp.status_code,
            latency_ms=latency_ms,
            detail=detail,
        )
    except httpx.HTTPError as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        return ModelEndpointHealth(
            ok=False,
            status_code=None,
            latency_ms=latency_ms,
            detail=f"{type(exc).__name__}: {exc}",
        )


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
