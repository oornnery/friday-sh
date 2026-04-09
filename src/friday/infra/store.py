"""TOML config file helpers for persistent Friday settings."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from friday.domain.models import AgentMode
from friday.infra.config import FridaySettings

__all__ = ['ConfigFileStore']


class ConfigFileStore:
    """Read and update the user config file while preserving unrelated keys."""

    def __init__(self, settings: FridaySettings) -> None:
        self.settings = settings
        self.path = settings.config_dir / 'config.toml'

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        return tomllib.loads(self.path.read_text(encoding='utf-8'))

    def write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(_dump_toml(payload).rstrip() + '\n', encoding='utf-8')

    def set_default_model(self, model: str) -> None:
        payload = self.read()
        payload['default_model'] = model
        self.write(payload)

    def set_default_mode(self, mode: AgentMode) -> None:
        payload = self.read()
        payload['default_mode'] = mode.value
        self.write(payload)


def _dump_toml(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    array_tables: list[tuple[str, list[dict[str, Any]]]] = []

    for key, value in payload.items():
        if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            array_tables.append((key, value))
            continue
        lines.extend(_render_value(key, value))

    for key, items in array_tables:
        for item in items:
            lines.append(f'[[{key}]]')
            for child_key, child_value in item.items():
                lines.extend(_render_value(child_key, child_value))
            lines.append('')

    return '\n'.join(lines).rstrip()


def _render_value(key: str, value: Any) -> list[str]:
    if isinstance(value, dict):
        lines = [f'[{key}]']
        for child_key, child_value in value.items():
            lines.extend(_render_value(child_key, child_value))
        lines.append('')
        return lines
    return [f'{key} = {_render_scalar(value)}']


def _render_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, Path):
        return _quote(str(value))
    if isinstance(value, list):
        return '[' + ', '.join(_render_scalar(item) for item in value) + ']'
    if value is None:
        return '""'
    return _quote(str(value))


def _quote(value: str) -> str:
    escaped = value.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{escaped}"'
