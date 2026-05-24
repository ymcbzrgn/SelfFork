"""GeminiCliAgent — drive Google ``gemini`` CLI as SelfFork Jr's hand.

Per the architecture in ``project_selffork_jr_is_user_simulator.md`` and
``project_selffork_jr_drives_3_cli_agents.md``, ``gemini`` uses its own
provider config (the user's Google AI / Vertex AI credentials) to write
code. SelfFork Jr (local Gemma 4 E2B-it on mlx-server) writes
operator-style coaching messages; we type each SelfFork-Jr reply into
``gemini -p`` (round 1) or ``gemini --resume latest -p`` (rounds 2+) and
feed the captured stdout back to SelfFork Jr as the next user-role
message.

Real gemini-cli CLI surface (verified by selffork-researcher 2026-05-01):
- Binary: ``gemini`` (npm ``@google/gemini-cli``).
- Non-interactive: ``gemini -p "msg"`` (the ``-p`` / ``--prompt`` flag,
  no ``run`` subcommand).
- Continuation: ``--resume latest`` / ``--resume <uuid>`` — does NOT
  support ``--continue`` / ``-c``.
- Output: default ``text`` to stdout (clean, human-readable).
- Auto-approve for unattended runs: ``--approval-mode yolo`` (the
  ``--yolo`` / ``-y`` short alias is deprecated; we use the modern
  long form). See project_per_cli_auto_approve_flags.md.
- Provider config: Google login or ``GEMINI_API_KEY``. SelfFork does NOT
  redirect.

CAVEAT (sequential-only in MVP): unlike opencode/claude-code,
``--resume latest`` is GLOBAL — it picks the most recent gemini session
on the host, not the most recent in the current cwd. As long as SelfFork
runs one gemini session per process at a time this is safe; once
multi-tmux orchestration lands (see ``project_yamac_jr_drives_3_cli_agents.md``)
we must capture the session UUID from the first call's
``--output-format json`` response and pass it explicitly via
``--resume <uuid>``. TODO: revisit before multi-tmux M2-M3 work begins.

Sources: docs at github.com/google-gemini/gemini-cli (cli-reference.md +
headless.md + session-management.md). See
``docs/decisions/ADR-001_MVP_v0.md`` §5.3.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path

from selffork_orchestrator.cli_agent.base import CLIAgent
from selffork_orchestrator.runtime.base import ChatMessage
from selffork_shared.config import CLIAgentConfig
from selffork_shared.errors import AgentBinaryNotFoundError

__all__ = ["DONE_SENTINEL", "GeminiCliAgent"]

# Common install locations probed if ``shutil.which`` can't find the binary.
# npm-global (Apple Silicon Homebrew prefix, Intel Homebrew prefix, or
# user-local npm prefix) covers the published install paths; ``~/.local/bin``
# is included for users who run npm with a custom prefix pointing there.
_COMMON_INSTALL_PATHS: tuple[Path, ...] = (
    Path.home() / ".local" / "bin" / "gemini",
    Path("/opt/homebrew/bin/gemini"),
    Path("/usr/local/bin/gemini"),
    Path.home() / ".npm-global" / "bin" / "gemini",
)

# Session-end sentinel. Identical literal across all three first-class
# CLIAgents (opencode / claude-code / gemini-cli) — see
# ``project_done_sentinel_protocol.md``.
DONE_SENTINEL = "[SELFFORK:DONE]"

# System prompt for SelfFork Jr at session start. Tuned for ``gemini``:
# Google's CLI emits clean prose by default (no JSON envelope). Continuation
# is global-scoped via ``--resume latest`` rather than cwd-scoped, so the
# orchestrator (not SelfFork Jr) is responsible for routing turns to the
# right session. SelfFork Jr's job stays the same: one concrete instruction
# per turn.
_SELFFORK_JR_SYSTEM_PROMPT = (
    "You are SelfFork Jr — the operator's user-simulator. You drive `gemini` "
    "(Google's gemini-cli, backed by a Gemini model). gemini writes the "
    "actual code; you write short, direct, operator-style INSTRUCTIONS to "
    "gemini in Turkish or English.\n\n"
    "Your job each round:\n"
    "  1. Read what gemini just produced (the previous user message in "
    "this conversation contains gemini's stdout).\n"
    "  2. Decide the next concrete step.\n"
    "  3. Write a short message to gemini telling it that step.\n\n"
    "STRICT RULES:\n"
    "  - On the FIRST round you receive the PRD. Your first reply MUST be "
    "a concrete instruction to gemini (e.g. \"Yaz bana hello.py'da add "
    'fonksiyonunu" or "Build add.py with add(a,b)->int and a pytest"). '
    "Do NOT skip work. Do NOT emit the session-end sentinel on round 0 "
    "under any circumstance.\n"
    "  - You DO NOT write code in your replies. gemini writes the code.\n"
    "  - Words like 'tamam' / 'bitti' / 'done' MAY legitimately appear in "
    "messages addressed to gemini (e.g. 'tamam, şu hatayı düzelt'). "
    "These do NOT end the session.\n"
    "  - Never wrap your reply in JSON or markdown fences. Plain text only.\n\n"
    "SESSION-END PROTOCOL (use ONLY when gemini has finished EVERY item "
    f"in the PRD's done criteria): include the literal tag {DONE_SENTINEL} "
    "on its own line at the end of your reply. This is for the SelfFork "
    "orchestrator, not gemini. Never include it before the work is "
    "verified done."
)


# Effort -> gemini thinking config (S6, ADR-006 §4.6). gemini-cli 0.39.1 has
# NO per-invoke thinking flag; thinking is a settings-file knob gated behind
# ``experimental.dynamicModelConfiguration`` (verified vs the installed
# bundle 2026-05-24). gemini-2.5 takes a numeric ``thinkingBudget``; Gemini-3
# takes a ``thinkingLevel`` enum (only ``HIGH`` is locally-verified).
# ``dynamic``/unset => no write (gemini's own default; opt-in per operator).
_THINKING_BUDGETS: dict[str, int] = {
    "off": 0,
    "low": 2048,
    "medium": 8192,
    "high": 24576,
}
_THINKING_LEVELS: dict[str, str] = {"high": "HIGH"}


def _matches_model(entry: object, model: str) -> bool:
    """True if a ``customOverrides`` entry targets ``model`` via ``match.model``."""
    if not isinstance(entry, dict):
        return False
    match = entry.get("match")
    return isinstance(match, dict) and match.get("model") == model


def _write_gemini_thinking_settings(
    workspace: Path,
    *,
    model: str,
    thinking: dict[str, object],
) -> None:
    """Read-merge-write ``<workspace>/.gemini/settings.json`` with a
    model-targeted thinking override. Preserves every other key; refuses to
    clobber an existing unreadable file.
    """
    path = workspace / ".gemini" / "settings.json"
    settings: dict[str, object] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return  # never clobber an existing unreadable settings file
        if isinstance(loaded, dict):
            settings = loaded
    # 1) experimental.dynamicModelConfiguration gate — REQUIRED (modelConfigs
    #    is inert without it; verified vs the installed bundle 2026-05-24).
    raw_exp = settings.get("experimental")
    experimental: dict[str, object] = raw_exp if isinstance(raw_exp, dict) else {}
    experimental["dynamicModelConfiguration"] = True
    settings["experimental"] = experimental
    # 2) modelConfigs.customOverrides — additive list; replace this model's
    #    entry idempotently (concat'd onto built-ins by gemini at resolve).
    raw_mc = settings.get("modelConfigs")
    model_configs: dict[str, object] = raw_mc if isinstance(raw_mc, dict) else {}
    raw_overrides = model_configs.get("customOverrides")
    overrides: list[object] = (
        list(raw_overrides) if isinstance(raw_overrides, list) else []
    )
    overrides = [o for o in overrides if not _matches_model(o, model)]
    overrides.append(
        {
            "match": {"model": model},
            "modelConfig": {
                "generateContentConfig": {"thinkingConfig": dict(thinking)},
            },
        }
    )
    model_configs["customOverrides"] = overrides
    settings["modelConfigs"] = model_configs
    # 3) atomic write (temp + replace; a reader never sees a torn file).
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(settings, fp, indent=2)
        os.replace(tmp_name, path)
    except Exception:
        with suppress(OSError):
            os.unlink(tmp_name)
        raise


class GeminiCliAgent(CLIAgent):
    """CLIAgent for ``gemini`` (Google gemini-cli)."""

    def __init__(self, config: CLIAgentConfig) -> None:
        if config.agent != "gemini-cli":
            raise ValueError(
                f"GeminiCliAgent requires agent='gemini-cli', got {config.agent!r}",
            )
        self._config = config

    def resolve_binary(self) -> str:
        if self._config.binary_path:
            path = Path(self._config.binary_path).expanduser()
            if path.is_file() and os.access(path, os.X_OK):
                return str(path)
            raise AgentBinaryNotFoundError(
                f"configured binary_path is not an executable file: {path}",
            )
        found = shutil.which("gemini")
        if found is not None:
            return found
        for candidate in _COMMON_INSTALL_PATHS:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
        raise AgentBinaryNotFoundError(
            "gemini binary not found. Install via 'npm install -g @google/gemini-cli' "
            "(or 'brew install gemini-cli') or set cli_agent.binary_path in "
            "selffork.yaml.",
        )

    def compose_initial_messages(
        self,
        *,
        prd: str,
        plan_path: str,
        workspace: str,
    ) -> list[ChatMessage]:
        user_intro = (
            f"PRD aşağıda. gemini'yi sana ver, görev bitene kadar yönlendir.\n\n"
            f"Workspace (gemini'nin cwd'si): `{workspace}`\n"
            f"Plan-as-state dosyası: `{plan_path}` "
            f"(gemini'ye 'oradaki sub-task'ları güncelle' diye söyleyebilirsin).\n\n"
            f"=== PRD ===\n{prd}\n=== /PRD ===\n\n"
            f"Şimdi gemini'ye verilecek **ilk mesajını** yaz. Kısa ve net. "
            f"Türkçe ya da İngilizce farketmez."
        )
        return [
            {"role": "system", "content": _SELFFORK_JR_SYSTEM_PROMPT},
            {"role": "user", "content": user_intro},
        ]

    def build_command(self, *, message: str, is_first_round: bool) -> list[str]:
        # Layout:
        #   gemini --skip-trust [--resume latest] --approval-mode yolo -p \
        #          [extra_args] "msg"
        # ``--skip-trust`` bypasses gemini-cli's trusted-folder gate, which
        # otherwise downgrades ``--approval-mode yolo`` to ``default`` in
        # any cwd not previously trusted via interactive mode. SelfFork
        # runs CLIs in fresh sandbox workspaces that are always untrusted,
        # so this flag is required for unattended runs. (Equivalent env
        # var: ``GEMINI_CLI_TRUST_WORKSPACE=true``.)
        # ``-p`` carries the prompt as positional. ``--resume latest``
        # resumes the most recent session (caveat: global-scoped — see
        # module docstring). ``--approval-mode yolo`` is the modern
        # non-deprecated form of -y.
        # See: ``project_per_cli_auto_approve_flags.md`` and
        # geminicli.com/docs/cli/trusted-folders/#headless-and-automated-environments.
        args: list[str] = ["--skip-trust"]
        if not is_first_round:
            args.extend(["--resume", "latest"])
        args.extend(["--approval-mode", "yolo"])
        # Model goes before ``-p`` (which immediately precedes the prompt).
        args.extend(self._model_args())
        args.append("-p")
        args.extend(self._config.extra_args)
        # Trailing positional: the user message we want gemini to act on.
        args.append(message)
        return args

    def prepare_workspace(self, workspace: str) -> None:
        """Write gemini's settings-file thinking config (opt-in, S6).

        Only when an effort is explicitly selected (!= ``dynamic``) AND a
        model is pinned — so default runs stay untouched and we never flip
        gemini's experimental model-config gate unless asked (operator
        decision 2026-05-24). Written to the WORKSPACE-local
        ``.gemini/settings.json`` (deep-merges over the user's ``~/.gemini``;
        never touches it) via read-merge-write.
        """
        effort = self._config.effort
        model = self._config.model
        if not model or effort is None or effort == "dynamic":
            return
        thinking: dict[str, object] | None = None
        if model.startswith("gemini-3"):
            level = _THINKING_LEVELS.get(effort)
            if level is not None:
                thinking = {"thinkingLevel": level}
        else:  # gemini-2.5 family -> numeric thinkingBudget
            budget = _THINKING_BUDGETS.get(effort)
            if budget is not None:
                thinking = {"thinkingBudget": budget}
        if thinking is None:
            return  # level not supported/verified for this model family
        _write_gemini_thinking_settings(
            Path(workspace), model=model, thinking=thinking
        )

    def build_env(self, base_env: Mapping[str, str]) -> dict[str, str]:
        env = dict(base_env)
        # Disable color / TTY heuristics so gemini's stdout is clean for
        # SelfFork Jr to read. gemini's provider credentials (Google login
        # or GEMINI_API_KEY) pass through untouched — SelfFork never
        # overrides them.
        env.setdefault("TERM", "dumb")
        env.setdefault("NO_COLOR", "1")
        return env

    def is_selffork_jr_done(self, reply: str) -> bool:
        # Strict literal match — see DONE_SENTINEL docstring above.
        return DONE_SENTINEL in reply
