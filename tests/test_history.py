"""Tests for history trimming."""

from __future__ import annotations

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from friday.agent.history import build_history_processor


def test_history_processor_keeps_full_tool_loop_for_single_user_turn() -> None:
    messages = [
        ModelRequest(parts=[UserPromptPart('fix it')]),
        ModelResponse(parts=[ToolCallPart('read_file', {'path': 'a.py'}, tool_call_id='call-1')]),
        ModelRequest(parts=[ToolReturnPart('read_file', 'ok', tool_call_id='call-1')]),
        ModelResponse(parts=[TextPart('done')]),
    ]

    processed = build_history_processor(1)(messages)

    assert processed == messages


def test_history_processor_trims_by_user_turn_boundary() -> None:
    messages = [
        ModelRequest(parts=[UserPromptPart('first turn')]),
        ModelResponse(parts=[TextPart('first answer')]),
        ModelRequest(parts=[UserPromptPart('second turn')]),
        ModelResponse(parts=[TextPart('second answer')]),
    ]

    processed = build_history_processor(1)(messages)

    assert processed == messages[2:]


def test_history_processor_deduplicates_old_read_file_loops() -> None:
    messages = [
        ModelRequest(parts=[UserPromptPart('first turn')]),
        ModelResponse(parts=[ToolCallPart('read_file', {'path': 'a.py'}, tool_call_id='call-1')]),
        ModelRequest(parts=[ToolReturnPart('read_file', 'old content', tool_call_id='call-1')]),
        ModelResponse(parts=[TextPart('first answer')]),
        ModelRequest(parts=[UserPromptPart('second turn')]),
        ModelResponse(parts=[ToolCallPart('read_file', {'path': 'a.py'}, tool_call_id='call-2')]),
        ModelRequest(
            parts=[ToolReturnPart('read_file', 'duplicate content', tool_call_id='call-2')]
        ),
        ModelResponse(parts=[TextPart('second answer')]),
        ModelRequest(parts=[UserPromptPart('third turn')]),
        ModelResponse(parts=[TextPart('third answer')]),
        ModelRequest(parts=[UserPromptPart('fourth turn')]),
        ModelResponse(parts=[TextPart('fourth answer')]),
    ]

    processed = build_history_processor(4)(messages)

    tool_call_ids = [
        part.tool_call_id
        for message in processed
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ToolCallPart)
    ]
    tool_return_ids = [
        part.tool_call_id
        for message in processed
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    ]

    assert 'call-1' in tool_call_ids
    assert 'call-1' in tool_return_ids
    assert 'call-2' not in tool_call_ids
    assert 'call-2' not in tool_return_ids
