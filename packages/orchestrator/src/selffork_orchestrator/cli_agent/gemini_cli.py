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

import os
import shutil
from collections.abc import Mapping
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
        args.append("-p")
        args.extend(self._config.extra_args)
        # Trailing positional: the user message we want gemini to act on.
        args.append(message)
        return args

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
