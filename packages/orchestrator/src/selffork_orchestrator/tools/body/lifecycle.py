"""Body lifecycle tools — app_launch / storage_state save+load.

Three tools that manipulate per-provider auth state and app windows.
Higher tier than interaction (storage_state touches secrets) — warden
allowlist policy decides whether the operator's mode is permissive.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from selffork_orchestrator.tools.base import (
    ToolArgs,
    ToolContext,
    ToolSpec,
)
from selffork_orchestrator.tools.body._internal import _invoke, _require_driver

__all__ = [
    "BodyAppLaunchArgs",
    "BodyStorageStateLoadArgs",
    "BodyStorageStateSaveArgs",
    "build_lifecycle_tools",
]


class BodyAppLaunchArgs(ToolArgs):
    bundle_id: str = Field(min_length=1)


class BodyStorageStateSaveArgs(ToolArgs):
    provider: str = Field(min_length=1, max_length=64)
    project_slug: str | None = None


class BodyStorageStateLoadArgs(ToolArgs):
    provider: str = Field(min_length=1, max_length=64)
    project_slug: str | None = None


async def _body_app_launch(
    ctx: ToolContext, args: BodyAppLaunchArgs,
) -> dict[str, Any]:
    driver = _require_driver(ctx)
    return await _invoke(
        ctx,
        action_type="app_launch",
        target_uri=args.bundle_id,
        args_summary={"bundle_id": args.bundle_id},
        coro_factory=lambda: driver.app_launch(args.bundle_id),
    )


async def _body_storage_state_save(
    ctx: ToolContext, args: BodyStorageStateSaveArgs,
) -> dict[str, Any]:
    driver = _require_driver(ctx)
    project = args.project_slug or ctx.project_slug

    async def _do() -> dict[str, Any]:
        result = await driver.storage_state_save(
            provider=args.provider, project_slug=project,
        )
        return {"path": str(result)} if result is not None else {}

    return await _invoke(
        ctx,
        action_type="storage_state_save",
        target_uri=args.provider,
        args_summary={"provider": args.provider, "project_slug": project},
        coro_factory=_do,
    )


async def _body_storage_state_load(
    ctx: ToolContext, args: BodyStorageStateLoadArgs,
) -> dict[str, Any]:
    driver = _require_driver(ctx)
    project = args.project_slug or ctx.project_slug

    async def _do() -> dict[str, Any]:
        result = await driver.storage_state_load(
            provider=args.provider, project_slug=project,
        )
        return {"loaded": bool(result)}

    return await _invoke(
        ctx,
        action_type="storage_state_load",
        target_uri=args.provider,
        args_summary={"provider": args.provider, "project_slug": project},
        coro_factory=_do,
    )


def build_lifecycle_tools() -> list[ToolSpec[Any]]:
    """Three lifecycle tools — app_launch / storage_state save+load."""
    return [
        ToolSpec(
            name="body_app_launch",
            description=(
                "Launch a native app by bundle/package id (T2)."
            ),
            args_model=BodyAppLaunchArgs,
            handler=_body_app_launch,
        ),
        ToolSpec(
            name="body_storage_state_save",
            description=(
                "Persist provider auth storage_state for later sessions (T1)."
            ),
            args_model=BodyStorageStateSaveArgs,
            handler=_body_storage_state_save,
        ),
        ToolSpec(
            name="body_storage_state_load",
            description=(
                "Load a previously saved provider storage_state (T1)."
            ),
            args_model=BodyStorageStateLoadArgs,
            handler=_body_storage_state_load,
        ),
    ]
