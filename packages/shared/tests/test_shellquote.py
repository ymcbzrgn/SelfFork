"""Unit tests for :mod:`selffork_shared.shellquote`."""

from __future__ import annotations

import shlex

import pytest

from selffork_shared.shellquote import quote, quote_argv


@pytest.mark.parametrize(
    "raw",
    [
        "simple",
        "with space",
        "claude-opus-4-7[1m]",  # the zsh-glob crash case
        "$DOLLAR",
        "'apostrophe'",
        "*.py",
        "back\\slash",
        "tab\there",
        "with;semicolon",
        "and|pipe",
        "&background",
    ],
)
def test_quote_matches_shlex(raw: str) -> None:
    assert quote(raw) == shlex.quote(raw)


def test_quote_argv_matches_shlex_join() -> None:
    args = ["a", "b c", "$HOME", "*.py", "claude-opus-4-7[1m]"]
    assert quote_argv(args) == shlex.join(args)


def test_quote_empty_string_is_quoted() -> None:
    # Empty string must be quoted to be a real positional arg.
    assert quote("") == "''"


def test_quote_argv_with_iterator_input() -> None:
    args_iter = iter(["a", "b c"])
    result = quote_argv(args_iter)
    assert result == "a 'b c'"
