"""Tests for the single-shot ask command."""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

from friday.cli import ask as ask_module
from friday.infra.config import FridaySettings


class DummyExecuted:
    def __init__(self) -> None:
        self.reply = SimpleNamespace(markdown='hello from friday')


async def _execute_agent(*args, **kwargs) -> DummyExecuted:
    return DummyExecuted()


def test_run_ask_prints_summary_after_answer(monkeypatch, tmp_path: Path) -> None:
    rendered: list[str] = []
    summaries: list[str] = []

    monkeypatch.setattr(
        ask_module.WorkspaceContext,
        'discover',
        staticmethod(lambda: SimpleNamespace(repo_root=tmp_path)),
    )
    monkeypatch.setattr(ask_module.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(ask_module.sys, 'stdout', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(ask_module, 'create_agent', lambda mode, settings, context: object())
    monkeypatch.setattr(ask_module, 'execute_agent', _execute_agent)
    monkeypatch.setattr(
        ask_module,
        'format_turn_summary',
        lambda stats: (
            'model: anthropic:claude-sonnet-4-20250514  '
            'tokens: 17 total, 12 in, 5 out  cost: n/d'
        ),
    )
    monkeypatch.setattr(ask_module, 'Status', lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(ask_module, 'print_markdown', rendered.append)
    monkeypatch.setattr(ask_module, 'print_run_summary', summaries.append)

    settings = FridaySettings(
        default_model='anthropic:claude-sonnet-4-20250514',
        session_dir=tmp_path / 'sessions',
        config_dir=tmp_path / 'config',
    )
    settings.resolve_paths()

    ask_module.run_ask('hi', None, settings)

    assert rendered == ['hello from friday']
    assert summaries == [
        'model: anthropic:claude-sonnet-4-20250514  tokens: 17 total, 12 in, 5 out  cost: n/d'
    ]
