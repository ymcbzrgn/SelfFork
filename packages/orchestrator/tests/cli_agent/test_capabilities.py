"""Per-CLI capability registry tests — verified flag conventions (S6)."""

from __future__ import annotations

import pytest

from selffork_orchestrator.cli_agent.capabilities import (
    candidate_pairs,
    capability_for,
)


def _cap(cli: str):
    cap = capability_for(cli)
    assert cap is not None
    return cap


def test_all_factory_clis_have_capability() -> None:
    for cli in (
        "claude-code",
        "codex",
        "gemini-cli",
        "opencode",
        "minimax-cli",
    ):
        assert capability_for(cli) is not None


def test_unknown_cli_returns_none() -> None:
    assert capability_for("bogus") is None


def test_claude_model_and_effort_are_flags() -> None:
    assert _cap("claude-code").model_args(model="opus", effort="max") == [
        "--model",
        "opus",
        "--effort",
        "max",
    ]


def test_claude_model_only_when_effort_none() -> None:
    # effort None ⇒ leave the CLI default (no flag); model still applied
    assert _cap("claude-code").model_args(model="sonnet", effort=None) == [
        "--model",
        "sonnet",
    ]


def test_codex_effort_is_config_kv() -> None:
    assert _cap("codex").model_args(model="gpt-5.5", effort="high") == [
        "-m",
        "gpt-5.5",
        "-c",
        "model_reasoning_effort=high",
    ]


def test_gemini_effort_is_settings_file_no_arg() -> None:
    # gemini thinking is settings.json-only — model_args gives just -m
    assert _cap("gemini-cli").model_args(
        model="gemini-2.5-pro", effort="high"
    ) == ["-m", "gemini-2.5-pro"]


def test_opencode_effort_is_variant_flag() -> None:
    assert _cap("opencode").model_args(
        model="openai/gpt-5.5", effort="high"
    ) == ["-m", "openai/gpt-5.5", "--variant", "high"]


def test_minimax_no_effort_knob() -> None:
    assert _cap("minimax-cli").model_args(
        model="MiniMax-M2.7", effort="high"
    ) == ["--model", "MiniMax-M2.7"]


def test_effort_clamp_invalid_to_default() -> None:
    cap = _cap("codex")
    assert cap.effort.clamp("bogus") == "xhigh"
    assert cap.effort.clamp("low") == "low"


def test_invalid_effort_clamped_in_model_args() -> None:
    # an unsupported level falls back to the default rather than erroring
    assert _cap("codex").model_args(model="gpt-5.5", effort="bogus") == [
        "-m",
        "gpt-5.5",
        "-c",
        "model_reasoning_effort=xhigh",
    ]


def test_only_gemini_has_per_model_quota() -> None:
    assert _cap("gemini-cli").per_model_quota is True
    for cli in ("claude-code", "codex", "opencode", "minimax-cli"):
        assert _cap(cli).per_model_quota is False


def test_candidate_pairs_enumerates_models() -> None:
    pairs = candidate_pairs(["claude-code", "codex"])
    assert ("claude-code", "opus") in pairs
    assert ("codex", "gpt-5.5") in pairs
    assert all(cli in ("claude-code", "codex") for cli, _ in pairs)


def test_candidate_pairs_honours_models_override() -> None:
    pairs = candidate_pairs(
        ["codex"], models_override={"codex": ("gpt-5.4-mini",)}
    )
    assert pairs == [("codex", "gpt-5.4-mini")]


def test_candidate_pairs_skips_unknown_cli() -> None:
    assert candidate_pairs(["bogus"]) == []


@pytest.mark.parametrize(
    ("cli", "model"),
    [
        ("claude-code", "opus"),
        ("codex", "gpt-5.5"),
        ("gemini-cli", "gemini-2.5-flash"),
        ("minimax-cli", "MiniMax-M2.7"),
    ],
)
def test_has_model_true_for_listed(cli: str, model: str) -> None:
    assert _cap(cli).has_model(model) is True
    assert _cap(cli).has_model("nope-9999") is False
