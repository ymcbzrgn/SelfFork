"""Unit tests for ``cli_agent.structured_tools`` (S8 mini-prereq).

Detection is name-based and CLI-agnostic — the same set covers all four
SelfFork CLIs (claude-code / codex / gemini-cli / opencode). These tests
pin the verified names + the exact-match contract.
"""

from __future__ import annotations

from selffork_orchestrator.cli_agent.structured_tools import (
    STRUCTURED_TOOL_NAMES,
    is_structured_question,
)


class TestIsStructuredQuestion:
    def test_claude_and_codex_pascalcase(self) -> None:
        # Both claude-code and codex emit this exact PascalCase name
        # (verified ~/.claude transcripts + ~/.codex).
        assert is_structured_question("AskUserQuestion")

    def test_snake_case_variant(self) -> None:
        # The snake_case spelling also appears in claude-code transcripts.
        assert is_structured_question("ask_user_question")

    def test_selffork_wire_name(self) -> None:
        # SelfFork's own camelCase wire name (S-Bridge contract).
        assert is_structured_question("askUserQuestion")

    def test_regular_tools_not_detected(self) -> None:
        for name in ("Write", "Bash", "kanban_card_move", "Read", "run_shell_command"):
            assert not is_structured_question(name), name

    def test_empty_string_not_detected(self) -> None:
        assert not is_structured_question("")

    def test_exact_match_only_no_substring(self) -> None:
        # A fuzzy/substring match would risk tagging an unrelated tool —
        # the same false-positive class the [SELFFORK:DONE] sentinel avoids.
        assert not is_structured_question("AskUserQuestionV2")
        assert not is_structured_question("MyAskUserQuestion")
        assert not is_structured_question("ask_user")

    def test_registry_shape(self) -> None:
        assert isinstance(STRUCTURED_TOOL_NAMES, frozenset)
        assert {"AskUserQuestion", "ask_user_question", "askUserQuestion"} <= (
            STRUCTURED_TOOL_NAMES
        )
