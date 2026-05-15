"""MinimaxCliAgent — drive Minimax ``mmx`` CLI as SelfFork Jr's hand.

Per ARGE 2026-05-09 + ``project_yamac_jr_drives_3_cli_agents``: Yamaç has
a Minimax subscription; ``mmx-cli`` (official MIT npm package
``@minimaxai/cli``, MiniMax-AI/cli on GitHub) authenticates via browser
OAuth → ``~/.mmx/credentials.json``. The CLI exposes
``api.minimax.io/anthropic`` — Anthropic-compatible — so SelfFork's
Claude bridge patterns translate one-to-one.

Real mmx CLI surface (best-effort defaults; refine when Yamaç verifies
on first run):

- Binary: ``mmx`` (npm ``@minimaxai/cli``, Rust runtime).
- Auth: ``mmx auth login`` browser OAuth → ``~/.mmx/credentials.json``.
- Non-interactive: ``mmx chat -p "msg"`` (analog to ``claude -p``).
- Continuation: ``mmx chat -c -p "msg"`` (analog to ``claude -c -p``).
- Quota probe (separate from CLI): ``GET api.minimax.io/v1/token_plan/remains``
  with Bearer ``MINIMAX_OAUTH_TOKEN`` (handled by the snapper layer).

Sources: ARGE 2026-05-09; github.com/MiniMax-AI/cli; platform.minimax.io.
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

__all__ = ["DONE_SENTINEL", "MinimaxCliAgent"]

# Common install locations probed if ``shutil.which`` can't find the binary.
_COMMON_INSTALL_PATHS: tuple[Path, ...] = (
    Path.home() / ".local" / "bin" / "mmx",
    Path("/opt/homebrew/bin/mmx"),
    Path("/usr/local/bin/mmx"),
    Path.home() / ".npm-global" / "bin" / "mmx",
    Path.home() / ".bun" / "bin" / "mmx",
)

# Identical literal across all CLIAgents — see ``project_done_sentinel_protocol``.
DONE_SENTINEL = "[SELFFORK:DONE]"

_SELFFORK_JR_SYSTEM_PROMPT = (
    "You are SelfFork Jr — the operator's user-simulator. You drive `mmx` "
    "(Minimax CLI, backed by a Minimax subscription via OAuth). mmx writes "
    "the actual code; you write short, direct, operator-style INSTRUCTIONS "
    "to mmx in Turkish or English.\n\n"
    "Your job each round:\n"
    "  1. Read what mmx just produced (the previous user message in "
    "this conversation contains mmx's stdout).\n"
    "  2. Decide the next concrete step.\n"
    "  3. Write a short message to mmx telling it that step.\n\n"
    "STRICT RULES:\n"
    "  - On the FIRST round you receive the PRD. Your first reply MUST be "
    "a concrete instruction to mmx (e.g. \"Yaz bana hello.py'da add "
    'fonksiyonunu" or "Build add.py with add(a,b)->int and a pytest"). '
    "Do NOT skip work. Do NOT emit the session-end sentinel on round 0 "
    "under any circumstance.\n"
    "  - You DO NOT write code in your replies. mmx writes the code.\n"
    "  - Words like 'tamam' / 'bitti' / 'done' MAY legitimately appear in "
    "messages addressed to mmx (e.g. 'tamam, şu hatayı düzelt'). "
    "These do NOT end the session.\n"
    "  - Never wrap your reply in JSON or markdown fences. Plain text only.\n\n"
    "SESSION-END PROTOCOL (use ONLY when mmx has finished EVERY item "
    f"in the PRD's done criteria): include the literal tag {DONE_SENTINEL} "
    "on its own line at the end of your reply. This is for the SelfFork "
    "orchestrator, not mmx. Never include it before the work is "
    "verified done."
)


class MinimaxCliAgent(CLIAgent):
    """CLIAgent for ``mmx`` (Minimax CLI, OAuth subscription auth)."""

    def __init__(self, config: CLIAgentConfig) -> None:
        if config.agent != "minimax-cli":
            raise ValueError(
                f"MinimaxCliAgent requires agent='minimax-cli', got {config.agent!r}",
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
        found = shutil.which("mmx")
        if found is not None:
            return found
        for candidate in _COMMON_INSTALL_PATHS:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
        raise AgentBinaryNotFoundError(
            "mmx binary not found. Install via "
            "'npm install -g @minimaxai/cli' "
            "(then 'mmx auth login' for Minimax OAuth), or set "
            "cli_agent.binary_path in selffork.yaml.",
        )

    def compose_initial_messages(
        self,
        *,
        prd: str,
        plan_path: str,
        workspace: str,
    ) -> list[ChatMessage]:
        user_intro = (
            f"PRD aşağıda. mmx'i sana ver, görev bitene kadar yönlendir.\n\n"
            f"Workspace (mmx'in cwd'si): `{workspace}`\n"
            f"Plan-as-state dosyası: `{plan_path}` "
            f"(mmx'e 'oradaki sub-task'ları güncelle' diye söyleyebilirsin).\n\n"
            f"=== PRD ===\n{prd}\n=== /PRD ===\n\n"
            f"Şimdi mmx'e verilecek **ilk mesajını** yaz. Kısa ve net. "
            f"Türkçe ya da İngilizce farketmez."
        )
        return [
            {"role": "system", "content": _SELFFORK_JR_SYSTEM_PROMPT},
            {"role": "user", "content": user_intro},
        ]

    def build_command(self, *, message: str, is_first_round: bool) -> list[str]:
        # Best-effort default: ``mmx chat -p "msg"`` for round 1, ``mmx chat
        # -c -p "msg"`` for continuation. Refine once Yamaç tests against the
        # real binary; the Anthropic-compatible endpoint suggests Claude-style
        # flag conventions.
        args: list[str] = ["chat"]
        if not is_first_round:
            args.append("-c")
        args.append("-p")
        args.extend(self._config.extra_args)
        args.append(message)
        return args

    def build_env(self, base_env: Mapping[str, str]) -> dict[str, str]:
        env = dict(base_env)
        env.setdefault("TERM", "dumb")
        env.setdefault("NO_COLOR", "1")
        return env

    def is_selffork_jr_done(self, reply: str) -> bool:
        return DONE_SENTINEL in reply
