"""Tests for shared memory storage and cross-chat retrieval."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from friday.agent.deps import AgentDeps
from friday.agent.memory import load_relevant_shared_memory, record_completed_turn
from friday.domain.models import AgentMode, MemoryKind, MemoryScope
from friday.infra.config import FridaySettings
from friday.infra.memory import SQLiteMemoryStore


def _settings(tmp_path: Path) -> FridaySettings:
    settings = FridaySettings(
        default_model='anthropic:claude-sonnet-4-20250514',
        default_mode='auto',
        session_dir=tmp_path / 'sessions',
        config_dir=tmp_path / 'config',
    )
    settings.resolve_paths()
    return settings


def _deps(tmp_path: Path, settings: FridaySettings, session_id: str = 'session-1') -> AgentDeps:
    deps = AgentDeps(
        workspace_root=tmp_path,
        context=SimpleNamespace(repo_root=tmp_path, render=lambda: 'workspace'),
        settings=settings,
        memory_store=SQLiteMemoryStore(settings.memory_db_path),
        session_id=session_id,
        interactive=False,
    )
    deps.memory.mode = AgentMode.AUTO
    return deps


def test_memory_store_prefers_repo_records_over_global(tmp_path: Path) -> None:
    store = SQLiteMemoryStore(tmp_path / 'memory.db')
    workspace_key = tmp_path.as_posix()

    store.save_memory(
        'Use ruff format in every repo.',
        kind=MemoryKind.WORKFLOW,
        scope=MemoryScope.GLOBAL,
        workspace_key=workspace_key,
        pinned=False,
    )
    store.save_memory(
        'Use ruff format for this repo.',
        kind=MemoryKind.DECISION,
        scope=MemoryScope.REPO,
        workspace_key=workspace_key,
        pinned=False,
    )

    results = store.search('ruff format', workspace_key=workspace_key, limit=5)

    assert results
    assert results[0].source == 'memory'
    assert results[0].scope is MemoryScope.REPO


def test_memory_store_upserts_duplicate_records(tmp_path: Path) -> None:
    store = SQLiteMemoryStore(tmp_path / 'memory.db')
    workspace_key = tmp_path.as_posix()

    first, created_first = store.save_memory(
        'User prefers concise answers.',
        kind=MemoryKind.PREFERENCE,
        scope=MemoryScope.GLOBAL,
        workspace_key=workspace_key,
        pinned=False,
    )
    second, created_second = store.save_memory(
        'User prefers concise answers.',
        kind=MemoryKind.PREFERENCE,
        scope=MemoryScope.GLOBAL,
        workspace_key=workspace_key,
        pinned=True,
    )

    listed = store.list_memories(workspace_key=workspace_key, limit=10)

    assert created_first is True
    assert created_second is False
    assert first.id == second.id
    assert len(listed) == 1
    assert listed[0].pinned is True


def test_record_completed_turn_indexes_cross_chat_chunks_and_prompt_snapshot(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    deps = _deps(tmp_path, settings, session_id='session-1')

    record_completed_turn(
        deps,
        user_prompt='where do we print model, tokens and cost?',
        reply_markdown='We print that summary at the end of the response.',
        record_chat_chunk=True,
    )

    other_session = _deps(tmp_path, settings, session_id='session-2')
    snapshot = load_relevant_shared_memory(other_session, 'model cost summary')

    assert snapshot.chats
    assert snapshot.chats[0].session_id == 'session-1'
    assert 'Assistant:' in snapshot.chats[0].snippet


def test_record_completed_turn_skips_sensitive_turns(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    deps = _deps(tmp_path, settings)

    record_completed_turn(
        deps,
        user_prompt='my api key is secret-123',
        reply_markdown='I will not store that.',
        record_chat_chunk=True,
    )

    assert deps.memory_store.list_memories(workspace_key=tmp_path.as_posix(), limit=10) == []
    assert deps.memory_store.search('secret-123', workspace_key=tmp_path.as_posix()) == []


def test_sticky_profile_memory_is_injected_cross_session(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    deps = _deps(tmp_path, settings, session_id='session-1')

    # Agent saves memory explicitly via save_memory tool (no regex auto-promotion)
    deps.memory_store.save_memory(
        'User name is Fabio.',
        kind=MemoryKind.PROFILE,
        scope=MemoryScope.GLOBAL,
        workspace_key=tmp_path.as_posix(),
        pinned=True,
    )

    other_session = _deps(tmp_path, settings, session_id='session-2')
    snapshot = load_relevant_shared_memory(other_session, 'qual o meu nome?')

    assert snapshot.records
    assert any('Fabio' in record.snippet for record in snapshot.records)
