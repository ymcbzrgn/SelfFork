"""Cross-CLI proactive quota snapshot — normalized schema.

Each CLI exposes a different proactive quota signal source:
  - claude-code  : ~/.claude/statusline.sh stdin JSON push (1s refresh)
  - codex        : ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl TokenCountEvent append
  - gemini-cli   : ~/.gemini/telemetry.log OTel append + `/stats model` slash
  - opencode     : ~/.local/share/opencode/opencode.db SQLite + GET /event SSE

The per-CLI Snapper layer reads each source and projects it into THIS shape.
The SnapperRunner atomically writes ~/.selffork/cli-state/<cli_id>.json.
Consumers (UsageAggregator, Yamaç Jr `quota_snapshot()` autopilot tool, dashboard)
read the normalized shape without caring about per-CLI peculiarities.

Wire format is JSON; schema_version is bumped on breaking changes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WindowKind(StrEnum):
    """Subscription rate-limit window kinds, normalized across providers.

    Mapping notes:
      - five_hour: Claude Pro 5h rolling; Codex Plus `rate_limits.primary`
      - seven_day: Claude Pro weekly; Codex `rate_limits.secondary`
      - daily: Gemini OAuth Code Assist RPD; Minimax multimodal daily reset
      - per_minute: Gemini RPM; generic per-minute RPM caps
      - rolling: Generic rolling window driven by `window_minutes` (Codex-style)
      - unknown: Fallback when source signal is opaque (still capture used_pct + reset)
    """

    five_hour = "five_hour"
    seven_day = "seven_day"
    daily = "daily"
    per_minute = "per_minute"
    rolling = "rolling"
    unknown = "unknown"


class WindowState(BaseModel):
    """Single rate-limit window state.

    used_pct is canonical (0.0-100.0); resets_at is timezone-aware UTC.
    Source of truth captured from per-CLI snapper.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    used_pct: float = Field(ge=0.0, le=100.0)
    resets_at: datetime
    window_seconds: int = Field(gt=0)

    @field_validator("resets_at")
    @classmethod
    def _ensure_tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("WindowState.resets_at must be timezone-aware (UTC).")
        return v.astimezone(UTC)


class ContextState(BaseModel):
    """Current context-window utilization for the active CLI session."""

    model_config = ConfigDict(frozen=True, strict=True)

    used_tokens: int = Field(ge=0)
    total_tokens: int = Field(gt=0)
    used_pct: float = Field(ge=0.0)

    @field_validator("used_pct")
    @classmethod
    def _clamp_pct(cls, v: float) -> float:
        return min(max(v, 0.0), 100.0)


class QuotaSnapshot(BaseModel):
    """Normalized cross-CLI proactive quota snapshot.

    Atomically written to ``~/.selffork/cli-state/<cli_id>.json`` by SnapperRunner.
    Consumed by UsageAggregator (proactive layer) and Jr autopilot tool surface.

    - ``cli_id`` matches CLIAgent registry key (opencode, claude-code, codex,
      gemini-cli, minimax-cli, zai).
    - ``account_id`` distinguishes multi-account setups (future-proof; None
      for single-account today).
    - ``windows`` is a dict so each CLI populates only the windows it
      actually exposes (Claude → 5h+7d; Gemini → daily+per_minute;
      Codex → 5h+7d rolling).
    - ``context`` is None until the snapper has captured at least one
      assistant turn.
    - ``source`` is a free-form trace tag for debugging (which channel
      fed this snapshot).
    """

    model_config = ConfigDict(frozen=True, strict=True)

    schema_version: str = "1"
    cli_id: str
    account_id: str | None = None
    windows: dict[WindowKind, WindowState] = Field(default_factory=dict)
    context: ContextState | None = None
    captured_at: datetime
    source: str

    @field_validator("captured_at")
    @classmethod
    def _ensure_tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("QuotaSnapshot.captured_at must be timezone-aware (UTC).")
        return v.astimezone(UTC)

    @field_validator("cli_id")
    @classmethod
    def _strip_cli_id(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("QuotaSnapshot.cli_id must be a non-empty string.")
        return v

    def is_exhausted(self, threshold_pct: float = 95.0) -> bool:
        """True if any tracked window is at or above the exhaustion threshold."""
        return any(w.used_pct >= threshold_pct for w in self.windows.values())

    def soonest_reset(self) -> datetime | None:
        """Earliest ``resets_at`` across all tracked windows, or None if no windows."""
        if not self.windows:
            return None
        return min(w.resets_at for w in self.windows.values())

    def age_seconds(self, now: datetime | None = None) -> float:
        """How stale this snapshot is (seconds since ``captured_at``)."""
        ref = now if now is not None else datetime.now(tz=UTC)
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=UTC)
        return max((ref - self.captured_at).total_seconds(), 0.0)
