"""CodexAgent — drive OpenAI ``codex`` CLI as SelfFork Jr's hand.

Per ``project_selffork_jr_drives_3_cli_agents.md`` and the M3 ARGE
findings (2026-05-09), ChatGPT Plus subscription auth is funneled through
OpenAI's official ``@openai/codex`` CLI rather than ``opencode → ChatGPT``.
The reason: Codex CLI exposes a per-turn ``TokenCountEvent`` (with
``rate_limits.primary`` / ``secondary`` windows) in
``~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`` — the only auth-only
proactive quota signal available for ChatGPT subscribers.

Real Codex CLI surface (verified 2026-05-09):

- Binary: ``codex`` (npm ``@openai/codex``, Rust runtime).
- Auth: ``codex login`` browser OAuth → ``~/.codex/auth.json`` (no API key).
- Non-interactive: ``codex exec "msg"`` — single-shot headless.
- Continuation: ``codex exec --resume-last "msg"`` resumes the most
  recent rollout session in cwd (DeepWiki 4.4 Session Resumption).
- Auto-approve for unattended runs is the default in exec mode (no
  permissions prompt — exec mode is non-interactive).
- Rate-limit signal: NOT in stdout (Issue #14728); SelfFork reads
  ``~/.codex/sessions/.../rollout-*.jsonl`` ``token_count`` events via
  :class:`CodexSnapper` (Order 1).
- Provider config: model + reasoning effort live in ``~/.codex/config.toml``;
  SelfFork does NOT redirect.

Sources: DeepWiki ``openai/codex`` 4.4 · Codex CLI Reference
(developers.openai.com/codex/cli/reference) · Issues #14728, #15281.
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

__all__ = ["DONE_SENTINEL", "CodexAgent"]

# Common install locations probed if ``shutil.which`` can't find the binary.
# npm-global and Homebrew npm install at these locations; the Rust binary
# ships as an npm postinstall script, so the locations match standard
# package-manager paths.
_COMMON_INSTALL_PATHS: tuple[Path, ...] = (
    Path.home() / ".local" / "bin" / "codex",
    Path("/opt/homebrew/bin/codex"),
    Path("/usr/local/bin/codex"),
    Path.home() / ".npm-global" / "bin" / "codex",
    Path.home() / ".bun" / "bin" / "codex",
)

# Identical literal across all CLIAgents — see ``project_done_sentinel_protocol``.
DONE_SENTINEL = "[SELFFORK:DONE]"

# System prompt for SelfFork Jr at session start. Tuned for ``codex``:
# Codex emits prose mixed with code-fenced patches; we coach SelfFork Jr
# to give one concrete instruction per turn (plain text, no JSON envelope).
_SELFFORK_JR_SYSTEM_PROMPT = (
    "You are SelfFork Jr — the operator's user-simulator. You drive `codex` "
    "(OpenAI's official Codex CLI, backed by ChatGPT Plus auth). codex writes "
    "the actual code; you write short, direct, operator-style INSTRUCTIONS "
    "to codex in Turkish or English.\n\n"
    "Your job each round:\n"
    "  1. Read what codex just produced (the previous user message in "
    "this conversation contains codex's stdout).\n"
    "  2. Decide the next concrete step.\n"
    "  3. Write a short message to codex telling it that step.\n\n"
    "STRICT RULES:\n"
    "  - On the FIRST round you receive the PRD. Your first reply MUST be "
    "a concrete instruction to codex (e.g. \"Yaz bana hello.py'da add "
    'fonksiyonunu" or "Build add.py with add(a,b)->int and a pytest"). '
    "Do NOT skip work. Do NOT emit the session-end sentinel on round 0 "
    "under any circumstance.\n"
    "  - You DO NOT write code in your replies. codex writes the code.\n"
    "  - Words like 'tamam' / 'bitti' / 'done' MAY legitimately appear in "
    "messages addressed to codex (e.g. 'tamam, şu hatayı düzelt'). "
    "These do NOT end the session.\n"
    "  - Never wrap your reply in JSON or markdown fences. Plain text only.\n\n"
    "SESSION-END PROTOCOL (use ONLY when codex has finished EVERY item "
    f"in the PRD's done criteria): include the literal tag {DONE_SENTINEL} "
    "on its own line at the end of your reply. This is for the SelfFork "
    "orchestrator, not codex. Never include it before the work is "
    "verified done."
)


class CodexAgent(CLIAgent):
    """CLIAgent for ``codex`` (OpenAI Codex CLI, ChatGPT Plus auth)."""

    def __init__(self, config: CLIAgentConfig) -> None:
        if config.agent != "codex":
            raise ValueError(
                f"CodexAgent requires agent='codex', got {config.agent!r}",
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
        found = shutil.which("codex")
        if found is not None:
            return found
        for candidate in _COMMON_INSTALL_PATHS:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
        raise AgentBinaryNotFoundError(
            "codex binary not found. Install via "
            "'npm install -g @openai/codex' "
            "(then 'codex login' for ChatGPT Plus OAuth), or set "
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
            f"PRD aşağıda. codex'i sana ver, görev bitene kadar yönlendir.\n\n"
            f"Workspace (codex'in cwd'si): `{workspace}`\n"
            f"Plan-as-state dosyası: `{plan_path}` "
            f"(codex'e 'oradaki sub-task'ları güncelle' diye söyleyebilirsin).\n\n"
            f"=== PRD ===\n{prd}\n=== /PRD ===\n\n"
            f"Şimdi codex'e verilecek **ilk mesajını** yaz. Kısa ve net. "
            f"Türkçe ya da İngilizce farketmez."
        )
        return [
            {"role": "system", "content": _SELFFORK_JR_SYSTEM_PROMPT},
            {"role": "user", "content": user_intro},
        ]

    def build_command(self, *, message: str, is_first_round: bool) -> list[str]:
        # ``codex exec`` is the headless single-shot subcommand.
        # ``--resume-last`` continues the most recent rollout session in cwd
        # (DeepWiki 4.4 Session Resumption).
        #
        # Auto-approve flags (M4 close-out E2E smoke 2026-05-09):
        # * ``--skip-git-repo-check`` — codex refuses to write outside a
        #   git repo by default; orchestrator workspaces are not always
        #   git-init'd (`sandbox.workspace_root` may be a fresh temp dir).
        # * ``--dangerously-bypass-approvals-and-sandbox`` — codex's
        #   default sandbox policy is read-only, which makes file writes
        #   fail silently from Jr's perspective. Codex CLI ships this
        #   flag specifically for environments that are externally
        #   sandboxed (which we are: see `sandbox.mode` in selffork.yaml).
        #
        # Order: exec / skip-git / bypass / resume-last / extra_args / msg.
        args: list[str] = [
            "exec",
            "--skip-git-repo-check",
            "--dangerously-bypass-approvals-and-sandbox",
        ]
        if not is_first_round:
            args.append("--resume-last")
        args.extend(self._model_args())
        args.extend(self._config.extra_args)
        args.append(message)
        return args

    def build_env(self, base_env: Mapping[str, str]) -> dict[str, str]:
        env = dict(base_env)
        # Disable color / TTY heuristics so codex's stdout is clean for
        # SelfFork Jr to read. codex auth (``~/.codex/auth.json``) is read
        # by codex itself; we don't redirect.
        env.setdefault("TERM", "dumb")
        env.setdefault("NO_COLOR", "1")
        return env

    def is_selffork_jr_done(self, reply: str) -> bool:
        return DONE_SENTINEL in reply
