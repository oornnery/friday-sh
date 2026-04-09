"""Interactive approval helpers for deferred tool execution."""

from __future__ import annotations

import json
import sys
import termios
import tty

from pydantic_ai.messages import ToolCallPart
from rich.panel import Panel

from friday.cli.output import console
from friday.cli.theme import COLORS

__all__ = ['confirm_action', 'confirm_deferred_tool']

_UP = ('\x1b[A', 'k')
_DOWN = ('\x1b[B', 'j')
_ENTER = ('\r', '\n')


def confirm_action(title: str, description: str, detail: str = '') -> bool:
    """Prompt the user to approve a sensitive action with arrow-key selector."""
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

    if not sys.stdin.isatty():
        return False

    # Flush rich output before taking over stdout
    console.file.flush()
    return _confirm_selector()


def _confirm_selector() -> bool:
    """Arrow-key Yes/No selector using raw terminal reads.

    Uses only sys.stdout (no rich) to avoid cursor position conflicts.
    """
    selected = 0  # 0=Yes, 1=No
    _G = '\x1b[32m'  # green
    _D = '\x1b[90m'  # dim
    _R = '\x1b[0m'   # reset
    _HIDE = '\x1b[?25l'  # hide cursor
    _SHOW = '\x1b[?25h'  # show cursor
    _CLR = '\x1b[J'       # clear from cursor to end
    _UP2 = '\x1b[2A'      # move up 2 lines

    out = sys.stdout

    def draw() -> None:
        yes = f'{_G}  > Yes{_R}' if selected == 0 else f'{_D}    Yes{_R}'
        no = f'{_G}  > No{_R}' if selected == 1 else f'{_D}    No{_R}'
        out.write(f'{yes}\r\n{no}\r\n')
        out.flush()

    out.write(_HIDE)
    draw()

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        # Use os.read for unbuffered single-byte reads in raw mode
        import os as _os

        def _readch() -> str:
            return _os.read(fd, 1).decode('utf-8', errors='replace')

        while True:
            ch = _readch()
            if ch == '\x1b':
                seq = _readch() + _readch()
                key = ch + seq
            elif ch == '\x03':
                selected = 1
                break
            else:
                key = ch

            prev = selected
            if key in _UP and selected > 0:
                selected = 0
            elif key in _DOWN and selected < 1:
                selected = 1
            elif key in _ENTER:
                break
            else:
                continue

            if selected != prev:
                out.write(f'{_UP2}{_CLR}')
                draw()
    except (EOFError, KeyboardInterrupt):
        selected = 1
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, old)
        out.write(_SHOW)
        out.flush()

    # Clear the selector and print result via rich
    out.write(f'{_UP2}{_CLR}')
    out.flush()
    console.print('[success]Approved[/success]' if selected == 0 else '[error]Denied[/error]')
    return selected == 0


def confirm_deferred_tool(call: ToolCallPart) -> bool:
    """Render a deferred tool call and ask the user to approve it."""
    detail = json.dumps(call.args_as_dict(), indent=2, ensure_ascii=False, sort_keys=True)
    return confirm_action(
        title='Confirm',
        description=f'[warning]{call.tool_name}[/warning]: execute deferred tool call',
        detail=detail,
    )
