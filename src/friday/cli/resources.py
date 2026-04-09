"""Shared resource actions used by the CLI and the interactive REPL."""

from __future__ import annotations

import sys
from dataclasses import dataclass

from rich.table import Table

from friday.cli.models import fetch_models
from friday.cli.output import console, print_error, print_info
from friday.cli.picker import pick
from friday.domain.models import AgentMode
from friday.infra.config import FridaySettings
from friday.infra.memory import MemoryRecord, MemorySearchResult, MemoryStore
from friday.infra.sessions import JsonSessionStore, SessionMeta
from friday.infra.store import ConfigFileStore

__all__ = [
    'interactive_memory_pick',
    'interactive_mode_pick',
    'interactive_model_pick',
    'interactive_session_pick',
    'list_mode_names',
    'print_memory_search_results',
    'print_memory_table',
    'print_session_table',
    'set_default_mode',
    'set_default_model',
]


@dataclass(frozen=True, slots=True)
class SessionChoice:
    id: str
    label: str


@dataclass(frozen=True, slots=True)
class MemoryChoice:
    id: str
    label: str


def list_mode_names() -> list[str]:
    return [mode.value for mode in AgentMode]


def interactive_model_pick(settings: FridaySettings, current: str = '') -> str | None:
    if not _is_tty():
        print_error('Select model requires an interactive terminal.')
        return None
    models = fetch_models(settings)
    if not models:
        print_error('No models found. Set API keys in .env or start Ollama.')
        return None
    if current and current not in models:
        models.insert(0, current)
    return pick(items=models, current=current, title='Select model')


def interactive_mode_pick(current: str = '') -> str | None:
    return _interactive_pick(list_mode_names(), current=current, title='Select mode')


def interactive_session_pick(store: JsonSessionStore, current: str = '') -> str | None:
    if not _is_tty():
        print_error('Select session requires an interactive terminal.')
        return None
    sessions = store.list_sessions(limit=20)
    if not sessions:
        print_info('No saved sessions.')
        return None

    choices = [
        SessionChoice(
            id=session.id,
            label=f'{session.id}  ({session.turn_count}t) {session.last_user_message or ""}',
        )
        for session in sessions
    ]
    selected = _interactive_pick(
        [choice.label for choice in choices],
        current=next((choice.label for choice in choices if choice.id == current), ''),
        title='Select session',
    )
    if selected is None:
        return None
    for choice in choices:
        if choice.label == selected:
            return choice.id
    return None


def interactive_memory_pick(
    store: MemoryStore,
    *,
    workspace_key: str,
    current: str = '',
) -> str | None:
    if not _is_tty():
        print_error('Select memory requires an interactive terminal.')
        return None

    records = store.list_memories(workspace_key=workspace_key, limit=30)
    if not records:
        print_info('No saved memories.')
        return None

    choices = [
        MemoryChoice(
            id=record.id,
            label=(f'{record.id}  [{record.scope.value}/{record.kind.value}] {record.text}'),
        )
        for record in records
    ]
    selected = _interactive_pick(
        [choice.label for choice in choices],
        current=next((choice.label for choice in choices if choice.id == current), ''),
        title='Select memory',
    )
    if selected is None:
        return None
    for choice in choices:
        if choice.label == selected:
            return choice.id
    return None


def print_session_table(sessions: list[SessionMeta], active_id: str = '') -> None:
    if not sessions:
        print_info('No saved sessions.')
        return

    table = Table(title='Sessions', show_lines=False)
    table.add_column('ID', style='info')
    table.add_column('Created', style='muted')
    table.add_column('Model', style='muted')
    table.add_column('Turns')
    table.add_column('Last message', max_width=48)
    for session in sessions:
        active = ' *' if active_id and session.id == active_id else ''
        table.add_row(
            f'{session.id}{active}',
            session.created_at[:19],
            session.model or '-',
            str(session.turn_count),
            session.last_user_message or '-',
        )
    console.print(table)


def print_memory_table(records: list[MemoryRecord]) -> None:
    if not records:
        print_info('No saved memories.')
        return

    table = Table(title='Shared Memories', show_lines=False)
    table.add_column('ID', style='info')
    table.add_column('Scope', style='muted')
    table.add_column('Kind', style='muted')
    table.add_column('Pinned')
    table.add_column('Text', max_width=72)
    for record in records:
        table.add_row(
            record.id,
            record.scope.value,
            record.kind.value,
            'yes' if record.pinned else 'no',
            record.text,
        )
    console.print(table)


def print_memory_search_results(results: list[MemorySearchResult]) -> None:
    if not results:
        print_info('No memory matches.')
        return

    table = Table(title='Memory Search', show_lines=False)
    table.add_column('Source', style='info')
    table.add_column('ID', style='muted')
    table.add_column('Details', style='muted')
    table.add_column('Snippet', max_width=72)
    for result in results:
        if result.source == 'memory':
            scope = result.scope.value if result.scope is not None else '-'
            kind = result.kind.value if result.kind is not None else '-'
            details = f'{scope}/{kind}'
        else:
            details = f'session={result.session_id}'
        table.add_row(
            result.source,
            result.id,
            details,
            result.snippet,
        )
    console.print(table)


def set_default_model(settings: FridaySettings, model: str) -> None:
    ConfigFileStore(settings).set_default_model(model)
    print_info(f'Default model updated: {model}')


def set_default_mode(settings: FridaySettings, mode: AgentMode) -> None:
    ConfigFileStore(settings).set_default_mode(mode)
    print_info(f'Default mode updated: {mode.value}')


def _interactive_pick(items: list[str], *, current: str, title: str) -> str | None:
    if not _is_tty():
        print_error(f'{title} requires an interactive terminal.')
        return None
    return pick(items=items, current=current, title=title)


def _is_tty() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()
