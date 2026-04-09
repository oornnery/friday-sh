"""Tests for interactive resource helpers."""

from __future__ import annotations

from types import SimpleNamespace

from friday.cli import resources as resources_module
from friday.infra.config import FridaySettings


def test_interactive_model_pick_requires_tty(monkeypatch, tmp_path) -> None:
    settings = FridaySettings(
        session_dir=tmp_path / 'sessions',
        config_dir=tmp_path / 'config',
    )
    settings.resolve_paths()
    errors: list[str] = []
    monkeypatch.setattr(resources_module.sys, 'stdin', SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr(resources_module.sys, 'stdout', SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr(resources_module, 'print_error', errors.append)

    selected = resources_module.interactive_model_pick(settings)

    assert selected is None
    assert errors == ['Select model requires an interactive terminal.']


def test_interactive_session_pick_requires_tty(monkeypatch, tmp_path) -> None:
    settings = FridaySettings(
        session_dir=tmp_path / 'sessions',
        config_dir=tmp_path / 'config',
    )
    settings.resolve_paths()
    errors: list[str] = []
    monkeypatch.setattr(resources_module.sys, 'stdin', SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr(resources_module.sys, 'stdout', SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr(resources_module, 'print_error', errors.append)

    selected = resources_module.interactive_session_pick(
        resources_module.JsonSessionStore(settings.session_dir)
    )

    assert selected is None
    assert errors == ['Select session requires an interactive terminal.']
