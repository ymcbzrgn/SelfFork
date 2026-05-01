"""Unit tests for :func:`parse_tool_calls`."""

from __future__ import annotations

import pytest

from selffork_orchestrator.tools.parser import parse_tool_calls


class TestParseToolCalls:
    def test_empty_reply_returns_empty(self) -> None:
        assert parse_tool_calls("") == []

    def test_no_blocks_returns_empty(self) -> None:
        assert parse_tool_calls("Just a regular reply.") == []

    def test_single_well_formed(self) -> None:
        reply = (
            "Sure, I'll move that.\n"
            "<selffork-tool-call>\n"
            '{"tool": "kanban_card_done", "args": {"card_id": "card-123"}}\n'
            "</selffork-tool-call>"
        )
        calls = parse_tool_calls(reply)
        assert len(calls) == 1
        assert calls[0].tool == "kanban_card_done"
        assert calls[0].args == {"card_id": "card-123"}
        assert calls[0].order_in_reply == 0

    def test_multiple_blocks_in_order(self) -> None:
        reply = (
            "<selffork-tool-call>"
            '{"tool": "a", "args": {"x": 1}}'
            "</selffork-tool-call>\n"
            "Some prose.\n"
            "<selffork-tool-call>"
            '{"tool": "b", "args": {"x": 2}}'
            "</selffork-tool-call>"
        )
        calls = parse_tool_calls(reply)
        assert [c.tool for c in calls] == ["a", "b"]
        assert calls[0].order_in_reply == 0
        assert calls[1].order_in_reply == 1

    def test_case_insensitive_tag(self) -> None:
        reply = '<SelfFork-Tool-Call>{"tool": "x", "args": {}}</selffork-tool-call>'
        calls = parse_tool_calls(reply)
        assert len(calls) == 1
        assert calls[0].tool == "x"

    def test_malformed_json_silently_skipped(self) -> None:
        reply = (
            "<selffork-tool-call>not json</selffork-tool-call>\n"
            "<selffork-tool-call>"
            '{"tool": "valid", "args": {}}'
            "</selffork-tool-call>"
        )
        calls = parse_tool_calls(reply)
        assert len(calls) == 1
        assert calls[0].tool == "valid"

    def test_missing_tool_field_skipped(self) -> None:
        reply = '<selffork-tool-call>{"args": {"x": 1}}</selffork-tool-call>'
        assert parse_tool_calls(reply) == []

    def test_non_string_tool_skipped(self) -> None:
        reply = '<selffork-tool-call>{"tool": 123, "args": {}}</selffork-tool-call>'
        assert parse_tool_calls(reply) == []

    def test_missing_args_defaults_to_empty_dict(self) -> None:
        reply = '<selffork-tool-call>{"tool": "noop"}</selffork-tool-call>'
        calls = parse_tool_calls(reply)
        assert len(calls) == 1
        assert calls[0].args == {}

    def test_non_object_args_defaults_to_empty(self) -> None:
        # ``args`` not a dict (e.g. a list); we ignore and use {}.
        reply = '<selffork-tool-call>{"tool": "noop", "args": [1, 2, 3]}</selffork-tool-call>'
        calls = parse_tool_calls(reply)
        assert calls[0].args == {}

    def test_empty_block_body_skipped(self) -> None:
        reply = "<selffork-tool-call></selffork-tool-call>"
        assert parse_tool_calls(reply) == []

    @pytest.mark.parametrize(
        "noisy_reply",
        [
            # Mixed with DONE sentinel — should still find the call.
            (
                "All done!\n"
                "<selffork-tool-call>"
                '{"tool": "x", "args": {}}'
                "</selffork-tool-call>\n"
                "[SELFFORK:DONE]"
            ),
            # Multi-line JSON inside the block.
            (
                "<selffork-tool-call>\n"
                "{\n"
                '  "tool": "x",\n'
                '  "args": {\n'
                '    "deep": {"nested": [1, 2]}\n'
                "  }\n"
                "}\n"
                "</selffork-tool-call>"
            ),
        ],
    )
    def test_mixed_with_other_content(self, noisy_reply: str) -> None:
        calls = parse_tool_calls(noisy_reply)
        assert len(calls) == 1
        assert calls[0].tool == "x"
