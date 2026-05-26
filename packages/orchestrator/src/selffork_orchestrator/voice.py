"""SelfFork Voice modality — Telegram-voice-only scaffold (ADR-010 §3 / S-Vision Faz A).

The operator sends a Telegram voice message; Self Jr transcribes the
audio via a pluggable :class:`VoiceBackend` and treats the result like a
normal text turn. No separate mobile microphone — the mobile companion
app is post-M7 (see [[s-vision-decisions]]).

This module is the **protocol seam** ([[no-mvp-full-quality-first-time]]
— pluggable interfaces day 1). The Telegram inbound side (parsing voice
attachments + dispatching here) wires in the follow-up Telegram bridge
work; the actual STT implementations (cloud Whisper, ElevenLabs, etc.)
plug in here without a wire-format break.

Two backends ship today:

* :class:`NullVoiceBackend` — explicit "no STT configured" stub. Always
  raises :class:`VoiceUnavailableError` so the caller renders a friendly
  message rather than silently dropping audio.
* :class:`WhisperCliVoiceBackend` — subprocess wrapper around the
  ``whisper`` CLI **as exposed by ``openai-whisper`` (the reference
  Python implementation)**. The flags assumed (``--output_format``,
  ``--output_dir``, ``--model <name>``) match openai-whisper; the
  whisper.cpp ``main`` binary uses different flags and a model PATH
  rather than a model NAME — wire a custom :class:`VoiceBackend` for
  that runtime. Graceful failures: missing binary →
  ``VoiceUnavailableError``; non-zero exit / no transcript file →
  ``VoiceTranscriptionError``.

:func:`default_voice_backend` picks Whisper when the binary is on PATH
and falls back to Null — the dashboard wires that into the Telegram
inbound side at boot.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol, runtime_checkable

__all__ = [
    "NullVoiceBackend",
    "VoiceBackend",
    "VoiceTranscriptionError",
    "VoiceUnavailableError",
    "WhisperCliVoiceBackend",
    "default_voice_backend",
]


_log = logging.getLogger(__name__)


class VoiceUnavailableError(RuntimeError):
    """Raised when a backend is structurally unavailable.

    Examples: ``NullVoiceBackend`` (intentionally absent), missing
    ``whisper`` binary on PATH. The caller catches this and surfaces a
    "voice not configured" hint to the operator rather than a stack
    trace.
    """


class VoiceTranscriptionError(RuntimeError):
    """Raised when a backend was available but transcription failed.

    Examples: ``whisper`` exited non-zero, output file unreadable. The
    caller distinguishes this from :class:`VoiceUnavailableError` —
    one means "fix your install", the other means "retry / inspect".
    """


@runtime_checkable
class VoiceBackend(Protocol):
    """Async STT contract.

    Implementations transcribe an audio blob (typically Telegram's OGG
    Opus, ``audio/ogg``) into a single text string. The ``mime`` arg
    lets backends pick the right decoder; backends that only handle one
    format ignore non-matching mimes and raise
    :class:`VoiceTranscriptionError`.
    """

    async def transcribe(
        self, audio: bytes, *, mime: str = "audio/ogg"
    ) -> str:
        """Return the transcript or raise.

        Raises:
            VoiceUnavailableError: backend is structurally absent.
            VoiceTranscriptionError: backend ran but failed.
        """
        ...


class NullVoiceBackend:
    """Explicit "no STT configured" backend — always raises.

    Default when :func:`default_voice_backend` cannot find a real
    backend. Lets the dashboard wire SOMETHING through the seam at boot
    so the Telegram side has a non-None reference; the user-facing
    error is friendly thanks to :class:`VoiceUnavailableError`.
    """

    async def transcribe(
        self, audio: bytes, *, mime: str = "audio/ogg"
    ) -> str:
        del audio, mime  # contract surface — null backend ignores both
        raise VoiceUnavailableError(
            "no voice backend configured; install whisper.cpp / OpenAI "
            "Whisper and set it on PATH, or wire a custom VoiceBackend"
        )


class WhisperCliVoiceBackend:
    """Subprocess wrapper around the ``whisper`` CLI.

    Writes the audio bytes to a temp file, runs ``whisper <temp>
    --output_format txt --output_dir <tmpdir>``, reads the resulting
    ``.txt`` sibling and returns its content. Cleans up on the way out.

    Configurable: pass ``binary`` for a custom path, ``model`` for the
    model name (default ``small`` — a reasonable CPU compromise), and
    ``language`` to skip auto-detect for known operator language.
    """

    DEFAULT_MODEL = "small"
    DEFAULT_TIMEOUT_SECONDS = 120

    def __init__(
        self,
        *,
        binary: str | None = None,
        model: str = DEFAULT_MODEL,
        language: str | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._binary = binary
        self._model = model
        self._language = language
        self._timeout = timeout_seconds

    def _resolve_binary(self) -> str:
        if self._binary is not None:
            return self._binary
        located = shutil.which("whisper")
        if located is None:
            raise VoiceUnavailableError(
                "whisper CLI not found on PATH; install with `pip install "
                "openai-whisper` or build whisper.cpp's `main` binary"
            )
        return located

    async def transcribe(
        self, audio: bytes, *, mime: str = "audio/ogg"
    ) -> str:
        del mime  # whisper auto-detects format from file content
        binary = self._resolve_binary()
        with tempfile.TemporaryDirectory(prefix="selffork-voice-") as tmp:
            tmpdir = Path(tmp)
            audio_path = tmpdir / "input.ogg"
            audio_path.write_bytes(audio)
            cmd = [
                binary,
                str(audio_path),
                "--output_format",
                "txt",
                "--output_dir",
                str(tmpdir),
                "--model",
                self._model,
            ]
            if self._language is not None:
                cmd.extend(["--language", self._language])
            try:
                proc = await asyncio.to_thread(
                    subprocess.run,
                    cmd,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=self._timeout,
                )
            except subprocess.TimeoutExpired as exc:
                msg = (
                    f"whisper exceeded the {self._timeout}s budget; the model"
                    f" may be too large for this host (current: {self._model})"
                )
                raise VoiceTranscriptionError(msg) from exc
            if proc.returncode != 0:
                msg = (
                    f"whisper exited {proc.returncode}: "
                    f"{proc.stderr.strip()[:500]}"
                )
                raise VoiceTranscriptionError(msg)
            transcript_path = tmpdir / "input.txt"
            if not transcript_path.is_file():
                msg = (
                    "whisper succeeded but produced no transcript file at "
                    f"{transcript_path.name}"
                )
                raise VoiceTranscriptionError(msg)
            return transcript_path.read_text(encoding="utf-8").strip()


def default_voice_backend() -> VoiceBackend:
    """Pick the best wirable backend; falls back to :class:`NullVoiceBackend`.

    Whisper wins when the binary is on PATH; otherwise the dashboard
    wires Null so the Telegram seam has a non-None reference and the
    operator-facing error is friendly.
    """
    if shutil.which("whisper") is not None:
        return WhisperCliVoiceBackend()
    # Debug, not info — this factory may be called many times per boot
    # (dashboard lifespan / tests); info would be ops noise. The error
    # surfaces clearly when :meth:`NullVoiceBackend.transcribe` is awaited.
    _log.debug(
        "selffork_voice_no_backend",
        extra={"hint": "install openai-whisper for STT, or wire a custom VoiceBackend"},
    )
    return NullVoiceBackend()
