"""Session persistence backed by JSON files."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter

from friday.domain.permissions import clip

__all__ = [
    'JsonSessionStore',
    'SessionData',
    'SessionEnvelope',
    'SessionMeta',
    'extract_last_user_message',
    'extract_turn_count',
]


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


class SessionMeta(BaseModel):
    """Lightweight session metadata for listing and resuming."""

    id: str
    created_at: str
    model: str = ''
    mode: str = 'auto'
    turn_count: int = 0
    last_user_message: str = ''
    workspace_key: str = ''


class SessionEnvelope(BaseModel):
    """Serialized session payload stored on disk."""

    schema_version: int = 2
    meta: SessionMeta
    messages: list[dict[str, Any]] = Field(default_factory=list)


class SessionData(BaseModel):
    """Validated session data used at runtime."""

    meta: SessionMeta
    messages: list[ModelMessage] = Field(default_factory=list)


class JsonSessionStore:
    """Stores sessions as JSON files in a directory."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        return self.root / f'{session_id}.json'

    def save(self, data: SessionData) -> None:
        envelope = SessionEnvelope(
            meta=data.meta,
            messages=ModelMessagesTypeAdapter.dump_python(data.messages, mode='json'),
        )
        self._path(data.meta.id).write_text(
            envelope.model_dump_json(indent=2),
            encoding='utf-8',
        )

    def load(self, session_id: str) -> SessionData:
        path = self._path(session_id)
        if not path.exists():
            msg = f'Session not found: {session_id}'
            raise FileNotFoundError(msg)

        raw = json.loads(path.read_text(encoding='utf-8'))
        if 'schema_version' in raw:
            envelope = SessionEnvelope.model_validate(raw)
        else:
            envelope = SessionEnvelope(
                schema_version=1,
                meta=SessionMeta.model_validate(raw['meta']),
                messages=raw.get('messages', []),
            )

        messages = ModelMessagesTypeAdapter.validate_python(envelope.messages)
        return SessionData(meta=envelope.meta, messages=messages)

    def latest_id(self) -> str | None:
        files = sorted(self.root.glob('*.json'), key=lambda path: path.stat().st_mtime)
        return files[-1].stem if files else None

    def list_sessions(self, limit: int = 20) -> list[SessionMeta]:
        files = sorted(
            self.root.glob('*.json'),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        sessions: list[SessionMeta] = []
        for file_path in files[:limit]:
            try:
                raw = json.loads(file_path.read_text(encoding='utf-8'))
                meta = raw['meta'] if 'meta' in raw else {}
                sessions.append(SessionMeta.model_validate(meta))
            except (json.JSONDecodeError, KeyError):
                continue
        return sessions

    def delete(self, session_id: str) -> bool:
        path = self._path(session_id)
        if not path.exists():
            return False
        path.unlink()
        return True


def extract_last_user_message(messages: list[dict[str, Any]]) -> str:
    """Extract the last user message text from serialized message history."""
    for message in reversed(messages):
        if message.get('kind') != 'request':
            continue
        for part in reversed(message.get('parts', [])):
            if part.get('part_kind') == 'user-prompt':
                return clip(part.get('content', ''), 80)
    return ''


def extract_turn_count(messages: list[dict[str, Any]]) -> int:
    """Count only top-level user prompts, ignoring tool-return requests."""
    count = 0
    for message in messages:
        if message.get('kind') != 'request':
            continue
        if any(part.get('part_kind') == 'user-prompt' for part in message.get('parts', [])):
            count += 1
    return count
