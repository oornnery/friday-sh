"""Command metadata shared by the CLI, REPL, and shell integration."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
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
    ResourceCommand('model', 'Select or show models', ('show',)),
    ResourceCommand('mode', 'Select or show modes', ('show',)),
    ResourceCommand(
        'session',
        'Manage saved sessions',
        ('show', 'resume', 'new', 'delete'),
    ),
    ResourceCommand('setting', 'Read or update settings', ('show',)),
    ResourceCommand(
        'memory',
        'Inspect and manage shared memory',
        ('show', 'search', 'add', 'delete'),
    ),
)

REPL_COMMANDS: dict[str, str] = {
    '/help': 'Show available commands',
    '/model': 'Model picker (or /model show | /model <name>)',
    '/mode': 'Mode picker (or /mode show | /mode <name>)',
    '/session': 'Session picker (or /session show | resume | new | delete)',
    '/setting': 'Show settings (or /setting <key> | /setting <key>=<value>)',
    '/memory': 'List memories (or /memory show | search | add | delete)',
    '/debug': 'Toggle debug (or /debug on | off | show)',
    '/clear': 'Clear conversation',
    '/quit': 'Exit Friday',
    '/exit': 'Exit Friday',
}


def resource_names() -> tuple[str, ...]:
    return tuple(resource.name for resource in RESOURCE_COMMANDS)


def resource_subcommands(name: str) -> tuple[str, ...]:
    for resource in RESOURCE_COMMANDS:
        if resource.name == name:
            return resource.subcommands
    return ()
