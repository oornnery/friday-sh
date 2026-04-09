"""Rich console output — markdown rendering and streaming display."""

from __future__ import annotations

from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from friday.cli.theme import RICH_THEME

console = Console(theme=RICH_THEME)


def build_response_panel(text: str) -> Panel:
    """Build the styled panel used for visible agent responses."""
    return Panel(
        Markdown(text),
        box=box.MARKDOWN,
        border_style='response.border',
        style='response',
        padding=(0, 1),
    )


def print_markdown(text: str) -> None:
    """Render markdown text to the console."""
    console.print()
    console.print(build_response_panel(text))
    console.print()


def print_info(text: str) -> None:
    console.print(f'[info]{text}[/info]')


def print_error(text: str) -> None:
    console.print(f'[error]{text}[/error]')


def print_success(text: str) -> None:
    console.print(f'[success]{text}[/success]')


def print_run_summary(text: str) -> None:
    """Render a compact post-response summary."""
    console.print(f'[muted]{text}[/muted]')


def print_tool_call(name: str, args: str) -> None:
    """Show a tool call in muted style."""
    console.print(f'[muted]  > {name}({args})[/muted]')
