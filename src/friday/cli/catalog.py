"""Command metadata shared by the CLI, REPL, and shell integration."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    'LEGACY_COMMAND_SUGGESTIONS',
    'REPL_COMMANDS',
    'RESOURCE_COMMANDS',
    'ResourceCommand',
    'resource_names',
    'resource_subcommands',
]


@dataclass(frozen=True, slots=True)
class ResourceCommand:
    name: str
    description: str
    subcommands: tuple[str, ...]


RESOURCE_COMMANDS: tuple[ResourceCommand, ...] = (
    ResourceCommand('models', 'List and select models', ('list', 'set')),
    ResourceCommand('modes', 'List and select modes', ('list', 'set')),
    ResourceCommand(
        'sessions',
        'List and manage saved sessions',
        ('list', 'set', 'delete', 'new'),
    ),
    ResourceCommand('settings', 'Read effective configuration', ('list', 'get')),
    ResourceCommand(
        'memories',
        'Inspect and manage shared memory',
        ('list', 'search', 'set', 'get', 'delete'),
    ),
)

REPL_COMMANDS: dict[str, str] = {
    '/help': 'Show available commands',
    '/debug': 'Toggle verbose logging and stack traces',
    '/models': 'List or set models',
    '/modes': 'List or set modes',
    '/sessions': 'List, set, delete, or create sessions',
    '/settings': 'Read settings',
    '/memories': 'List, search, create, inspect, or delete memories',
    '/clear': 'Clear conversation',
    '/quit': 'Exit Friday',
    '/exit': 'Exit Friday',
}

LEGACY_COMMAND_SUGGESTIONS: dict[str, str] = {
    'session': 'sessions',
    'model': 'models',
    'mode': 'modes',
    'config': 'settings',
    '/session': '/sessions',
    '/model': '/models',
    '/mode': '/modes',
    '/config': '/settings',
}


def resource_names() -> tuple[str, ...]:
    return tuple(resource.name for resource in RESOURCE_COMMANDS)


def resource_subcommands(name: str) -> tuple[str, ...]:
    for resource in RESOURCE_COMMANDS:
        if resource.name == name:
            return resource.subcommands
    return ()
