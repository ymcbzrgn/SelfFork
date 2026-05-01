"""Unit tests for :func:`extract_spawn_requests`."""

from __future__ import annotations

import pytest

from selffork_orchestrator.spawn.sentinel import (
    SpawnRequest,
    extract_spawn_requests,
)


class TestExtractSpawnRequests:
    def test_empty_reply_returns_empty(self) -> None:
        assert extract_spawn_requests("") == []

    def test_no_sentinel_returns_empty(self) -> None:
        assert extract_spawn_requests("just regular Jr instruction text") == []

    def test_single_spawn(self) -> None:
        reply = "[SELFFORK:SPAWN: Build add.py with add(a, b) function]"
        requests = extract_spawn_requests(reply)
        assert requests == [
            SpawnRequest(index=0, spec="Build add.py with add(a, b) function"),
        ]

    def test_multiple_spawns_indexed_in_order(self) -> None:
        reply = (
            "Here are two parallel jobs:\n"
            "[SELFFORK:SPAWN: Build divide.py and test_divide.py]\n"
            "[SELFFORK:SPAWN: Build subtract.py and test_subtract.py]\n"
            "I'll wait for both."
        )
        requests = extract_spawn_requests(reply)
        assert len(requests) == 2
        assert requests[0].index == 0
        assert "divide" in requests[0].spec
        assert requests[1].index == 1
        assert "subtract" in requests[1].spec

    def test_strips_whitespace_around_spec(self) -> None:
        reply = "[SELFFORK:SPAWN:    spaced spec   ]"
        requests = extract_spawn_requests(reply)
        assert requests == [SpawnRequest(index=0, spec="spaced spec")]

    def test_empty_spec_ignored(self) -> None:
        # Whitespace-only specs would spawn empty children — drop them.
        reply = "[SELFFORK:SPAWN:   ]"
        assert extract_spawn_requests(reply) == []

    def test_unclosed_sentinel_ignored(self) -> None:
        # A SPAWN with no closing ] is malformed; Jr is a small model
        # and we'd rather drop noise than crash.
        reply = "[SELFFORK:SPAWN: missing close bracket"
        assert extract_spawn_requests(reply) == []

    def test_case_insensitive_matching(self) -> None:
        # Lowercase variants are tolerated (small models drift on caps).
        reply = "[selffork:spawn: lowercase test]"
        requests = extract_spawn_requests(reply)
        assert requests == [SpawnRequest(index=0, spec="lowercase test")]

    @pytest.mark.parametrize(
        "noisy_reply",
        [
            "Some prose. [SELFFORK:SPAWN: do thing one] More prose.",
            "[SELFFORK:SPAWN: do thing one]\n\n\n[SELFFORK:SPAWN: do thing two]",
            "  [SELFFORK:SPAWN: indented]  ",
        ],
    )
    def test_handles_surrounding_text(self, noisy_reply: str) -> None:
        requests = extract_spawn_requests(noisy_reply)
        assert len(requests) >= 1
        for r in requests:
            assert r.spec  # non-empty

    def test_does_not_match_done_sentinel(self) -> None:
        # A reply that ONLY has DONE — no SPAWN — must yield nothing here.
        # The DONE/SPAWN priority is the run-loop's call, not the parser's.
        reply = "All done. [SELFFORK:DONE]"
        assert extract_spawn_requests(reply) == []

    def test_spec_does_not_swallow_outer_brackets(self) -> None:
        # The greedy-but-stop-at-first-] semantics matter: a SPAWN spec
        # ends at the first ``]`` even if the surrounding reply has more
        # bracketed text afterwards.
        reply = "[SELFFORK:SPAWN: build foo.py] then [some other note]"
        requests = extract_spawn_requests(reply)
        assert requests == [SpawnRequest(index=0, spec="build foo.py")]
