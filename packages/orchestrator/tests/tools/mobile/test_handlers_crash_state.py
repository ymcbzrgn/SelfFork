"""Crash/state handler tests — snapshot/restore/list/delete/diff + log fetch."""

from __future__ import annotations

import json

import pytest

from selffork_orchestrator.tools.mobile.crash_state import (
    CrashAnrDumpArgs,
    CrashBugReportArgs,
    CrashHeapDumpArgs,
    CrashLogFetchArgs,
    CrashStateDeleteArgs,
    CrashStateDiffArgs,
    CrashStateListArgs,
    CrashStateRestoreArgs,
    CrashStateSnapshotArgs,
    CrashThreadDumpArgs,
    _crash_anr_dump,
    _crash_bug_report,
    _crash_heap_dump,
    _crash_log_fetch,
    _crash_state_delete,
    _crash_state_diff,
    _crash_state_list,
    _crash_state_restore,
    _crash_state_snapshot,
    _crash_thread_dump,
)


@pytest.fixture(autouse=True)
def isolated_state_dir(tmp_path, monkeypatch):
    """Redirect SELFFORK_STATE_DIR into a per-test tmp dir."""
    monkeypatch.setenv("SELFFORK_STATE_DIR", str(tmp_path))
    yield


async def test_log_fetch_android(ctx_android, stub_android_driver) -> None:
    result = await _crash_log_fetch(ctx_android, CrashLogFetchArgs(max_lines=50))
    assert result["result"]["source"] == "logcat"


async def test_log_fetch_ios(ctx_ios, stub_ios_driver) -> None:
    result = await _crash_log_fetch(ctx_ios, CrashLogFetchArgs(max_lines=20))
    assert result["result"]["source"] == "ios_unified_log"


async def test_log_fetch_composite_prefers_android(
    ctx_composite,
    stub_composite_driver,
) -> None:
    result = await _crash_log_fetch(ctx_composite, CrashLogFetchArgs())
    assert result["result"]["source"] == "logcat"


async def test_bug_report_android(
    ctx_android,
    stub_android_driver,
    tmp_path,
) -> None:
    out = tmp_path / "bug.zip"
    result = await _crash_bug_report(
        ctx_android,
        CrashBugReportArgs(output_path=str(out)),
    )
    assert result["status"] == "ok"


async def test_bug_report_ios(ctx_ios, stub_ios_driver, tmp_path) -> None:
    out = tmp_path / "bug.txt"
    result = await _crash_bug_report(
        ctx_ios,
        CrashBugReportArgs(output_path=str(out)),
    )
    assert result["status"] == "ok"
    assert out.is_file()


async def test_state_snapshot_creates_json(
    ctx_ios,
    stub_ios_driver,
    tmp_path,
) -> None:
    result = await _crash_state_snapshot(
        ctx_ios,
        CrashStateSnapshotArgs(label="before", include_logs=True),
    )
    assert result["status"] == "ok"
    path = tmp_path / "orphan" / "before.json"
    assert path.is_file()
    data = json.loads(path.read_text())
    assert data["label"] == "before"
    assert "ax_tree" in data


async def test_state_snapshot_rejects_path_traversal(
    ctx_ios,
    stub_ios_driver,
) -> None:
    with pytest.raises(ValueError, match="must match"):
        CrashStateSnapshotArgs(label="../etc/passwd")
        await _crash_state_snapshot(
            ctx_ios,
            CrashStateSnapshotArgs(label="../etc/passwd"),
        )


async def test_state_snapshot_label_with_slash_rejected(
    ctx_ios,
    stub_ios_driver,
) -> None:
    # Validation happens inside the handler via _validate_label
    with pytest.raises(ValueError, match="must match"):
        await _crash_state_snapshot(
            ctx_ios,
            CrashStateSnapshotArgs(label="bad/label"),
        )


async def test_state_restore_returns_snapshot(
    ctx_ios,
    stub_ios_driver,
    tmp_path,
) -> None:
    await _crash_state_snapshot(
        ctx_ios,
        CrashStateSnapshotArgs(label="snap1"),
    )
    result = await _crash_state_restore(
        ctx_ios,
        CrashStateRestoreArgs(label="snap1"),
    )
    assert result["result"]["status"] == "ok"
    assert result["result"]["snapshot"]["label"] == "snap1"


async def test_state_restore_not_found(
    ctx_ios,
    stub_ios_driver,
) -> None:
    result = await _crash_state_restore(
        ctx_ios,
        CrashStateRestoreArgs(label="nonexistent"),
    )
    assert result["result"]["status"] == "not_found"


async def test_state_list_after_snapshots(
    ctx_ios,
    stub_ios_driver,
) -> None:
    for label in ("snap_a", "snap_b", "snap_c"):
        await _crash_state_snapshot(
            ctx_ios,
            CrashStateSnapshotArgs(label=label),
        )
    result = await _crash_state_list(ctx_ios, CrashStateListArgs())
    assert sorted(result["result"]["labels"]) == ["snap_a", "snap_b", "snap_c"]


async def test_state_delete(ctx_ios, stub_ios_driver) -> None:
    await _crash_state_snapshot(ctx_ios, CrashStateSnapshotArgs(label="kill_me"))
    result = await _crash_state_delete(
        ctx_ios,
        CrashStateDeleteArgs(label="kill_me"),
    )
    assert result["result"]["status"] == "deleted"


async def test_state_delete_missing(ctx_ios, stub_ios_driver) -> None:
    result = await _crash_state_delete(
        ctx_ios,
        CrashStateDeleteArgs(label="nope"),
    )
    assert result["result"]["status"] == "not_found"


async def test_state_diff_two_snapshots(ctx_ios, stub_ios_driver) -> None:
    await _crash_state_snapshot(ctx_ios, CrashStateSnapshotArgs(label="a"))
    await _crash_state_snapshot(ctx_ios, CrashStateSnapshotArgs(label="b"))
    result = await _crash_state_diff(
        ctx_ios,
        CrashStateDiffArgs(label_a="a", label_b="b"),
    )
    assert result["result"]["status"] == "ok"


async def test_state_diff_missing_label(ctx_ios, stub_ios_driver) -> None:
    result = await _crash_state_diff(
        ctx_ios,
        CrashStateDiffArgs(label_a="missing_a", label_b="missing_b"),
    )
    assert result["result"]["status"] == "not_found"


async def test_anr_dump_android(ctx_android, stub_android_driver) -> None:
    result = await _crash_anr_dump(ctx_android, CrashAnrDumpArgs())
    assert result["result"]["status"] == "ok"


async def test_anr_dump_ios_unsupported(ctx_ios, stub_ios_driver) -> None:
    result = await _crash_anr_dump(ctx_ios, CrashAnrDumpArgs())
    assert result["result"]["status"] == "unsupported"


async def test_heap_dump_android(ctx_android, stub_android_driver, tmp_path) -> None:
    result = await _crash_heap_dump(
        ctx_android,
        CrashHeapDumpArgs(pid=1234, output_path=str(tmp_path / "heap.hprof")),
    )
    assert result["result"]["status"] == "ok"


async def test_thread_dump_android(ctx_android, stub_android_driver) -> None:
    result = await _crash_thread_dump(ctx_android, CrashThreadDumpArgs())
    assert result["result"]["status"] == "ok"
