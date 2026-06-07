"""S-Vision Faz A — Voice modality scaffold tests (ADR-010 §3)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from selffork_orchestrator.voice import (
    NullVoiceBackend,
    VoiceBackend,
    VoiceTranscriptionError,
    VoiceUnavailableError,
    WhisperCliVoiceBackend,
    default_voice_backend,
)

# ── Protocol ─────────────────────────────────────────────────────────


def test_null_and_whisper_satisfy_protocol() -> None:
    assert isinstance(NullVoiceBackend(), VoiceBackend)
    assert isinstance(WhisperCliVoiceBackend(), VoiceBackend)


# ── NullVoiceBackend ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_null_backend_raises_unavailable() -> None:
    backend = NullVoiceBackend()
    with pytest.raises(VoiceUnavailableError, match="no voice backend"):
        await backend.transcribe(b"\x00\x01\x02")


# ── WhisperCliVoiceBackend ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_whisper_missing_binary_raises_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("selffork_orchestrator.voice.shutil.which", lambda _name: None)
    backend = WhisperCliVoiceBackend()
    with pytest.raises(VoiceUnavailableError, match="whisper CLI not found"):
        await backend.transcribe(b"audio")


@pytest.mark.asyncio
async def test_whisper_custom_binary_skips_lookup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A custom ``binary=`` overrides PATH lookup."""
    seen: dict[str, Any] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen["cmd"] = cmd
        # Write the transcript file the handler expects.
        out_dir = Path(cmd[cmd.index("--output_dir") + 1])
        (out_dir / "input.txt").write_text("ok\n", encoding="utf-8")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("selffork_orchestrator.voice.subprocess.run", fake_run)
    backend = WhisperCliVoiceBackend(
        binary="/opt/whisper/bin/whisper",
        model="tiny",
        language="tr",
    )
    transcript = await backend.transcribe(b"audio")
    assert transcript == "ok"
    assert seen["cmd"][0] == "/opt/whisper/bin/whisper"
    assert "--model" in seen["cmd"] and "tiny" in seen["cmd"]
    assert "--language" in seen["cmd"] and "tr" in seen["cmd"]
    assert "--output_format" in seen["cmd"] and "txt" in seen["cmd"]


@pytest.mark.asyncio
async def test_whisper_success_reads_transcript_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        out_dir = Path(cmd[cmd.index("--output_dir") + 1])
        (out_dir / "input.txt").write_text("  merhaba dünya  \n", encoding="utf-8")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("selffork_orchestrator.voice.shutil.which", lambda _n: "/bin/whisper")
    monkeypatch.setattr("selffork_orchestrator.voice.subprocess.run", fake_run)
    backend = WhisperCliVoiceBackend()
    assert await backend.transcribe(b"audio") == "merhaba dünya"


@pytest.mark.asyncio
async def test_whisper_non_zero_exit_raises_transcription_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=cmd, returncode=1, stdout="", stderr="model file missing"
        )

    monkeypatch.setattr("selffork_orchestrator.voice.shutil.which", lambda _n: "/bin/whisper")
    monkeypatch.setattr("selffork_orchestrator.voice.subprocess.run", fake_run)
    backend = WhisperCliVoiceBackend()
    with pytest.raises(VoiceTranscriptionError, match="model file missing"):
        await backend.transcribe(b"audio")


@pytest.mark.asyncio
async def test_whisper_succeeds_but_no_transcript_file_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        # Returns 0 but writes NO transcript file.
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("selffork_orchestrator.voice.shutil.which", lambda _n: "/bin/whisper")
    monkeypatch.setattr("selffork_orchestrator.voice.subprocess.run", fake_run)
    backend = WhisperCliVoiceBackend()
    with pytest.raises(VoiceTranscriptionError, match="no transcript file"):
        await backend.transcribe(b"audio")


@pytest.mark.asyncio
async def test_whisper_timeout_raises_transcription_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=10)

    monkeypatch.setattr("selffork_orchestrator.voice.shutil.which", lambda _n: "/bin/whisper")
    monkeypatch.setattr("selffork_orchestrator.voice.subprocess.run", fake_run)
    backend = WhisperCliVoiceBackend(timeout_seconds=10)
    with pytest.raises(VoiceTranscriptionError, match="exceeded the 10s budget"):
        await backend.transcribe(b"audio")


# ── Factory ──────────────────────────────────────────────────────────


def test_default_backend_picks_whisper_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("selffork_orchestrator.voice.shutil.which", lambda _n: "/bin/whisper")
    backend = default_voice_backend()
    assert isinstance(backend, WhisperCliVoiceBackend)


def test_default_backend_falls_back_to_null_when_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("selffork_orchestrator.voice.shutil.which", lambda _n: None)
    backend = default_voice_backend()
    assert isinstance(backend, NullVoiceBackend)
