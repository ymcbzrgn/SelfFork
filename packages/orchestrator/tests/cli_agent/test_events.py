"""Unit tests for :mod:`selffork_orchestrator.cli_agent.events`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from selffork_orchestrator.cli_agent.events import (
    AssistantMessageEvent,
    DoneEvent,
    ErrorEvent,
    ExitEvent,
    StartedEvent,
    ToolCallEvent,
    ToolResultEvent,
    agent_event_adapter,
)


class TestEventConstruction:
    def test_started_default_type(self) -> None:
        ev = StartedEvent(session_id="sess1")
        assert ev.type == "started"
        assert ev.session_id == "sess1"

    def test_assistant_message_requires_text(self) -> None:
        ev = AssistantMessageEvent(text="hi")
        assert ev.type == "assistant_message"
        assert ev.text == "hi"

    def test_tool_call_default_args(self) -> None:
        ev = ToolCallEvent(tool_name="bash")
        assert ev.args == {}
        assert ev.call_id is None

    def test_tool_result_defaults(self) -> None:
        ev = ToolResultEvent()
        assert ev.tool_name is None
        assert ev.success is True
        assert ev.output is None

    def test_error_requires_message(self) -> None:
        ev = ErrorEvent(message="boom")
        assert ev.message == "boom"

    def test_done_optional_summary(self) -> None:
        ev = DoneEvent()
        assert ev.summary is None

    def test_exit_requires_code(self) -> None:
        ev = ExitEvent(code=0)
        assert ev.code == 0


class TestAdapterDiscrimination:
    @pytest.mark.parametrize(
        ("data", "expected_type"),
        [
            ({"type": "started"}, StartedEvent),
            ({"type": "started", "session_id": "abc"}, StartedEvent),
            ({"type": "assistant_message", "text": "hi"}, AssistantMessageEvent),
            ({"type": "tool_call", "tool_name": "bash"}, ToolCallEvent),
            ({"type": "tool_result"}, ToolResultEvent),
            ({"type": "error", "message": "bad"}, ErrorEvent),
            ({"type": "done"}, DoneEvent),
            ({"type": "done", "summary": "ok"}, DoneEvent),
            ({"type": "exit", "code": 0}, ExitEvent),
        ],
    )
    def test_validates_to_correct_subclass(
        self,
        data: dict[str, object],
        expected_type: type,
    ) -> None:
        ev = agent_event_adapter.validate_python(data)
        assert isinstance(ev, expected_type)

    def test_rejects_unknown_type(self) -> None:
        with pytest.raises(ValidationError):
            agent_event_adapter.validate_python({"type": "totally_unknown"})

    def test_extra_fields_preserved(self) -> None:
        ev = agent_event_adapter.validate_python(
            {"type": "started", "session_id": "s1", "backend_specific": 42},
        )
        # Pydantic stores extras in ``__pydantic_extra__`` when extra='allow'.
        dumped = ev.model_dump()
        assert dumped["backend_specific"] == 42
