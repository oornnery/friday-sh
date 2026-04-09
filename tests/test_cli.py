"""Tests for the unified CLI surface."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from friday.cli import app as app_module
from friday.cli.app import app
from friday.domain.models import MemoryKind, MemoryScope
from friday.infra.config import FridaySettings
from friday.infra.sessions import JsonSessionStore, SessionData, SessionMeta

runner = CliRunner()


def _settings(tmp_path: Path) -> FridaySettings:
    settings = FridaySettings(
        default_model='anthropic:claude-sonnet-4-20250514',
        default_mode='auto',
        session_dir=tmp_path / 'sessions',
        config_dir=tmp_path / 'config',
    )
    settings.resolve_paths()
    return settings


def test_help() -> None:
    result = runner.invoke(app, ['--help'])
    assert result.exit_code == 0
    assert 'Friday' in result.output


def test_settings_default_action_lists_effective_settings(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(app_module, '_get_settings', lambda: _settings(tmp_path))

    result = runner.invoke(app, ['setting'])

    assert result.exit_code == 0
    assert 'default_model' in result.output


def test_models_default_action_calls_list(monkeypatch, tmp_path: Path) -> None:
    calls: list[str | None] = []
    monkeypatch.setattr(app_module, '_get_settings', lambda: _settings(tmp_path))
    monkeypatch.setattr(
        app_module,
        'list_models',
        lambda settings, provider=None: calls.append(provider),
    )

    result = runner.invoke(app, ['model'])

    assert result.exit_code == 0
    assert calls == [None]


def test_unknown_command_shows_help() -> None:
    result = runner.invoke(app, ['nonexistent'])
    assert result.exit_code != 0


def test_sessions_default_action_lists_saved_sessions(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = JsonSessionStore(settings.session_dir)
    store.save(
        SessionData(
            meta=SessionMeta(
                id='abc123',
                created_at='2026-04-09T12:00:00',
                model=settings.default_model,
                mode='auto',
                turn_count=1,
                last_user_message='hello',
            ),
            messages=[],
        )
    )
    monkeypatch.setattr(app_module, '_get_settings', lambda: settings)

    result = runner.invoke(app, ['session'])

    assert result.exit_code == 0
    assert 'abc123' in result.output


def test_sessions_set_invokes_chat_with_session(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    called: list[str] = []
    monkeypatch.setattr(app_module, '_get_settings', lambda: settings)
    monkeypatch.setattr(
        app_module,
        'run_chat_with_session',
        lambda session_id, settings: called.append(session_id),
    )

    result = runner.invoke(app, ['session', 'resume', 'abc123'])

    assert result.exit_code == 0
    assert called == ['abc123']


def test_memories_set_and_list(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setattr(app_module, '_get_settings', lambda: settings)
    monkeypatch.setattr(
        app_module.WorkspaceContext,
        'discover',
        lambda: SimpleNamespace(repo_root=tmp_path),
    )

    set_result = runner.invoke(app, ['memory', 'add', 'remember Fabio'])
    list_result = runner.invoke(app, ['memory'])

    assert set_result.exit_code == 0
    assert 'Saved memory' in set_result.output
    assert list_result.exit_code == 0
    assert 'remember Fabio' in list_result.output


def test_memories_search_includes_chat_and_memory_hits(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setattr(app_module, '_get_settings', lambda: settings)
    monkeypatch.setattr(
        app_module.WorkspaceContext,
        'discover',
        lambda: SimpleNamespace(repo_root=tmp_path),
    )
    store = app_module.SQLiteMemoryStore(settings.memory_db_path)
    store.save_memory(
        'Fabio prefers concise summaries.',
        kind=MemoryKind.PREFERENCE,
        scope=MemoryScope.GLOBAL,
        workspace_key=tmp_path.as_posix(),
        pinned=True,
    )
    store.index_chat_turn(
        session_id='session-2',
        workspace_key=tmp_path.as_posix(),
        user_prompt='where do we show model cost?',
        assistant_reply='We show it at the end of the answer.',
    )

    result = runner.invoke(app, ['memory', 'search', 'Fabio'])

    assert result.exit_code == 0
    assert 'memory' in result.output
