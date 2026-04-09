"""Tests for visible console output renderables."""

from __future__ import annotations

from rich.panel import Panel

from friday.cli.output import build_response_panel


def test_build_response_panel_uses_dedicated_background_style() -> None:
    panel = build_response_panel('hello from friday')

    assert isinstance(panel, Panel)
    assert panel.style == 'response'
    assert panel.border_style == 'response.border'
