"""Structured tool-call detection (AskUserQuestion-style) — S8 mini-prereq.

Self Jr drives a CLI agent (Claude Code / Codex / Gemini) and, increasingly,
emits its own ``<selffork-tool-call>`` blocks. Some of those calls are
*structured questions*: an AskUserQuestion-style choice prompt the operator
(or, at runtime, Self Jr) answers by picking an option rather than writing
free text. The fine-tune (M7) needs Self Jr to learn this reflex cleanly, so
we tag those calls in the audit log NOW (S8) — well before the interactive
round-trip bridge (S-Bridge) is built — so the dashboard can surface them and
S-Train can over-sample them.

Scope (deliberate): this module is **detection only**. It does NOT build the
interactive pause/resume bridge, validate option indices, or normalise a
question across CLIs — those are S-Bridge. Here we answer one question: *is
this tool name an AskUserQuestion-style structured choice?*

Wire point: :meth:`Session._handle_tool_calls` routes a matching
``<selffork-tool-call>`` to the ``tool.structured_question`` audit category
(and its result to ``tool.structured_answer``) instead of the generic
``tool.call`` / ``tool.result``. The activity feed (``GET /api/activity``)
then groups the request/response pair by ``call_id``.

CLI-agnostic by design: detection is by *tool name*, not by which of the
four SelfFork CLIs emitted it (``claude-code`` · ``codex`` · ``gemini-cli`` ·
``opencode`` — the ``DEFAULT_CLI_IDS`` set). Whichever CLI Self Jr is driving,
if a structured-choice tool with one of these names appears, it is tagged.
So opencode is **not** excluded — it is covered by the same name set.

Tool-name provenance (verified against local installs, 2026-05-25):

* ``AskUserQuestion`` — the literal PascalCase tool name used by BOTH
  **claude-code** (``~/.claude/projects/*/*.jsonl``, 94 hits) and **codex**
  (``~/.codex``, confirmed). The shared name is why the set is keyed by
  name, not CLI.
* ``ask_user_question`` — the snake_case variant that also appears in
  claude-code transcripts (56 hits) for the same tool.
* ``askUserQuestion`` — SelfFork's own canonical camelCase wire name for the
  structured tool (the S-Bridge ``<selffork-tool-call>`` contract; see
  ``project_jr_tool_protocol`` / ``s-bridge-sprint-added``).

Per-CLI status of the remaining two (no fabricated names —
``feedback_verify_research_locally``):

* **gemini-cli** — local history exposes only file/shell tools
  (``read_file`` / ``replace`` / ``run_shell_command`` / …); no
  AskUserQuestion-style tool observed. If gemini-cli grows one, S-Bridge —
  which instruments each CLI's interactive subprocess — adds its exact name.
* **opencode** — its session store is a SQLite DB (``opencode.db``), not a
  greppable transcript, so a structured-tool name could not be confirmed by
  inspection here. opencode is still covered the moment it emits any name in
  this set; S-Bridge instruments it directly to capture any opencode-specific
  spelling.
"""

from __future__ import annotations

__all__ = [
    "STRUCTURED_TOOL_NAMES",
    "is_structured_question",
]


# Exact-match registry of AskUserQuestion-style structured-choice tool names.
# Membership is a hard fact (verified transcript or our own wire contract),
# never a guess — matching is by exact name so an unrelated tool can't be
# mis-tagged.
#
# **Canonical name (S-ToolFleet Faz 0 F3):** ``AskUserQuestion`` is the ONLY
# name registered in the SelfFork tool registry; Self Jr's fine-tune corpus
# emits this spelling. The other two entries exist to AUDIT-route calls
# observed in third-party CLI transcripts (claude-code/codex) where this
# module's registry isn't the invocation surface. If Self Jr drifts to
# snake_case or camelCase, the call lands as ``status="unknown_tool"`` but
# still routes to ``tool.structured_*`` audit categories — drift is caught,
# not silently swallowed. See ``test_structured_tool_canonical_is_pascalcase
# _drift_unknown`` for the pinned invariant.
STRUCTURED_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "AskUserQuestion",
        "ask_user_question",
        "askUserQuestion",
    },
)


def is_structured_question(tool_name: str) -> bool:
    """Return ``True`` when ``tool_name`` is a known AskUserQuestion-style
    structured-choice tool.

    Used by the session round-loop to route the audit event to the
    ``tool.structured_question`` / ``tool.structured_answer`` categories and
    by the activity-feed aggregator to render the structured-Q/A pair with a
    distinct affordance. Exact match only — no normalisation, no fuzzy match
    (a fuzzy match would risk tagging an unrelated tool, the same false-
    positive class the ``[SELFFORK:DONE]`` sentinel protocol avoids).
    """
    return tool_name in STRUCTURED_TOOL_NAMES
