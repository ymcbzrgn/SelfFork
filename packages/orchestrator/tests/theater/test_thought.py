"""Unit tests for :mod:`selffork_orchestrator.theater.thought` — S2 Theater.

``parse_thought`` is a pure, deterministic function — no fixtures, no I/O.
"""

from __future__ import annotations

from selffork_orchestrator.theater.thought import parse_thought


class TestExplicitBlock:
    def test_extracts_thought_summary_block(self) -> None:
        reply = "<thought_summary>Testing the login flow.</thought_summary>"
        thought = parse_thought(reply)
        assert thought is not None
        assert thought.summary == "Testing the login flow."
        assert thought.raw == reply

    def test_block_wins_over_surrounding_prose(self) -> None:
        reply = (
            "Some directive prose here.\n"
            "<thought_summary>The real summary.</thought_summary>\n"
            "More prose."
        )
        thought = parse_thought(reply)
        assert thought is not None
        assert thought.summary == "The real summary."

    def test_block_is_case_insensitive(self) -> None:
        reply = "<THOUGHT_SUMMARY>Upper tags work.</THOUGHT_SUMMARY>"
        thought = parse_thought(reply)
        assert thought is not None
        assert thought.summary == "Upper tags work."

    def test_multiline_block_collapses_whitespace(self) -> None:
        reply = "<thought_summary>\n  line one\n  line two\n</thought_summary>"
        thought = parse_thought(reply)
        assert thought is not None
        assert thought.summary == "line one line two"

    def test_empty_block_falls_back_to_prose(self) -> None:
        reply = "<thought_summary>   </thought_summary> real prose"
        thought = parse_thought(reply)
        assert thought is not None
        assert thought.summary == "real prose"


class TestFallback:
    def test_plain_prose_is_the_summary(self) -> None:
        thought = parse_thought("I will check the signup page.")
        assert thought is not None
        assert thought.summary == "I will check the signup page."

    def test_strips_tool_call_blocks(self) -> None:
        reply = (
            "Moving the card.\n"
            "<selffork-tool-call>\n"
            '{"tool": "kanban_card_move", "args": {}}\n'
            "</selffork-tool-call>"
        )
        thought = parse_thought(reply)
        assert thought is not None
        assert thought.summary == "Moving the card."
        assert "selffork-tool-call" not in thought.summary

    def test_strips_done_and_spawn_sentinels(self) -> None:
        reply = "Wrapping up. [SELFFORK:DONE] [SELFFORK:SPAWN: do x]"
        thought = parse_thought(reply)
        assert thought is not None
        assert thought.summary == "Wrapping up."
        assert "SELFFORK" not in thought.summary

    def test_raw_keeps_the_unmodified_reply(self) -> None:
        reply = "Prose. <selffork-tool-call>{}</selffork-tool-call>"
        thought = parse_thought(reply)
        assert thought is not None
        assert thought.summary == "Prose."
        assert thought.raw == reply  # raw is unfiltered

    def test_long_reply_truncated_on_word_boundary(self) -> None:
        thought = parse_thought("word " * 200)  # ~1000 chars
        assert thought is not None
        assert len(thought.summary) <= 281  # 280 + the ellipsis
        assert thought.summary.endswith("…")
        assert not thought.summary.endswith(" …")


class TestNoThought:
    def test_empty_reply_returns_none(self) -> None:
        assert parse_thought("") is None
        assert parse_thought("   \n  ") is None

    def test_pure_tool_call_returns_none(self) -> None:
        reply = "<selffork-tool-call>{}</selffork-tool-call>"
        assert parse_thought(reply) is None

    def test_pure_sentinel_returns_none(self) -> None:
        assert parse_thought("[SELFFORK:DONE]") is None
