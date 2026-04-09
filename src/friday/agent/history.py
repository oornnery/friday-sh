"""Message history processors for keeping agent context bounded."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from friday.domain.permissions import clip

__all__ = ['build_history_processor']

_OLD_TEXT_LIMIT = 240
_OLD_TOOL_LIMIT = 180
_RECENT_TURNS = 2


def build_history_processor(
    request_limit: int,
) -> Callable[[list[ModelMessage]], list[ModelMessage]]:
    """Keep only the most recent user turns and following messages."""

    def keep_recent_requests(messages: list[ModelMessage]) -> list[ModelMessage]:
        turn_indexes = [
            index
            for index, message in enumerate(messages)
            if isinstance(message, ModelRequest)
            and any(isinstance(part, UserPromptPart) for part in message.parts)
        ]
        if len(turn_indexes) > request_limit:
            start = turn_indexes[-request_limit]
            selected = messages[start:]
        else:
            selected = messages
        selected_turns = [
            index
            for index, message in enumerate(selected)
            if isinstance(message, ModelRequest)
            and any(isinstance(part, UserPromptPart) for part in message.parts)
        ]
        if len(selected_turns) <= _RECENT_TURNS:
            return selected

        compact_until = selected_turns[-_RECENT_TURNS]
        seen_read_paths: set[str] = set()
        dropped_tool_calls: set[str] = set()
        compacted: list[ModelMessage] = []

        for index, message in enumerate(selected):
            if index >= compact_until:
                compacted.append(message)
                continue

            if isinstance(message, ModelResponse):
                new_parts = []
                for part in message.parts:
                    if isinstance(part, ToolCallPart) and part.tool_name == 'read_file':
                        path = str(part.args_as_dict().get('path', ''))
                        if path and path in seen_read_paths:
                            dropped_tool_calls.add(part.tool_call_id)
                            continue
                        if path:
                            seen_read_paths.add(path)
                        new_parts.append(part)
                        continue

                    if isinstance(part, TextPart):
                        new_parts.append(replace(part, content=clip(part.content, _OLD_TEXT_LIMIT)))
                        continue

                    new_parts.append(part)

                if new_parts:
                    compacted.append(replace(message, parts=tuple(new_parts)))
                continue

            if isinstance(message, ModelRequest):
                new_parts = []
                for part in message.parts:
                    if isinstance(part, ToolReturnPart):
                        if part.tool_call_id in dropped_tool_calls:
                            continue
                        if isinstance(part.content, str):
                            new_parts.append(
                                replace(part, content=clip(part.content, _OLD_TOOL_LIMIT))
                            )
                            continue
                    if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                        new_parts.append(replace(part, content=clip(part.content, _OLD_TEXT_LIMIT)))
                        continue
                    new_parts.append(part)

                if new_parts:
                    compacted.append(replace(message, parts=tuple(new_parts)))
                continue

            compacted.append(message)

        return compacted

    return keep_recent_requests
