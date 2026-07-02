"""Tests for the S-Train T1 session-capture normalizer.

Synthetic audit-event lists only -- no ``selffork-shared`` import, no I/O, no
heavy deps (reflex is dependency-free). Covers the locked loss mask
(``docs/Operator_Locked_Decisions.md`` section 3), sample-per-operator-message
generation, prefix growth, and the pure-core / glue boundary.
"""

from __future__ import annotations

from collections.abc import Mapping

from selffork_reflex.data import (
    INACTIVE_WEIGHT,
    PRIOR_OPERATOR_WEIGHT,
    SYSTEM_PROMPT,
    TARGET_OPERATOR_WEIGHT,
    ChatMessage,
    SessionEvent,
    event_to_message,
    normalize_from_audit,
    normalize_session,
    session_event_from_mapping,
    session_events_from_audit,
)

# Verbatim canonical system prompt from docs/Operator_Locked_Decisions.md
# section 2. Hard-coded here (not imported) so a drift in the constant fails
# this test loudly -- the prompt is a frozen retraining-gated input.
EXPECTED_SYSTEM_PROMPT = (
    "You are Yamaç Jr. Nano. Your task is to predict how Yamaç would respond "
    "in this situation."
)


def _op(text: str) -> SessionEvent:
    """An operator (Yamac) message -- the round loop's ``selffork_jr.reply``."""
    return SessionEvent(category="selffork_jr.reply", payload={"round": 0, "text": text})


def _agent_invoke() -> SessionEvent:
    return SessionEvent(
        category="agent.invoke",
        payload={"round": 0, "binary": "/x/claude", "args_count": 2},
    )


def _agent_output() -> SessionEvent:
    return SessionEvent(
        category="agent.output",
        payload={"round": 0, "exit_code": 0, "output_chars": 128, "stderr_chars": 0},
    )


def _tool_call(tool: str) -> SessionEvent:
    return SessionEvent(
        category="tool.call",
        payload={"round": 0, "tool": tool, "args": {"path": "a.py"}, "order": 0},
    )


def _tool_result(tool: str) -> SessionEvent:
    return SessionEvent(
        category="tool.result",
        payload={"round": 0, "tool": tool, "status": "ok", "order": 0},
    )


def _lifecycle() -> SessionEvent:
    return SessionEvent(category="session.state", payload={"to": "RUNNING"})


# --------------------------------------------------------------------------
# System prompt + constants
# --------------------------------------------------------------------------


def test_system_prompt_matches_locked_decisions_verbatim() -> None:
    assert SYSTEM_PROMPT == EXPECTED_SYSTEM_PROMPT


def test_loss_weight_constants_match_locked_table() -> None:
    assert INACTIVE_WEIGHT == 0.0
    assert PRIOR_OPERATOR_WEIGHT == 0.3
    assert TARGET_OPERATOR_WEIGHT == 1.0


# --------------------------------------------------------------------------
# Role discriminator + per-event base weighting
# --------------------------------------------------------------------------


def test_operator_discriminator_is_selffork_jr_reply() -> None:
    op = event_to_message(_op("hi"))
    assert op.role == "operator"
    assert op.content == "hi"
    # base (non-target) operator weight
    assert op.loss_weight == PRIOR_OPERATOR_WEIGHT


def test_agent_and_tool_and_context_events_are_weight_zero() -> None:
    assert event_to_message(_agent_invoke()).role == "assistant"
    assert event_to_message(_agent_output()).role == "assistant"
    assert event_to_message(_tool_call("read_file")).role == "tool"
    assert event_to_message(_tool_result("read_file")).role == "tool"
    assert event_to_message(_lifecycle()).role == "context"
    non_operator = (
        _agent_invoke(),
        _agent_output(),
        _tool_call("x"),
        _tool_result("x"),
        _lifecycle(),
    )
    for event in non_operator:
        assert event_to_message(event).loss_weight == INACTIVE_WEIGHT


# --------------------------------------------------------------------------
# Single operator turn
# --------------------------------------------------------------------------


def test_single_operator_turn_emits_one_sample() -> None:
    events = [_agent_invoke(), _op("do the thing"), _agent_output()]
    samples = normalize_session(events, session_id="S1")

    assert len(samples) == 1
    sample = samples[0]
    assert sample.session_id == "S1"

    # [system, agent.invoke(prefix), target]  -- events AFTER the operator
    # message are not part of that sample's prefix.
    assert [m.role for m in sample.messages] == ["system", "assistant", "operator"]

    system, prefix_agent, target = sample.messages
    assert system.role == "system"
    assert system.content == SYSTEM_PROMPT
    assert system.loss_weight == INACTIVE_WEIGHT
    assert prefix_agent.loss_weight == INACTIVE_WEIGHT

    # Target is the last message, weight 1.0.
    assert sample.target_index == len(sample.messages) - 1
    assert target is sample.messages[sample.target_index]
    assert target.role == "operator"
    assert target.content == "do the thing"
    assert target.loss_weight == TARGET_OPERATOR_WEIGHT


# --------------------------------------------------------------------------
# Multi operator turn -- sample count, prefix growth, prior-vs-target weights
# --------------------------------------------------------------------------


def _multi_turn_session() -> list[SessionEvent]:
    return [
        _op("first instruction"),  # op 1
        _agent_invoke(),
        _agent_output(),
        _tool_call("read_file"),
        _tool_result("read_file"),
        _op("second instruction"),  # op 2
        _agent_invoke(),
        _op("[SELFFORK:DONE]"),  # op 3
    ]


def test_multi_operator_turn_emits_one_sample_per_operator_message() -> None:
    samples = normalize_session(_multi_turn_session(), session_id="S2")
    assert len(samples) == 3


def test_multi_operator_prefix_grows_monotonically() -> None:
    samples = normalize_session(_multi_turn_session(), session_id="S2")
    lengths = [len(s.messages) for s in samples]
    # system+target(1) ; system+5prefix+target(7) ; system+7prefix+target(9)
    assert lengths == [2, 7, 9]
    assert lengths == sorted(lengths)


def test_multi_operator_target_always_last_and_weight_one() -> None:
    samples = normalize_session(_multi_turn_session(), session_id="S2")
    targets = ["first instruction", "second instruction", "[SELFFORK:DONE]"]
    for sample, expected in zip(samples, targets, strict=True):
        target = sample.messages[sample.target_index]
        assert sample.target_index == len(sample.messages) - 1
        assert target.role == "operator"
        assert target.content == expected
        assert target.loss_weight == TARGET_OPERATOR_WEIGHT


def test_prior_operator_messages_in_prefix_weighted_point_three() -> None:
    samples = normalize_session(_multi_turn_session(), session_id="S2")

    # Sample 0 has no prior operator message in its (empty) prefix.
    prefix0 = samples[0].messages[1:-1]
    assert all(m.role != "operator" for m in prefix0)

    # Sample 1's prefix contains op 1 as a PRIOR operator message at 0.3.
    prefix1 = samples[1].messages[1:-1]
    prior_ops_1 = [m for m in prefix1 if m.role == "operator"]
    assert [m.content for m in prior_ops_1] == ["first instruction"]
    assert all(m.loss_weight == PRIOR_OPERATOR_WEIGHT for m in prior_ops_1)

    # Sample 2's prefix contains op 1 + op 2, both prior at 0.3.
    prefix2 = samples[2].messages[1:-1]
    prior_ops_2 = [m for m in prefix2 if m.role == "operator"]
    assert [m.content for m in prior_ops_2] == ["first instruction", "second instruction"]
    assert all(m.loss_weight == PRIOR_OPERATOR_WEIGHT for m in prior_ops_2)


def test_non_operator_prefix_messages_all_weight_zero() -> None:
    samples = normalize_session(_multi_turn_session(), session_id="S2")
    for sample in samples:
        for message in sample.messages:
            if message.role != "operator":
                assert message.loss_weight == INACTIVE_WEIGHT


def test_full_loss_mask_of_final_sample() -> None:
    # The richest sample (last operator turn) exercises every message kind.
    sample = normalize_session(_multi_turn_session(), session_id="S2")[-1]
    roles_weights = [(m.role, m.loss_weight) for m in sample.messages]
    assert roles_weights == [
        ("system", 0.0),
        ("operator", 0.3),  # op 1 (prior)
        ("assistant", 0.0),  # agent.invoke
        ("assistant", 0.0),  # agent.output
        ("tool", 0.0),  # tool.call
        ("tool", 0.0),  # tool.result
        ("operator", 0.3),  # op 2 (prior)
        ("assistant", 0.0),  # agent.invoke
        ("operator", 1.0),  # op 3 (target)
    ]


# --------------------------------------------------------------------------
# Zero-operator session
# --------------------------------------------------------------------------


def test_zero_operator_session_yields_no_samples() -> None:
    events = [_agent_invoke(), _agent_output(), _tool_call("x"), _tool_result("x"), _lifecycle()]
    assert normalize_session(events, session_id="S3") == []


def test_empty_session_yields_no_samples() -> None:
    assert normalize_session([], session_id="S4") == []


# --------------------------------------------------------------------------
# Content extraction + custom system prompt
# --------------------------------------------------------------------------


def test_tool_call_content_renders_name_and_args() -> None:
    message = event_to_message(_tool_call("read_file"))
    assert message.content.startswith("read_file")
    assert "a.py" in message.content


def test_tool_result_content_renders_status_when_no_text() -> None:
    message = event_to_message(_tool_result("read_file"))
    assert message.content == "read_file -> ok"


def test_agent_output_without_text_falls_back_to_category() -> None:
    # SelfFork's own audit stores only char counts for agent.output, no
    # transcript -- content degrades to a stable non-empty descriptor.
    message = event_to_message(_agent_output())
    assert message.content == "agent.output"


def test_custom_system_prompt_is_honoured() -> None:
    samples = normalize_session([_op("hi")], session_id="S5", system_prompt="CUSTOM")
    assert samples[0].messages[0].content == "CUSTOM"


# --------------------------------------------------------------------------
# audit_reader glue (dependency-free / structural)
# --------------------------------------------------------------------------


class _FakeRawAuditEvent:
    """Duck-types ``selffork_shared.audit_reader.RawAuditEvent`` (category +
    payload) without importing it, exercising the structural glue path.
    """

    def __init__(self, category: str, payload: Mapping[str, object]) -> None:
        self.category = category
        self.payload = payload


def test_session_event_from_mapping_reads_category_and_payload() -> None:
    event = session_event_from_mapping({"category": "selffork_jr.reply", "payload": {"text": "yo"}})
    assert event.category == "selffork_jr.reply"
    assert event.payload == {"text": "yo"}


def test_session_event_from_mapping_degrades_on_missing_fields() -> None:
    event = session_event_from_mapping({})
    assert event.category == ""
    assert event.payload == {}


def test_session_events_from_audit_adapts_duck_typed_events() -> None:
    raw = [
        _FakeRawAuditEvent("agent.invoke", {"round": 0}),
        _FakeRawAuditEvent("selffork_jr.reply", {"text": "hello"}),
    ]
    events = session_events_from_audit(raw)
    assert [e.category for e in events] == ["agent.invoke", "selffork_jr.reply"]
    assert isinstance(events[0], SessionEvent)


def test_normalize_from_audit_end_to_end() -> None:
    raw = [
        _FakeRawAuditEvent("selffork_jr.reply", {"text": "one"}),
        _FakeRawAuditEvent("agent.invoke", {"round": 0}),
        _FakeRawAuditEvent("selffork_jr.reply", {"text": "two"}),
    ]
    samples = normalize_from_audit(raw, session_id="AUDIT")
    assert len(samples) == 2
    assert [s.session_id for s in samples] == ["AUDIT", "AUDIT"]
    assert samples[-1].messages[samples[-1].target_index] == ChatMessage(
        role="operator",
        content="two",
        loss_weight=TARGET_OPERATOR_WEIGHT,
    )
