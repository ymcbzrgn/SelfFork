"""ClaudeCodeAgent — drive Anthropic ``claude`` CLI as SelfFork Jr's hand.

Per the architecture in ``project_selffork_jr_is_user_simulator.md`` and
``project_selffork_jr_drives_3_cli_agents.md``, ``claude`` uses its own
provider config (the user's ``ANTHROPIC_API_KEY`` or login session) to
write code. SelfFork Jr (local Gemma 4 E2B-it on mlx-server) writes
operator-style coaching messages; we type each SelfFork-Jr reply into
``claude -p`` (round 1) or ``claude -c -p`` (rounds 2+) and feed the
captured stdout back to SelfFork Jr as the next user-role message.

Real claude CLI surface (verified by selffork-researcher 2026-05-01):
- Binary: ``claude`` (npm ``@anthropic-ai/claude-code``).
- Non-interactive: ``claude -p "msg"`` (the ``-p`` / ``--print`` flag, no
  ``run`` subcommand).
- Continuation in same cwd: ``claude -c -p "msg"`` (``-c`` /
  ``--continue`` resumes the most recent conversation in cwd).
- Output: default ``text`` to stdout (clean, human-readable).
- Auto-approve for unattended runs: ``--dangerously-skip-permissions``
  (NOT ``--allow-dangerously-skip-permissions``, which is a different,
  weaker flag — see project_per_cli_auto_approve_flags.md).
- Provider config: ``ANTHROPIC_API_KEY`` env or claude login. SelfFork
  does NOT redirect.

Sources: docs at code.claude.com/docs/en/cli-reference + headless +
setup. See ``docs/decisions/ADR-001_MVP_v0.md`` §5.3.
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

__all__ = ["DONE_SENTINEL", "ClaudeCodeAgent"]

# Common install locations probed if ``shutil.which`` can't find the binary.
# Native installer (code.claude.com/docs/en/setup) drops the binary at
# ``~/.local/bin/claude``; Homebrew + npm-global variants follow standard
# package-manager paths and are also enumerated as a defensive fallback.
_COMMON_INSTALL_PATHS: tuple[Path, ...] = (
    Path.home() / ".local" / "bin" / "claude",
    Path("/opt/homebrew/bin/claude"),
    Path("/usr/local/bin/claude"),
    Path.home() / ".npm-global" / "bin" / "claude",
)

# Session-end sentinel. SelfFork Jr signals "this session is over" by
# emitting this exact tag SOMEWHERE in its reply. Identical literal across
# all three first-class CLIAgents (opencode / claude-code / gemini-cli) so
# the round-loop driver can normalize done detection regardless of which
# CLI is mounted. Matches ``project_done_sentinel_protocol.md``.
DONE_SENTINEL = "[SELFFORK:DONE]"

# System prompt for SelfFork Jr at session start. Tuned for ``claude``:
# Anthropic's CLI emits clean prose (no JSON envelope) and supports
# multi-turn continuation natively, so we coach SelfFork Jr to give one
# concrete instruction per turn and let claude ask back if it needs to.
_SELFFORK_JR_SYSTEM_PROMPT = (
    "You are SelfFork Jr — the operator's user-simulator. You drive `claude` "
    "(Anthropic's claude-code CLI, backed by a Claude model). claude writes "
    "the actual code; you write short, direct, operator-style INSTRUCTIONS "
    "to claude in Turkish or English.\n\n"
    "Your job each round:\n"
    "  1. Read what claude just produced (the previous user message in "
    "this conversation contains claude's stdout).\n"
    "  2. Decide the next concrete step.\n"
    "  3. Write a short message to claude telling it that step.\n\n"
    "STRICT RULES:\n"
    "  - On the FIRST round you receive the PRD. Your first reply MUST be "
    "a concrete instruction to claude (e.g. \"Yaz bana hello.py'da add "
    'fonksiyonunu" or "Build add.py with add(a,b)->int and a pytest"). '
    "Do NOT skip work. Do NOT emit the session-end sentinel on round 0 "
    "under any circumstance.\n"
    "  - You DO NOT write code in your replies. claude writes the code.\n"
    "  - Words like 'tamam' / 'bitti' / 'done' MAY legitimately appear in "
    "messages addressed to claude (e.g. 'tamam, şu hatayı düzelt'). "
    "These do NOT end the session.\n"
    "  - Never wrap your reply in JSON or markdown fences. Plain text only.\n\n"
    "SESSION-END PROTOCOL (use ONLY when claude has finished EVERY item "
    f"in the PRD's done criteria): include the literal tag {DONE_SENTINEL} "
    "on its own line at the end of your reply. This is for the SelfFork "
    "orchestrator, not claude. Never include it before the work is "
    "verified done."
)


class ClaudeCodeAgent(CLIAgent):
    """CLIAgent for ``claude`` (Anthropic claude-code CLI)."""

    def __init__(self, config: CLIAgentConfig) -> None:
        if config.agent != "claude-code":
            raise ValueError(
                f"ClaudeCodeAgent requires agent='claude-code', got {config.agent!r}",
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
        found = shutil.which("claude")
        if found is not None:
            return found
        for candidate in _COMMON_INSTALL_PATHS:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
        raise AgentBinaryNotFoundError(
            "claude binary not found. Install via the native installer at "
            "code.claude.com/docs/en/setup (drops binary at "
            "~/.local/bin/claude) or 'npm install -g @anthropic-ai/claude-code', "
            "or set cli_agent.binary_path in selffork.yaml.",
        )

    def compose_initial_messages(
        self,
        *,
        prd: str,
        plan_path: str,
        workspace: str,
    ) -> list[ChatMessage]:
        user_intro = (
            f"PRD aşağıda. claude'u sana ver, görev bitene kadar yönlendir.\n\n"
            f"Workspace (claude'un cwd'si): `{workspace}`\n"
            f"Plan-as-state dosyası: `{plan_path}` "
            f"(claude'a 'oradaki sub-task'ları güncelle' diye söyleyebilirsin).\n\n"
            f"=== PRD ===\n{prd}\n=== /PRD ===\n\n"
            f"Şimdi claude'a verilecek **ilk mesajını** yaz. Kısa ve net. "
            f"Türkçe ya da İngilizce farketmez."
        )
        return [
            {"role": "system", "content": _SELFFORK_JR_SYSTEM_PROMPT},
            {"role": "user", "content": user_intro},
        ]

    def build_command(self, *, message: str, is_first_round: bool) -> list[str]:
        # claude needs an explicit ``--dangerously-skip-permissions`` for
        # unattended runs (no equivalent of opencode's permissionless
        # config-file mode). Order: -p / --continue / skip-perms / extra_args / msg.
        # See: ``project_per_cli_auto_approve_flags.md``.
        args: list[str] = ["-p"]
        if not is_first_round:
            args.append("--continue")
        args.append("--dangerously-skip-permissions")
        args.extend(self._config.extra_args)
        # Trailing positional: the user message we want claude to act on.
        args.append(message)
        return args

    def build_env(self, base_env: Mapping[str, str]) -> dict[str, str]:
        env = dict(base_env)
        # Disable color / TTY heuristics so claude's stdout is clean for
        # SelfFork Jr to read. claude's provider key (ANTHROPIC_API_KEY)
        # passes through untouched — SelfFork never overrides it.
        env.setdefault("TERM", "dumb")
        env.setdefault("NO_COLOR", "1")
        return env

    def is_selffork_jr_done(self, reply: str) -> bool:
        # Strict literal match — see DONE_SENTINEL docstring above.
        return DONE_SENTINEL in reply
