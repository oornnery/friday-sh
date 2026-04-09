"""Interactive approval helpers for deferred tool execution."""

from __future__ import annotations

import json
from builtins import input as builtin_input

from pydantic_ai.messages import ToolCallPart
from rich.panel import Panel

from friday.cli.output import console
from friday.cli.theme import COLORS

__all__ = ['confirm_action', 'confirm_deferred_tool']


def confirm_action(title: str, description: str, detail: str = '') -> bool:
    """Prompt the user to approve a sensitive action."""
    content = description
    if detail:
        content += f'\n\n{detail}'

    console.print()
    console.print(
        Panel(
            content,
            title=f'[warning]{title}[/warning]',
            border_style=COLORS['warning'],
            padding=(0, 1),
        )
    )

    try:
        console.print('[muted]Allow? [y/N] [/muted]', end='')
        answer = builtin_input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        console.print('[error]Denied[/error]')
        return False

    approved = answer in {'y', 'yes'}
    console.print('[success]Approved[/success]' if approved else '[error]Denied[/error]')
    return approved


def confirm_deferred_tool(call: ToolCallPart) -> bool:
    """Render a deferred tool call and ask the user to approve it."""
    detail = json.dumps(call.args_as_dict(), indent=2, ensure_ascii=False, sort_keys=True)
    return confirm_action(
        title='Confirm',
        description=f'[warning]{call.tool_name}[/warning]: execute deferred tool call',
        detail=detail,
    )
