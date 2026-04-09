"""Interactive picker — reusable prompt_toolkit selector with search."""

from __future__ import annotations

import shutil

from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl

from friday.cli.theme import PT_STYLE

_HEADER_LINES = 4


class InteractivePicker:
    """Arrow-key list picker with fuzzy search, scroll, and active indicator.

    Usage:
        result = pick(['a', 'b', 'c'], current='b', title='Pick one')
    """

    def __init__(
        self,
        items: list[str],
        current: str = '',
        title: str = 'Select',
        max_visible: int = 0,
    ) -> None:
        self.all_items = items
        self.current = current
        self.title = title
        self.query = ''
        self.index = 0
        self.scroll_offset = 0
        self.result: str | None = None

        term_h = shutil.get_terminal_size().lines
        self.max_visible = max_visible or max(5, term_h - _HEADER_LINES - 3)

        self.filtered = list(self.all_items)
        self._set_initial_cursor()

    def _set_initial_cursor(self) -> None:
        """Put cursor on the current/active item."""
        for i, item in enumerate(self.filtered):
            if item == self.current:
                self.index = i
                break
        self._adjust_scroll()

    def _apply_filter(self) -> None:
        """Filter items by query (case-insensitive substring match)."""
        if not self.query:
            self.filtered = list(self.all_items)
        else:
            q = self.query.lower()
            self.filtered = [it for it in self.all_items if q in it.lower()]
        self.index = min(self.index, max(0, len(self.filtered) - 1))
        self.scroll_offset = 0
        self._adjust_scroll()

    def _adjust_scroll(self) -> None:
        if self.index < self.scroll_offset:
            self.scroll_offset = self.index
        elif self.index >= self.scroll_offset + self.max_visible:
            self.scroll_offset = self.index - self.max_visible + 1

    def _render(self) -> list[tuple[str, str]]:
        lines: list[tuple[str, str]] = []
        total = len(self.filtered)
        pos = self.index + 1 if total else 0

        # Title + counter
        lines.append(('class:title', f'  {self.title}'))
        lines.append(('class:hint', f'  ({pos}/{total})\n'))

        # Search bar
        if self.query:
            lines.append(('class:search', f'  / {self.query}'))
            lines.append(('class:search-cursor', '_\n'))
        else:
            lines.append(('class:hint', '  type to search, j/k move, enter select, esc cancel\n'))

        if not total:
            lines.append(('class:hint', '\n  no matches\n'))
            return lines

        # Scroll indicator top
        if self.scroll_offset > 0:
            lines.append(('class:hint', f'  ... {self.scroll_offset} more above\n'))
        else:
            lines.append(('', '\n'))

        # Visible items
        end = min(self.scroll_offset + self.max_visible, total)
        for i in range(self.scroll_offset, end):
            item = self.filtered[i]
            selected = i == self.index
            is_active = item == self.current

            if selected:
                pointer = '  > '
                style = 'class:pointer'
            else:
                pointer = '    '
                style = 'class:item'

            label = item
            if is_active:
                label += '  (active)'
                if not selected:
                    style = 'class:active'

            lines.append((style, f'{pointer}{label}\n'))

        # Scroll indicator bottom
        remaining = total - end
        if remaining > 0:
            lines.append(('class:hint', f'  ... {remaining} more below\n'))

        return lines

    def run(self) -> str | None:
        if not self.all_items:
            return None

        kb = KeyBindings()

        @kb.add('up')
        @kb.add('c-p')
        def _up(event) -> None:
            if self.filtered and self.index > 0:
                self.index -= 1
                self._adjust_scroll()

        @kb.add('down')
        @kb.add('c-n')
        def _down(event) -> None:
            if self.filtered and self.index < len(self.filtered) - 1:
                self.index += 1
                self._adjust_scroll()

        @kb.add('home')
        def _top(event) -> None:
            self.index = 0
            self._adjust_scroll()

        @kb.add('end')
        def _bottom(event) -> None:
            if self.filtered:
                self.index = len(self.filtered) - 1
                self._adjust_scroll()

        @kb.add('enter')
        def _select(event) -> None:
            if self.filtered:
                self.result = self.filtered[self.index]
            event.app.exit()

        @kb.add('escape')
        @kb.add('c-c')
        def _cancel(event) -> None:
            self.result = None
            event.app.exit()

        @kb.add('backspace')
        def _backspace(event) -> None:
            if self.query:
                self.query = self.query[:-1]
                self._apply_filter()

        @kb.add('c-u')
        def _clear_query(event) -> None:
            self.query = ''
            self._apply_filter()
            self._set_initial_cursor()

        # Catch any printable character for search
        @kb.add('<any>')
        def _char(event) -> None:
            char = event.data
            if char.isprintable() and len(char) == 1:
                self.query += char
                self._apply_filter()

        control = FormattedTextControl(self._render)
        window = Window(content=control, always_hide_cursor=True)

        app: Application[None] = Application(
            layout=Layout(HSplit([window])),
            key_bindings=kb,
            full_screen=False,
            style=PT_STYLE,
        )

        app.run()
        return self.result


def pick(
    items: list[str],
    current: str = '',
    title: str = 'Select',
) -> str | None:
    """Show an interactive picker with search. Returns selected item or None."""
    return InteractivePicker(items=items, current=current, title=title).run()
