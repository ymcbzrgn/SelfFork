"""Unit tests for :mod:`selffork_shared.audit_reader`.

Mirrors the style of ``test_audit.py`` (the writer's tests): ``tmp_path``
fixtures, plain ``assert`` statements, ``-> None`` annotations. These tests
pin the *actual* behaviour of the read primitives, especially the tolerant
paths (malformed input is skipped, not raised).
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from selffork_shared.audit_reader import (
    RawAuditEvent,
    SessionSummary,
    infer_cli_from_binary,
    iter_session_events,
    list_audit_files,
    parse_audit_line,
    parse_iso_timestamp,
    summarize_session,
)


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    """Write one JSON object per line (trailing newline included)."""
    body = "\n".join(json.dumps(r) for r in records)
    path.write_text(body + "\n" if body else "", encoding="utf-8")


class TestParseIsoTimestamp:
    def test_z_suffix_treated_as_utc(self) -> None:
        result = parse_iso_timestamp("2026-07-02T10:00:00Z")
        assert result == datetime(2026, 7, 2, 10, 0, 0, tzinfo=UTC)
        assert result.utcoffset() == timedelta(0)

    def test_naive_assumed_utc(self) -> None:
        result = parse_iso_timestamp("2026-07-02T10:00:00")
        assert result == datetime(2026, 7, 2, 10, 0, 0, tzinfo=UTC)
        assert result.tzinfo is not None
        assert result.utcoffset() == timedelta(0)

    def test_tz_aware_converted_to_utc(self) -> None:
        # +03:00 wall clock 10:00 is 07:00 UTC.
        result = parse_iso_timestamp("2026-07-02T10:00:00+03:00")
        assert result == datetime(2026, 7, 2, 7, 0, 0, tzinfo=UTC)
        assert result.utcoffset() == timedelta(0)

    def test_z_and_explicit_offset_agree(self) -> None:
        assert parse_iso_timestamp("2026-07-02T10:00:00Z") == parse_iso_timestamp(
            "2026-07-02T10:00:00+00:00"
        )

    def test_microseconds_preserved(self) -> None:
        result = parse_iso_timestamp("2026-07-02T10:00:00.123456Z")
        assert result == datetime(2026, 7, 2, 10, 0, 0, 123456, tzinfo=UTC)

    @pytest.mark.parametrize("bad", ["", "not-a-timestamp", "2026-13-99T99:99:99"])
    def test_malformed_raises_value_error(self, bad: str) -> None:
        # NOTE: parse_iso_timestamp does NOT swallow errors; the caller
        # (parse_audit_line) is the layer that catches ValueError.
        with pytest.raises(ValueError):
            parse_iso_timestamp(bad)


class TestParseAuditLine:
    def test_well_formed_line(self) -> None:
        line = json.dumps(
            {
                "ts": "2026-07-02T10:00:00Z",
                "correlation_id": "01HJCORRELATION0000000000A",
                "session_id": "01HJSESSION00000000000000B",
                "category": "session.state",
                "level": "WARNING",
                "event": "state_change",
                "payload": {"to": "RUNNING"},
            }
        )
        ev = parse_audit_line(line)
        assert isinstance(ev, RawAuditEvent)
        assert ev.ts == datetime(2026, 7, 2, 10, 0, 0, tzinfo=UTC)
        assert ev.correlation_id == "01HJCORRELATION0000000000A"
        assert ev.session_id == "01HJSESSION00000000000000B"
        assert ev.category == "session.state"
        assert ev.level == "WARNING"
        assert ev.event == "state_change"
        assert ev.payload == {"to": "RUNNING"}

    def test_defaults_when_optional_keys_absent(self) -> None:
        line = json.dumps(
            {"ts": "2026-07-02T10:00:00Z", "category": "cat", "event": "evt"}
        )
        ev = parse_audit_line(line)
        assert ev is not None
        assert ev.correlation_id is None
        assert ev.level == "INFO"  # documented default
        assert ev.payload == {}
        assert ev.session_id == ""  # no value, no hint

    @pytest.mark.parametrize("bad", ["{not json", "", "   ", '{"ts": "x",'])
    def test_malformed_json_returns_none(self, bad: str) -> None:
        assert parse_audit_line(bad) is None

    @pytest.mark.parametrize("payload", ["42", "true", "null", '"a string"', "[1, 2, 3]"])
    def test_non_dict_json_returns_none(self, payload: str) -> None:
        assert parse_audit_line(payload) is None

    @pytest.mark.parametrize("missing", ["ts", "category", "event"])
    def test_missing_required_key_returns_none(self, missing: str) -> None:
        base = {
            "ts": "2026-07-02T10:00:00Z",
            "category": "cat",
            "event": "evt",
        }
        del base[missing]
        assert parse_audit_line(json.dumps(base)) is None

    def test_unparseable_ts_returns_none(self) -> None:
        # Valid JSON but the ts fails parse_iso_timestamp -> ValueError -> None.
        line = json.dumps({"ts": "garbage", "category": "cat", "event": "evt"})
        assert parse_audit_line(line) is None

    def test_session_id_hint_used_when_absent(self) -> None:
        line = json.dumps({"ts": "2026-07-02T10:00:00Z", "category": "c", "event": "e"})
        ev = parse_audit_line(line, session_id_hint="HINTSESSION")
        assert ev is not None
        assert ev.session_id == "HINTSESSION"

    def test_explicit_session_id_wins_over_hint(self) -> None:
        line = json.dumps(
            {
                "ts": "2026-07-02T10:00:00Z",
                "session_id": "EXPLICIT",
                "category": "c",
                "event": "e",
            }
        )
        ev = parse_audit_line(line, session_id_hint="HINT")
        assert ev is not None
        assert ev.session_id == "EXPLICIT"

    def test_empty_session_id_falls_through_to_hint(self) -> None:
        # SURPRISING: an explicit empty-string session_id is falsy, so the
        # ``or`` chain falls through to the hint.
        line = json.dumps(
            {
                "ts": "2026-07-02T10:00:00Z",
                "session_id": "",
                "category": "c",
                "event": "e",
            }
        )
        ev = parse_audit_line(line, session_id_hint="HINT")
        assert ev is not None
        assert ev.session_id == "HINT"

    def test_non_string_correlation_id_coerced(self) -> None:
        line = json.dumps(
            {
                "ts": "2026-07-02T10:00:00Z",
                "correlation_id": 12345,
                "category": "c",
                "event": "e",
            }
        )
        ev = parse_audit_line(line)
        assert ev is not None
        assert ev.correlation_id == "12345"


class TestListAuditFiles:
    def test_sorted_by_mtime_desc(self, tmp_path: Path) -> None:
        old = tmp_path / "old.jsonl"
        mid = tmp_path / "mid.jsonl"
        new = tmp_path / "new.jsonl"
        for p in (old, mid, new):
            p.write_text("{}\n", encoding="utf-8")
        os.utime(old, (1_000_000_000, 1_000_000_000))
        os.utime(mid, (1_000_000_100, 1_000_000_100))
        os.utime(new, (1_000_000_200, 1_000_000_200))

        result = list_audit_files([tmp_path])
        assert [p.name for p in result] == ["new.jsonl", "mid.jsonl", "old.jsonl"]

    def test_non_jsonl_ignored(self, tmp_path: Path) -> None:
        (tmp_path / "keep.jsonl").write_text("{}\n", encoding="utf-8")
        (tmp_path / "skip.json").write_text("{}\n", encoding="utf-8")
        (tmp_path / "skip.txt").write_text("x\n", encoding="utf-8")
        (tmp_path / "skip.log").write_text("x\n", encoding="utf-8")

        result = list_audit_files([tmp_path])
        assert [p.name for p in result] == ["keep.jsonl"]

    def test_subdirectory_ignored(self, tmp_path: Path) -> None:
        # A directory named like a jsonl file must not be listed (is_file gate).
        (tmp_path / "real.jsonl").write_text("{}\n", encoding="utf-8")
        (tmp_path / "fake.jsonl").mkdir()
        result = list_audit_files([tmp_path])
        assert [p.name for p in result] == ["real.jsonl"]

    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        assert list_audit_files([empty]) == []

    def test_missing_dir_skipped(self, tmp_path: Path) -> None:
        assert list_audit_files([tmp_path / "does-not-exist"]) == []

    def test_multiple_dirs_combined_and_sorted(self, tmp_path: Path) -> None:
        d1 = tmp_path / "d1"
        d2 = tmp_path / "d2"
        d1.mkdir()
        d2.mkdir()
        a = d1 / "a.jsonl"
        b = d2 / "b.jsonl"
        a.write_text("{}\n", encoding="utf-8")
        b.write_text("{}\n", encoding="utf-8")
        os.utime(a, (1_000_000_000, 1_000_000_000))
        os.utime(b, (1_000_000_500, 1_000_000_500))

        result = list_audit_files([d1, d2])
        assert [p.name for p in result] == ["b.jsonl", "a.jsonl"]


class TestInferCliFromBinary:
    @pytest.mark.parametrize(
        ("binary", "expected"),
        [
            ("opencode", "opencode"),
            ("claude", "claude-code"),
            ("gemini", "gemini-cli"),
            ("codex", "codex"),
            ("mmx", "minimax-cli"),
        ],
    )
    def test_known_bare_names(self, binary: str, expected: str) -> None:
        assert infer_cli_from_binary(binary) == expected

    @pytest.mark.parametrize(
        ("binary", "expected"),
        [
            ("/usr/local/bin/opencode", "opencode"),
            ("/opt/homebrew/bin/claude", "claude-code"),
            ("./node_modules/.bin/gemini", "gemini-cli"),
        ],
    )
    def test_posix_paths_use_basename(self, binary: str, expected: str) -> None:
        assert infer_cli_from_binary(binary) == expected

    def test_case_insensitive(self) -> None:
        assert infer_cli_from_binary("CLAUDE") == "claude-code"
        assert infer_cli_from_binary("/bin/OpenCode") == "opencode"

    @pytest.mark.parametrize("binary", ["python", "bash", "unknown-cli", ""])
    def test_unknown_returns_none(self, binary: str) -> None:
        assert infer_cli_from_binary(binary) is None

    def test_windows_backslash_not_split(self) -> None:
        # SURPRISING: only forward-slash is split, so a backslash path is
        # treated as one token and never matches -> None.
        assert infer_cli_from_binary(r"C:\\bin\\claude") is None


class TestIterSessionEvents:
    def test_yields_parseable_and_skips_malformed(self, tmp_path: Path) -> None:
        path = tmp_path / "SESSIONSTEM.jsonl"
        good1 = json.dumps({"ts": "2026-07-02T10:00:00Z", "category": "c", "event": "e1"})
        good2 = json.dumps({"ts": "2026-07-02T10:00:01Z", "category": "c", "event": "e2"})
        path.write_text(f"{good1}\n{{garbage\n\n{good2}\n", encoding="utf-8")

        events = list(iter_session_events(path))
        assert [ev.event for ev in events] == ["e1", "e2"]

    def test_session_id_defaults_to_stem(self, tmp_path: Path) -> None:
        path = tmp_path / "STEMASSESSION.jsonl"
        line = json.dumps({"ts": "2026-07-02T10:00:00Z", "category": "c", "event": "e"})
        path.write_text(line + "\n", encoding="utf-8")

        events = list(iter_session_events(path))
        assert len(events) == 1
        assert events[0].session_id == "STEMASSESSION"

    def test_missing_file_yields_nothing(self, tmp_path: Path) -> None:
        assert list(iter_session_events(tmp_path / "nope.jsonl")) == []


class TestSummarizeSession:
    def test_full_session(self, tmp_path: Path) -> None:
        path = tmp_path / "01HJSESSIONSUMMARY0000000A.jsonl"
        _write_jsonl(
            path,
            [
                {
                    "ts": "2026-07-02T10:00:00Z",
                    "category": "session.state",
                    "event": "init",
                    "payload": {"to": "PREPARING"},
                },
                {
                    "ts": "2026-07-02T10:00:01Z",
                    "category": "agent.invoke",
                    "event": "invoke",
                    "payload": {"binary": "/usr/bin/claude"},
                },
                {
                    "ts": "2026-07-02T10:00:02Z",
                    "category": "agent.invoke",
                    "event": "invoke",
                    "payload": {"binary": "/usr/bin/claude"},
                },
                {
                    "ts": "2026-07-02T10:00:03Z",
                    "category": "session.state",
                    "event": "state",
                    "payload": {"to": "RUNNING"},
                },
                {
                    "ts": "2026-07-02T10:00:05Z",
                    "category": "session.state",
                    "event": "state",
                    "payload": {"state": "COMPLETED"},
                },
            ],
        )

        summary = summarize_session(path)
        assert isinstance(summary, SessionSummary)
        assert summary.session_id == "01HJSESSIONSUMMARY0000000A"
        assert summary.started_at == datetime(2026, 7, 2, 10, 0, 0, tzinfo=UTC)
        assert summary.last_event_at == datetime(2026, 7, 2, 10, 0, 5, tzinfo=UTC)
        assert summary.final_state == "COMPLETED"  # last state wins; "state" key honoured
        assert summary.rounds_observed == 2
        assert summary.cli_agent == "claude-code"
        assert summary.audit_path == path

    def test_cli_inferred_from_sandbox_exec(self, tmp_path: Path) -> None:
        path = tmp_path / "sandbox.jsonl"
        _write_jsonl(
            path,
            [
                {
                    "ts": "2026-07-02T10:00:00Z",
                    "category": "session.state",
                    "event": "s",
                    "payload": {"to": "RUNNING"},
                },
                {
                    "ts": "2026-07-02T10:00:01Z",
                    "category": "sandbox.exec",
                    "event": "exec",
                    "payload": {"command": ["opencode", "run", "--task"]},
                },
            ],
        )

        summary = summarize_session(path)
        assert summary is not None
        assert summary.cli_agent == "opencode"
        assert summary.rounds_observed == 0  # sandbox.exec does not bump rounds
        assert summary.final_state == "RUNNING"

    def test_final_state_uses_to_key(self, tmp_path: Path) -> None:
        path = tmp_path / "tokey.jsonl"
        _write_jsonl(
            path,
            [
                {
                    "ts": "2026-07-02T10:00:00Z",
                    "category": "session.state",
                    "event": "s",
                    "payload": {"to": "DONE", "state": "IGNORED"},
                },
            ],
        )
        summary = summarize_session(path)
        assert summary is not None
        assert summary.final_state == "DONE"  # "to" preferred over "state"

    def test_empty_file_returns_none(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.jsonl"
        path.write_text("", encoding="utf-8")
        assert summarize_session(path) is None

    def test_only_unparseable_lines_returns_none(self, tmp_path: Path) -> None:
        path = tmp_path / "garbage.jsonl"
        path.write_text("{bad\nnot json\n[oops\n", encoding="utf-8")
        assert summarize_session(path) is None

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert summarize_session(tmp_path / "absent.jsonl") is None

    def test_unparseable_lines_skipped_between_valid(self, tmp_path: Path) -> None:
        path = tmp_path / "mixed.jsonl"
        good1 = json.dumps(
            {"ts": "2026-07-02T10:00:00Z", "category": "session.state", "event": "e"}
        )
        good2 = json.dumps(
            {"ts": "2026-07-02T10:00:09Z", "category": "session.state", "event": "e"}
        )
        path.write_text(f"{good1}\n{{broken\n{good2}\n", encoding="utf-8")

        summary = summarize_session(path)
        assert summary is not None
        assert summary.started_at == datetime(2026, 7, 2, 10, 0, 0, tzinfo=UTC)
        assert summary.last_event_at == datetime(2026, 7, 2, 10, 0, 9, tzinfo=UTC)

    def test_no_cli_when_binary_unrecognised(self, tmp_path: Path) -> None:
        path = tmp_path / "nocli.jsonl"
        _write_jsonl(
            path,
            [
                {
                    "ts": "2026-07-02T10:00:00Z",
                    "category": "agent.invoke",
                    "event": "invoke",
                    "payload": {"binary": "/usr/bin/some-unknown-runner"},
                },
            ],
        )
        summary = summarize_session(path)
        assert summary is not None
        assert summary.cli_agent is None
        assert summary.rounds_observed == 1
        assert summary.final_state is None
