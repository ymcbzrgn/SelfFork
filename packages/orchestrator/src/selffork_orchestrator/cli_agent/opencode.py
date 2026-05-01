"""OpenCodeAgent — drive ``opencode`` CLI as SelfFork Jr's hand.

Per the architecture in ``project_selffork_jr_is_user_simulator.md``,
opencode uses its own provider (whatever the user has configured in
``opencode.json``) to write code. SelfFork Jr (local Gemma 4 E2B-it on
mlx-server) writes operator-style coaching messages; we type each SelfFork-Jr
reply into ``opencode run`` (round 1) or ``opencode run --continue``
(rounds 2+) and feed opencode's stdout back to SelfFork Jr as the next
user-role message.

Real opencode CLI surface (verified by selffork-researcher 2026-05-01):
- Subcommand: ``opencode run [message...]`` (NOT ``--print``).
- Continuation: ``-c`` / ``--continue``.
- Skip permissions for unattended runs: ``--dangerously-skip-permissions``.
- Output: human-readable text on stdout (NOT stream-json).
- Provider config: ``~/.config/opencode/opencode.json`` or
  ``OPENCODE_CONFIG_CONTENT`` env var. SelfFork does NOT redirect.

Pattern reference for binary resolution:
`prior art in the agentic-CLI orchestration space`.

See: ``docs/decisions/ADR-001_MVP_v0.md`` §5.3.
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

__all__ = ["OpenCodeAgent"]

# Common install locations probed if ``shutil.which`` can't find the binary.
_COMMON_INSTALL_PATHS: tuple[Path, ...] = (
    Path.home() / ".local" / "bin" / "opencode",
    Path("/opt/opencode/bin/opencode"),
    Path("/usr/local/bin/opencode"),
    Path("/opt/homebrew/bin/opencode"),
)

# Session-end sentinel. SelfFork Jr signals "this session is over" by
# emitting this exact tag SOMEWHERE in its reply (start, end, anywhere).
# It is intentionally an unusual literal so it never collides with text
# SelfFork Jr might naturally say to opencode (e.g. "tamam, şunu da yap" or
# "done with that step, now refactor X"). Words like "tamam"/"bitti"/
# "done" frequently appear as in-message instructions to opencode and
# MUST NOT trigger session termination.
DONE_SENTINEL = "[SELFFORK:DONE]"

# System prompt for SelfFork Jr at session start. Kept terse — the adapter
# (M7+) carries the actual operator voice; until then this nudges a base
# model toward the right register. Order matters: the "what to do now"
# instruction comes BEFORE the session-end protocol, because small models
# (Gemma 4 E2B 4bit) tend to over-fixate on the last instruction in the
# system message and emit the sentinel immediately.
_YAMAC_JR_SYSTEM_PROMPT = (
    "You are SelfFork Jr — the operator's user-simulator. You drive `opencode` (a CLI "
    "coding agent backed by a powerful provider). opencode writes the "
    "actual code; you write short, direct, operator-style INSTRUCTIONS to "
    "opencode in Turkish or English.\n\n"
    "Your job each round:\n"
    "  1. Read what opencode just produced (the previous user message in "
    "this conversation contains opencode's output).\n"
    "  2. Decide the next concrete step.\n"
    "  3. Write a short message to opencode telling it that step.\n\n"
    "STRICT RULES:\n"
    "  - On the FIRST round you receive the PRD. Your first reply MUST be "
    "a concrete instruction to opencode (e.g. \"Yaz bana hello.py'da add "
    'fonksiyonunu" or "Build add.py with add(a,b)->int and a pytest"). '
    "Do NOT skip work. Do NOT emit the session-end sentinel on round 0 "
    "under any circumstance.\n"
    "  - You DO NOT write code in your replies. opencode writes the code.\n"
    "  - Words like 'tamam' / 'bitti' / 'done' MAY legitimately appear in "
    "messages addressed to opencode (e.g. 'tamam, şu hatayı düzelt'). "
    "These do NOT end the session.\n"
    "  - Never wrap your reply in JSON or markdown fences. Plain text only.\n\n"
    "SESSION-END PROTOCOL (use ONLY when opencode has finished EVERY item "
    f"in the PRD's done criteria): include the literal tag {DONE_SENTINEL} "
    "on its own line at the end of your reply. This is for the SelfFork "
    "orchestrator, not opencode. Never include it before the work is "
    "verified done."
)


class OpenCodeAgent(CLIAgent):
    """CLIAgent for ``opencode``."""

    def __init__(self, config: CLIAgentConfig) -> None:
        if config.agent != "opencode":
            raise ValueError(
                f"OpenCodeAgent requires agent='opencode', got {config.agent!r}",
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
        found = shutil.which("opencode")
        if found is not None:
            return found
        for candidate in _COMMON_INSTALL_PATHS:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
        raise AgentBinaryNotFoundError(
            "opencode binary not found. Install via 'npm install -g opencode-ai' "
            "(or your preferred packaging) or set cli_agent.binary_path in "
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
            f"PRD aşağıda. opencode'u sana ver, görev bitene kadar yönlendir.\n\n"
            f"Workspace (opencode'un cwd'si): `{workspace}`\n"
            f"Plan-as-state dosyası: `{plan_path}` "
            f"(opencode'a 'oradaki sub-task'ları güncelle' diye söyleyebilirsin).\n\n"
            f"=== PRD ===\n{prd}\n=== /PRD ===\n\n"
            f"Şimdi opencode'a verilecek **ilk mesajını** yaz. Kısa ve net. "
            f"Türkçe ya da İngilizce farketmez."
        )
        return [
            {"role": "system", "content": _YAMAC_JR_SYSTEM_PROMPT},
            {"role": "user", "content": user_intro},
        ]

    def build_command(self, *, message: str, is_first_round: bool) -> list[str]:
        # NB: opencode does NOT need an auto-approve CLI flag — its
        # ``opencode.json`` config carries that. The flag the user already
        # passes in interactive use is empty (``opencode``). For unattended
        # runs we still rely on the user's pre-existing config.
        # See: ``project_per_cli_auto_approve_flags.md``.
        args: list[str] = ["run"]
        if not is_first_round:
            args.append("--continue")
        args.extend(self._config.extra_args)
        # Trailing positional: the user message we want opencode to act on.
        args.append(message)
        return args

    def build_env(self, base_env: Mapping[str, str]) -> dict[str, str]:
        env = dict(base_env)
        # Disable color / TTY heuristics so opencode's stdout is clean
        # for SelfFork Jr to read.
        env.setdefault("TERM", "dumb")
        env.setdefault("NO_COLOR", "1")
        return env

    def is_selffork_jr_done(self, reply: str) -> bool:
        # Strict literal match. Words like "tamam"/"bitti"/"done" may appear
        # in messages addressed to opencode and must NOT terminate the loop;
        # only an explicit ``[SELFFORK:DONE]`` sentinel does.
        return DONE_SENTINEL in reply
