"""Unified theme — shared color palette for rich and prompt_toolkit."""

from __future__ import annotations

from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.styles import Style as PTStyle
from rich.theme import Theme as RichTheme

# ── Color palette ──────────────────────────────────────────────

COLORS = {
    'primary': '#5fafff',
    'success': '#00cc66',
    'warning': '#ffaf00',
    'error': '#ff5555',
    'muted': '#666666',
    'text': '#cccccc',
    'bg_response': '#101822',
    'bg_selected': '#1e1e2e',
    'bg_completion': '#1a1a2a',
    'border': '#3a3a4a',
    'response_border': '#2d5678',
}

# ── Rich theme (console output, panels, markdown) ─────────────

RICH_THEME = RichTheme(
    {
        'info': COLORS['primary'],
        'success': f'bold {COLORS["success"]}',
        'warning': COLORS['warning'],
        'error': f'bold {COLORS["error"]}',
        'muted': COLORS['muted'],
        'accent': f'bold {COLORS["primary"]}',
        'response': f'{COLORS["text"]} on {COLORS["bg_response"]}',
        'response.border': COLORS['response_border'],
    }
)

# ── prompt_toolkit style (picker, REPL, completions) ──────────

PT_STYLE = PTStyle.from_dict(
    {
        # Picker
        'title': f'bold {COLORS["primary"]}',
        'hint': f'{COLORS["muted"]} italic',
        'pointer': f'bold {COLORS["primary"]}',
        'item': '',
        'active': f'{COLORS["success"]} bold',
        # Search
        'search': f'bold {COLORS["warning"]}',
        'search-cursor': COLORS['warning'],
        # REPL prompt
        'prompt': f'bold {COLORS["primary"]}',
        'prompt-mode': f'{COLORS["success"]}',
        'prompt-model': COLORS['muted'],
        'prompt-sep': COLORS['muted'],
        # Completion dropdown
        'completion-menu': f'bg:{COLORS["bg_completion"]} {COLORS["text"]}',
        'completion-menu.completion': f'bg:{COLORS["bg_completion"]} {COLORS["text"]}',
        'completion-menu.completion.current': f'bg:{COLORS["primary"]} #000000 bold',
        'completion-menu.meta': f'bg:{COLORS["bg_completion"]} {COLORS["muted"]}',
        'completion-menu.meta.current': f'bg:{COLORS["primary"]} #000000',
        'scrollbar.background': COLORS['bg_completion'],
        'scrollbar.button': COLORS['border'],
    }
)


def make_prompt_message(mode: str, model: str, *, debug_enabled: bool = False) -> FormattedText:
    """Build the styled REPL prompt fragments."""
    short_model = model.split(':')[-1] if ':' in model else model
    parts: list[tuple[str, str]] = [
        ('class:prompt', 'friday'),
        ('class:prompt-sep', ':'),
        ('class:prompt-mode', mode),
        ('class:prompt-sep', f'({short_model})'),
    ]
    if debug_enabled:
        parts.append(('class:search', '[debug]'))
    parts.append(('class:prompt', '> '))
    return FormattedText(parts)
