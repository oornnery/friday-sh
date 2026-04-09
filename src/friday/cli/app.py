"""Friday CLI entrypoint."""

from __future__ import annotations

from typing import Annotated

import typer
from dotenv import load_dotenv

from friday.agent.context import WorkspaceContext
from friday.cli.ask import run_ask
from friday.cli.catalog import LEGACY_COMMAND_SUGGESTIONS
from friday.cli.chat import run_chat, run_chat_with_session
from friday.cli.models import list_models
from friday.cli.output import console, print_error, print_info
from friday.cli.resources import (
    interactive_memory_pick,
    interactive_mode_pick,
    interactive_model_pick,
    interactive_session_pick,
    list_mode_names,
    print_memory_search_results,
    print_memory_table,
    print_session_table,
    set_default_mode,
    set_default_model,
)
from friday.domain.models import AgentMode, MemoryKind, MemoryScope
from friday.infra.config import FridaySettings
from friday.infra.memory import SQLiteMemoryStore
from friday.infra.sessions import JsonSessionStore

load_dotenv()

app = typer.Typer(
    name='friday',
    help='Friday — LLM-powered shell agent',
    no_args_is_help=True,
    rich_markup_mode='rich',
)
models_app = typer.Typer(help='List and select models', invoke_without_command=True)
modes_app = typer.Typer(help='List and select modes', invoke_without_command=True)
sessions_app = typer.Typer(help='List and manage saved sessions', invoke_without_command=True)
settings_app = typer.Typer(help='Read effective configuration', invoke_without_command=True)
memories_app = typer.Typer(help='Inspect and manage shared memory', invoke_without_command=True)


def _get_settings() -> FridaySettings:
    settings = FridaySettings()
    settings.resolve_paths()
    return settings


def _parse_mode(value: str | None) -> AgentMode | None:
    if value is None:
        return None
    return AgentMode(value)


def _legacy_command(name: str) -> None:
    replacement = LEGACY_COMMAND_SUGGESTIONS[name]
    print_error(f'`friday {name}` no longer exists.')
    print_info(f'Use `friday {replacement}` instead.')
    raise typer.Exit(1)


def _memory_store(settings: FridaySettings) -> SQLiteMemoryStore:
    return SQLiteMemoryStore(settings.memory_db_path)


def _workspace_key() -> str:
    return WorkspaceContext.discover().repo_root.resolve().as_posix()


@app.command()
def ask(
    question: Annotated[str, typer.Argument(help='Question to ask Friday')],
    mode: Annotated[
        str | None,
        typer.Option('--mode', '-m', help='Force mode (auto/code/reader/write/debug)'),
    ] = None,
    model: Annotated[str | None, typer.Option('--model', help='Model override')] = None,
) -> None:
    """Ask a single question."""
    settings = _get_settings()
    if model:
        settings = settings.model_copy(update={'default_model': model})
    agent_mode = _parse_mode(mode) or settings.default_mode
    run_ask(question, agent_mode, settings)


@app.command()
def chat(
    mode: Annotated[
        str | None,
        typer.Option('--mode', '-m', help='Force mode (auto/code/reader/write/debug)'),
    ] = None,
    model: Annotated[str | None, typer.Option('--model', help='Model override')] = None,
) -> None:
    """Start an interactive chat session."""
    settings = _get_settings()
    if model:
        settings = settings.model_copy(update={'default_model': model})
    agent_mode = _parse_mode(mode) or settings.default_mode
    run_chat(agent_mode, settings)


@models_app.callback(invoke_without_command=True)
def models_root(
    ctx: typer.Context,
    provider: Annotated[str | None, typer.Argument(help='Optional provider filter')] = None,
) -> None:
    if ctx.invoked_subcommand is None:
        list_models(_get_settings(), provider)


@models_app.command('list')
def models_list(
    provider: Annotated[str | None, typer.Argument(help='Optional provider filter')] = None,
) -> None:
    list_models(_get_settings(), provider)


@models_app.command('set')
def models_set(
    model: Annotated[str | None, typer.Argument(help='Model name to persist')] = None,
) -> None:
    settings = _get_settings()
    selected = model or interactive_model_pick(settings, current=settings.default_model)
    if not selected:
        raise typer.Exit(1)
    set_default_model(settings, selected)


@modes_app.callback(invoke_without_command=True)
def modes_root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        for mode in list_mode_names():
            console.print(mode)


@modes_app.command('list')
def modes_list() -> None:
    for mode in list_mode_names():
        console.print(mode)


@modes_app.command('set')
def modes_set(
    mode: Annotated[str | None, typer.Argument(help='Mode name to persist')] = None,
) -> None:
    settings = _get_settings()
    selected = mode or interactive_mode_pick(current=settings.default_mode.value)
    if not selected:
        raise typer.Exit(1)
    parsed_mode = _parse_mode(selected)
    assert parsed_mode is not None
    set_default_mode(settings, parsed_mode)


@sessions_app.callback(invoke_without_command=True)
def sessions_root(
    ctx: typer.Context,
    plain: Annotated[bool, typer.Option('--plain', help='Print IDs only')] = False,
) -> None:
    if ctx.invoked_subcommand is None:
        _sessions_list(plain=plain)


@sessions_app.command('list')
def sessions_list(
    plain: Annotated[bool, typer.Option('--plain', help='Print IDs only')] = False,
) -> None:
    _sessions_list(plain=plain)


@sessions_app.command('set')
def sessions_set(
    session_id: Annotated[str | None, typer.Argument(help='Session ID')] = None,
) -> None:
    settings = _get_settings()
    store = JsonSessionStore(settings.session_dir)
    selected = session_id or interactive_session_pick(store)
    if not selected:
        raise typer.Exit(1)
    run_chat_with_session(selected, settings)


@sessions_app.command('delete')
def sessions_delete(
    session_id: Annotated[str | None, typer.Argument(help='Session ID')] = None,
) -> None:
    settings = _get_settings()
    store = JsonSessionStore(settings.session_dir)
    selected = session_id or interactive_session_pick(store)
    if not selected:
        raise typer.Exit(1)
    if store.delete(selected):
        print_info(f'Deleted session {selected}')
        return
    print_error(f'Session not found: {selected}')
    raise typer.Exit(1)


@sessions_app.command('new')
def sessions_new() -> None:
    settings = _get_settings()
    run_chat(settings.default_mode, settings)


@settings_app.callback(invoke_without_command=True)
def settings_root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        _settings_list()


@settings_app.command('list')
def settings_list() -> None:
    _settings_list()


@settings_app.command('get')
def settings_get(
    key: Annotated[str, typer.Argument(help='Config key to show')],
) -> None:
    settings = _get_settings()
    if key not in FridaySettings.model_fields:
        print_error(f'Unknown setting: {key}')
        raise typer.Exit(1)
    value = getattr(settings, key)
    console.print(f'{key} = {value}')


@memories_app.callback(invoke_without_command=True)
def memories_root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        _memories_list()


@memories_app.command('list')
def memories_list() -> None:
    _memories_list()


@memories_app.command('search')
def memories_search(
    query: Annotated[str, typer.Argument(help='Search query')],
) -> None:
    settings = _get_settings()
    store = _memory_store(settings)
    results = store.search(
        query,
        workspace_key=_workspace_key(),
        limit=max(6, settings.memory_top_k),
    )
    print_memory_search_results(results)


@memories_app.command('set')
def memories_set(
    text: Annotated[str, typer.Argument(help='Memory text to save')],
) -> None:
    settings = _get_settings()
    store = _memory_store(settings)
    record, created = store.save_memory(
        text,
        kind=MemoryKind.NOTE,
        scope=MemoryScope.GLOBAL,
        workspace_key=_workspace_key(),
        pinned=True,
    )
    action = 'Saved' if created else 'Updated'
    print_info(f'{action} memory {record.id}')


@memories_app.command('get')
def memories_get(
    memory_id: Annotated[str | None, typer.Argument(help='Memory ID')] = None,
) -> None:
    settings = _get_settings()
    store = _memory_store(settings)
    selected = memory_id or interactive_memory_pick(store, workspace_key=_workspace_key())
    if not selected:
        raise typer.Exit(1)
    record = store.get_memory(selected)
    if record is None:
        print_error(f'Memory not found: {selected}')
        raise typer.Exit(1)
    console.print(f'id = {record.id}')
    console.print(f'scope = {record.scope.value}')
    console.print(f'kind = {record.kind.value}')
    console.print(f'pinned = {record.pinned}')
    console.print(f'text = {record.text}')


@memories_app.command('delete')
def memories_delete(
    memory_id: Annotated[str | None, typer.Argument(help='Memory ID')] = None,
) -> None:
    settings = _get_settings()
    store = _memory_store(settings)
    selected = memory_id or interactive_memory_pick(store, workspace_key=_workspace_key())
    if not selected:
        raise typer.Exit(1)
    if store.delete_memory(selected):
        print_info(f'Deleted memory {selected}')
        return
    print_error(f'Memory not found: {selected}')
    raise typer.Exit(1)


@app.command(hidden=True)
def session() -> None:
    _legacy_command('session')


@app.command(hidden=True)
def model() -> None:
    _legacy_command('model')


@app.command(hidden=True)
def mode() -> None:
    _legacy_command('mode')


@app.command(hidden=True)
def config() -> None:
    _legacy_command('config')


def _sessions_list(*, plain: bool) -> None:
    settings = _get_settings()
    store = JsonSessionStore(settings.session_dir)
    sessions = store.list_sessions(limit=20)
    if plain:
        for session in sessions:
            console.print(session.id)
        return
    print_session_table(sessions)


def _settings_list() -> None:
    settings = _get_settings()
    for field_name in FridaySettings.model_fields:
        value = getattr(settings, field_name)
        console.print(f'  {field_name} = {value}')


def _memories_list() -> None:
    settings = _get_settings()
    store = _memory_store(settings)
    print_memory_table(store.list_memories(workspace_key=_workspace_key(), limit=20))


app.add_typer(models_app, name='models')
app.add_typer(modes_app, name='modes')
app.add_typer(sessions_app, name='sessions')
app.add_typer(settings_app, name='settings')
app.add_typer(memories_app, name='memories')


def main() -> None:
    app()
