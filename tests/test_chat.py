"""Tests for REPL command handling."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from pydantic_ai.messages import ModelRequest, UserPromptPart

from friday.cli import chat as chat_module
from friday.domain.models import AgentMode
from friday.infra.config import FridaySettings
from friday.infra.memory import SQLiteMemoryStore
from friday.infra.sessions import JsonSessionStore, SessionData, SessionMeta


def _settings(tmp_path: Path) -> FridaySettings:
    settings = FridaySettings(
        default_model='anthropic:claude-sonnet-4-20250514',
        default_mode='auto',
        session_dir=tmp_path / 'sessions',
        config_dir=tmp_path / 'config',
    )
    settings.resolve_paths()
    return settings


def _state() -> chat_module.ChatState:
    return chat_module.ChatState(
        model='anthropic:claude-sonnet-4-20250514',
        mode=AgentMode.AUTO,
        session_meta=SessionMeta(
            id='session-1',
            created_at='2026-04-09T12:00:00',
            model='anthropic:claude-sonnet-4-20250514',
            mode='auto',
        ),
        message_history=[ModelRequest(parts=[UserPromptPart('hello')])],
        rebuild_agent=False,
    )


def _deps(tmp_path: Path, settings: FridaySettings) -> chat_module.AgentDeps:
    deps = chat_module.AgentDeps(
        workspace_root=tmp_path,
        context=SimpleNamespace(repo_root=tmp_path, render=lambda: 'workspace'),
        settings=settings,
        memory_store=SQLiteMemoryStore(settings.memory_db_path),
        session_id='session-1',
        interactive=True,
    )
    deps.memory.mode = AgentMode.AUTO
    deps.memory.task = 'carry-over'
    deps.memory.files = ['a.py']
    deps.memory.notes = ['note']
    deps.memory.entities = ['user_name=Fabio']
    deps.memory.decisions = ['use pytest']
    return deps


def test_models_set_updates_current_session_without_resetting_history(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = JsonSessionStore(settings.session_dir)
    state = _state()

    handled = chat_module._handle_slash(
        '/model mistral:mistral-large-latest',
        state,
        settings,
        store,
    )

    assert handled is True
    assert state.model == 'mistral:mistral-large-latest'
    assert state.rebuild_agent is True
    assert len(state.message_history) == 1


def test_modes_set_updates_current_session_without_resetting_history(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = JsonSessionStore(settings.session_dir)
    state = _state()

    handled = chat_module._handle_slash('/mode debug', state, settings, store)

    assert handled is True
    assert state.mode is AgentMode.DEBUG
    assert state.rebuild_agent is True
    assert len(state.message_history) == 1


def test_sessions_set_switches_current_session(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = JsonSessionStore(settings.session_dir)
    store.save(
        SessionData(
            meta=SessionMeta(
                id='session-2',
                created_at='2026-04-09T12:05:00',
                model='openai:gpt-4.1',
                mode='debug',
                turn_count=2,
                last_user_message='debug this',
            ),
            messages=[ModelRequest(parts=[UserPromptPart('debug this')])],
        )
    )
    state = _state()

    handled = chat_module._handle_slash('/session resume session-2', state, settings, store)

    assert handled is True
    assert state.session_meta.id == 'session-2'
    assert state.model == 'openai:gpt-4.1'
    assert state.mode is AgentMode.DEBUG
    assert state.rebuild_agent is True


def test_sessions_set_resets_working_memory_when_runtime_is_available(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = JsonSessionStore(settings.session_dir)
    store.save(
        SessionData(
            meta=SessionMeta(
                id='session-2',
                created_at='2026-04-09T12:05:00',
                model='openai:gpt-4.1',
                mode='debug',
                turn_count=2,
                last_user_message='debug this',
            ),
            messages=[ModelRequest(parts=[UserPromptPart('debug this')])],
        )
    )
    state = _state()
    deps = _deps(tmp_path, settings)

    handled = chat_module._handle_slash(
        '/session resume session-2',
        state,
        settings,
        store,
        deps=deps,
    )

    assert handled is True
    assert deps.session_id == 'session-2'
    assert deps.memory.task == ''
    assert deps.memory.files == []
    assert deps.memory.notes == []
    assert deps.memory.entities == []
    assert deps.memory.decisions == []


def test_clear_resets_working_memory(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = JsonSessionStore(settings.session_dir)
    state = _state()
    deps = _deps(tmp_path, settings)

    handled = chat_module._handle_slash('/clear', state, settings, store, deps=deps)

    assert handled is True
    assert deps.session_id == state.session_meta.id
    assert deps.memory.task == ''
    assert deps.memory.files == []
    assert deps.memory.notes == []
    assert deps.memory.entities == []
    assert deps.memory.decisions == []


def test_unknown_slash_command_returns_false(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = JsonSessionStore(settings.session_dir)
    state = _state()

    handled = chat_module._handle_slash('/nonexistent', state, settings, store)

    assert handled is False


def test_debug_toggle_updates_chat_state(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = JsonSessionStore(settings.session_dir)
    state = _state()
    toggled: list[bool] = []

    monkeypatch.setattr(
        chat_module,
        'set_debug_logging',
        lambda enabled: toggled.append(enabled) or enabled,
    )

    handled = chat_module._handle_slash('/debug on', state, settings, store)

    assert handled is True
    assert state.debug_enabled is True
    assert toggled == [True]


def test_debug_show_reports_current_state(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = JsonSessionStore(settings.session_dir)
    state = _state()
    state.debug_enabled = True
    info: list[str] = []
    monkeypatch.setattr(chat_module, 'print_info', info.append)

    handled = chat_module._handle_slash('/debug show', state, settings, store)

    assert handled is True
    assert info == ['Debug is on']
