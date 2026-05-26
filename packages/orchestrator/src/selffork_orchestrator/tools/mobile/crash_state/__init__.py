"""Crash + state-capture tools — log/bug_report/snapshot/restore/diff (10 tools).

S-ToolFleet Faz 1. Operator-level + autonomous-regression use; all
deferred. Snapshot/restore writes plaintext JSON under
``~/.selffork/state/<workspace>/<label>.json`` so the operator can
inspect + the autonomous loop can diff before+after.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.mobile._internal import (
    _invoke_mobile,
    _require_mobile_driver,
)

__all__ = [
    "CrashAnrDumpArgs",
    "CrashBugReportArgs",
    "CrashHeapDumpArgs",
    "CrashLogFetchArgs",
    "CrashStateDeleteArgs",
    "CrashStateDiffArgs",
    "CrashStateListArgs",
    "CrashStateRestoreArgs",
    "CrashStateSnapshotArgs",
    "CrashThreadDumpArgs",
    "build_crash_state_tools",
]


_LABEL_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _state_root() -> Path:
    root = os.environ.get("SELFFORK_STATE_DIR")
    if root:
        return Path(root).expanduser()
    return Path("~/.selffork/state").expanduser()


def _state_dir_for(workspace_slug: str | None) -> Path:
    base = _state_root()
    if workspace_slug:
        return base / workspace_slug
    return base / "orphan"


def _validate_label(label: str) -> None:
    if not _LABEL_RE.fullmatch(label):
        raise ValueError(
            f"label {label!r} must match {_LABEL_RE.pattern} (no path separators)",
        )


# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------


class CrashLogFetchArgs(ToolArgs):
    max_lines: int = Field(default=200, ge=1, le=10_000)


class CrashBugReportArgs(ToolArgs):
    output_path: str = Field(min_length=1, description="Local zip path")


class CrashStateSnapshotArgs(ToolArgs):
    label: str = Field(min_length=1, max_length=64)
    include_a11y: bool = True
    include_logs: bool = False
    workspace_slug: str | None = None


class CrashStateRestoreArgs(ToolArgs):
    label: str = Field(min_length=1, max_length=64)
    workspace_slug: str | None = None


class CrashStateListArgs(ToolArgs):
    workspace_slug: str | None = None


class CrashStateDeleteArgs(ToolArgs):
    label: str = Field(min_length=1, max_length=64)
    workspace_slug: str | None = None


class CrashStateDiffArgs(ToolArgs):
    label_a: str = Field(min_length=1, max_length=64)
    label_b: str = Field(min_length=1, max_length=64)
    workspace_slug: str | None = None


class CrashAnrDumpArgs(ToolArgs):
    pass


class CrashHeapDumpArgs(ToolArgs):
    pid: int = Field(ge=1)
    output_path: str = Field(min_length=1)


class CrashThreadDumpArgs(ToolArgs):
    pass


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def _crash_log_fetch(
    ctx: ToolContext, args: CrashLogFetchArgs,
) -> dict[str, Any]:
    drv = _require_mobile_driver(ctx)

    async def _grab() -> dict[str, Any]:
        platform = getattr(drv, "platform", "unknown")
        if platform == "android":
            text = await drv.logcat(max_lines=args.max_lines)
            source = "logcat"
        elif platform == "ios":
            text = await drv.get_logs(last=f"{args.max_lines}")
            source = "ios_unified_log"
        elif platform == "composite":
            # Prefer Android logcat — usually faster
            if drv.android is not None:
                text = await drv.android.logcat(max_lines=args.max_lines)
                source = "logcat"
            elif drv.ios is not None:
                text = await drv.ios.get_logs(last=f"{args.max_lines}")
                source = "ios_unified_log"
            else:
                return {"status": "unsupported", "platform": platform}
        elif hasattr(drv, "logcat"):
            text = await drv.logcat(max_lines=args.max_lines)
            source = "logcat"
        elif hasattr(drv, "get_logs"):
            text = await drv.get_logs(last=f"{args.max_lines}")
            source = "ios_unified_log"
        else:
            return {"status": "unsupported", "platform": platform}
        return {"source": source, "text_len": len(text), "preview": text[:8192]}

    return await _invoke_mobile(
        ctx,
        action_type="crash.log_fetch",
        target_uri=None,
        args_summary={"max_lines": args.max_lines},
        coro_factory=_grab,
    )


async def _crash_bug_report(
    ctx: ToolContext, args: CrashBugReportArgs,
) -> dict[str, Any]:
    drv = _require_mobile_driver(ctx)

    async def _capture() -> dict[str, Any]:
        platform = getattr(drv, "platform", "unknown")
        if platform == "android" and hasattr(drv, "shell"):
            await drv.shell(f"bugreportz -o /sdcard/{Path(args.output_path).name}")
            await drv.pull(f"/sdcard/{Path(args.output_path).name}", Path(args.output_path))
            return {"status": "ok", "output_path": args.output_path}
        if platform == "ios":
            # No direct iOS bug report capture from simulator; snapshot logs
            text = await drv.get_logs(last="10m")
            Path(args.output_path).write_text(text, encoding="utf-8")  # noqa: ASYNC240 — small text dump
            return {"status": "ok_partial", "output_path": args.output_path}
        return {"status": "unsupported", "platform": platform}

    return await _invoke_mobile(
        ctx,
        action_type="crash.bug_report",
        target_uri=f"file:{args.output_path}",
        args_summary={"output_path": args.output_path},
        coro_factory=_capture,
    )


async def _crash_state_snapshot(
    ctx: ToolContext, args: CrashStateSnapshotArgs,
) -> dict[str, Any]:
    _validate_label(args.label)
    drv = _require_mobile_driver(ctx)
    workspace = args.workspace_slug or ctx.project_slug
    target_dir = _state_dir_for(workspace)

    async def _snap() -> dict[str, Any]:
        target_dir.mkdir(parents=True, exist_ok=True)
        platform = getattr(drv, "platform", "unknown")
        record: dict[str, Any] = {
            "label": args.label,
            "platform": platform,
            "session_id": ctx.session_id,
            "workspace_slug": workspace,
            "captured_at": datetime.now(UTC).isoformat(),
        }
        if args.include_a11y and hasattr(drv, "ax_tree"):
            try:
                tree = await drv.ax_tree()
                record["ax_tree"] = str(tree)[:65_536]
            except Exception as exc:
                record["ax_tree_error"] = str(exc)
        if args.include_logs:
            try:
                if hasattr(drv, "logcat"):
                    record["logs"] = (await drv.logcat(max_lines=200))[:65_536]
                elif hasattr(drv, "get_logs"):
                    record["logs"] = (await drv.get_logs(last="2m"))[:65_536]
            except Exception as exc:
                record["logs_error"] = str(exc)
        path = target_dir / f"{args.label}.json"
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return {"label": args.label, "path": str(path), "bytes": path.stat().st_size}

    return await _invoke_mobile(
        ctx,
        action_type="crash.state_snapshot",
        target_uri=f"state:{workspace or 'orphan'}/{args.label}",
        args_summary={
            "label": args.label,
            "include_a11y": args.include_a11y,
            "include_logs": args.include_logs,
            "workspace_slug": workspace,
        },
        coro_factory=_snap,
    )


async def _crash_state_restore(
    ctx: ToolContext, args: CrashStateRestoreArgs,
) -> dict[str, Any]:
    _validate_label(args.label)
    workspace = args.workspace_slug or ctx.project_slug
    path = _state_dir_for(workspace) / f"{args.label}.json"

    async def _load() -> dict[str, Any]:
        if not path.is_file():
            return {"status": "not_found", "path": str(path)}
        content = json.loads(path.read_text(encoding="utf-8"))
        return {"status": "ok", "path": str(path), "snapshot": content}

    return await _invoke_mobile(
        ctx,
        action_type="crash.state_restore",
        target_uri=f"state:{workspace or 'orphan'}/{args.label}",
        args_summary={"label": args.label, "workspace_slug": workspace},
        coro_factory=_load,
    )


async def _crash_state_list(
    ctx: ToolContext, args: CrashStateListArgs,
) -> dict[str, Any]:
    workspace = args.workspace_slug or ctx.project_slug
    target_dir = _state_dir_for(workspace)

    async def _list() -> dict[str, Any]:
        if not target_dir.is_dir():
            return {"labels": [], "dir": str(target_dir)}
        labels = sorted(
            p.stem for p in target_dir.glob("*.json")
        )
        return {"labels": labels[:500], "count": len(labels), "dir": str(target_dir)}

    return await _invoke_mobile(
        ctx,
        action_type="crash.state_list",
        target_uri=f"state:{workspace or 'orphan'}",
        args_summary={"workspace_slug": workspace},
        coro_factory=_list,
    )


async def _crash_state_delete(
    ctx: ToolContext, args: CrashStateDeleteArgs,
) -> dict[str, Any]:
    _validate_label(args.label)
    workspace = args.workspace_slug or ctx.project_slug
    path = _state_dir_for(workspace) / f"{args.label}.json"

    async def _delete() -> dict[str, Any]:
        if not path.is_file():
            return {"status": "not_found", "path": str(path)}
        path.unlink()
        return {"status": "deleted", "path": str(path)}

    return await _invoke_mobile(
        ctx,
        action_type="crash.state_delete",
        target_uri=f"state:{workspace or 'orphan'}/{args.label}",
        args_summary={"label": args.label, "workspace_slug": workspace},
        coro_factory=_delete,
    )


async def _crash_state_diff(
    ctx: ToolContext, args: CrashStateDiffArgs,
) -> dict[str, Any]:
    _validate_label(args.label_a)
    _validate_label(args.label_b)
    workspace = args.workspace_slug or ctx.project_slug
    base = _state_dir_for(workspace)
    path_a = base / f"{args.label_a}.json"
    path_b = base / f"{args.label_b}.json"

    async def _diff() -> dict[str, Any]:
        if not (path_a.is_file() and path_b.is_file()):
            return {
                "status": "not_found",
                "exists": {
                    args.label_a: path_a.is_file(),
                    args.label_b: path_b.is_file(),
                },
            }
        a = json.loads(path_a.read_text(encoding="utf-8"))
        b = json.loads(path_b.read_text(encoding="utf-8"))
        a_tree = a.get("ax_tree", "")
        b_tree = b.get("ax_tree", "")
        a_lines = set(a_tree.splitlines())
        b_lines = set(b_tree.splitlines())
        only_a = sorted(a_lines - b_lines)[:200]
        only_b = sorted(b_lines - a_lines)[:200]
        return {
            "status": "ok",
            "label_a": args.label_a,
            "label_b": args.label_b,
            "only_in_a_count": len(a_lines - b_lines),
            "only_in_b_count": len(b_lines - a_lines),
            "only_in_a_preview": only_a,
            "only_in_b_preview": only_b,
        }

    return await _invoke_mobile(
        ctx,
        action_type="crash.state_diff",
        target_uri=f"state:{workspace or 'orphan'}",
        args_summary={
            "label_a": args.label_a,
            "label_b": args.label_b,
            "workspace_slug": workspace,
        },
        coro_factory=_diff,
    )


async def _crash_anr_dump(ctx: ToolContext, args: CrashAnrDumpArgs) -> dict[str, Any]:
    drv = _require_mobile_driver(ctx)

    async def _dump() -> dict[str, Any]:
        platform = getattr(drv, "platform", "unknown")
        if platform == "android" and hasattr(drv, "shell"):
            text = await drv.shell("ls -lh /data/anr/")
            return {"status": "ok", "preview": text[:4096]}
        if platform == "composite" and drv.android is not None:
            text = await drv.android.shell("ls -lh /data/anr/")
            return {"status": "ok", "preview": text[:4096]}
        return {"status": "unsupported", "platform": platform}

    return await _invoke_mobile(
        ctx,
        action_type="crash.anr_dump",
        target_uri=None,
        args_summary={},
        coro_factory=_dump,
    )


async def _crash_heap_dump(
    ctx: ToolContext, args: CrashHeapDumpArgs,
) -> dict[str, Any]:
    drv = _require_mobile_driver(ctx)

    async def _dump() -> dict[str, Any]:
        platform = getattr(drv, "platform", "unknown")
        if platform == "android" and hasattr(drv, "shell"):
            await drv.shell(
                f"am dumpheap {args.pid} /sdcard/{Path(args.output_path).name}",
            )
            await drv.pull(
                f"/sdcard/{Path(args.output_path).name}", Path(args.output_path),
            )
            return {"status": "ok", "output_path": args.output_path}
        if platform == "composite" and drv.android is not None:
            await drv.android.shell(
                f"am dumpheap {args.pid} /sdcard/{Path(args.output_path).name}",
            )
            await drv.android.pull(
                f"/sdcard/{Path(args.output_path).name}", Path(args.output_path),
            )
            return {"status": "ok", "output_path": args.output_path}
        return {"status": "unsupported", "platform": platform}

    return await _invoke_mobile(
        ctx,
        action_type="crash.heap_dump",
        target_uri=f"pid:{args.pid}",
        args_summary={"pid": args.pid, "output_path": args.output_path},
        coro_factory=_dump,
    )


async def _crash_thread_dump(
    ctx: ToolContext, args: CrashThreadDumpArgs,
) -> dict[str, Any]:
    drv = _require_mobile_driver(ctx)

    async def _dump() -> dict[str, Any]:
        platform = getattr(drv, "platform", "unknown")
        if platform == "android" and hasattr(drv, "shell"):
            text = await drv.shell("ps -T -A | head -50")
            return {"status": "ok", "preview": text[:8192]}
        if platform == "composite" and drv.android is not None:
            text = await drv.android.shell("ps -T -A | head -50")
            return {"status": "ok", "preview": text[:8192]}
        return {"status": "unsupported", "platform": platform}

    return await _invoke_mobile(
        ctx,
        action_type="crash.thread_dump",
        target_uri=None,
        args_summary={},
        coro_factory=_dump,
    )


def build_crash_state_tools() -> list[ToolSpec[Any]]:
    return [
        ToolSpec(
            name="crash_log_fetch",
            description="Fetch recent device logs (logcat / iOS unified log).",
            args_model=CrashLogFetchArgs,
            handler=_crash_log_fetch,
            defer_loading=True,
        ),
        ToolSpec(
            name="crash_bug_report",
            description="Capture full bug report (Android bugreportz / iOS log dump).",
            args_model=CrashBugReportArgs,
            handler=_crash_bug_report,
            defer_loading=True,
        ),
        ToolSpec(
            name="crash_state_snapshot",
            description=(
                "Persist a labelled state snapshot (a11y + optional logs) "
                "under ~/.selffork/state/."
            ),
            args_model=CrashStateSnapshotArgs,
            handler=_crash_state_snapshot,
            defer_loading=True,
        ),
        ToolSpec(
            name="crash_state_restore",
            description="Load a previously saved state snapshot by label.",
            args_model=CrashStateRestoreArgs,
            handler=_crash_state_restore,
            defer_loading=True,
        ),
        ToolSpec(
            name="crash_state_list",
            description="List saved state snapshot labels for a workspace.",
            args_model=CrashStateListArgs,
            handler=_crash_state_list,
            defer_loading=True,
        ),
        ToolSpec(
            name="crash_state_delete",
            description="Delete a saved state snapshot by label.",
            args_model=CrashStateDeleteArgs,
            handler=_crash_state_delete,
            defer_loading=True,
        ),
        ToolSpec(
            name="crash_state_diff",
            description=(
                "Diff two snapshots' a11y trees; returns only-in-A / only-in-B "
                "line sets."
            ),
            args_model=CrashStateDiffArgs,
            handler=_crash_state_diff,
            defer_loading=True,
        ),
        ToolSpec(
            name="crash_anr_dump",
            description="List Android ANR (Application Not Responding) trace files.",
            args_model=CrashAnrDumpArgs,
            handler=_crash_anr_dump,
            defer_loading=True,
        ),
        ToolSpec(
            name="crash_heap_dump",
            description="Dump Android process heap (am dumpheap) and pull to host.",
            args_model=CrashHeapDumpArgs,
            handler=_crash_heap_dump,
            defer_loading=True,
        ),
        ToolSpec(
            name="crash_thread_dump",
            description="List active threads for the active platform (Android: ps -T -A).",
            args_model=CrashThreadDumpArgs,
            handler=_crash_thread_dump,
            defer_loading=True,
        ),
    ]
