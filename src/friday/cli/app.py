"""Friday CLI entrypoint."""

from __future__ import annotations

from typing import Annotated

import typer
from dotenv import load_dotenv

from friday.agent.context import WorkspaceContext
from friday.cli.ask import run_ask
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
model_app = typer.Typer(help='Select or show models', invoke_without_command=True)
mode_app = typer.Typer(help='Select or show modes', invoke_without_command=True)
session_app = typer.Typer(help='Manage saved sessions', invoke_without_command=True)
setting_app = typer.Typer(help='Read or update settings', invoke_without_command=True)
memory_app = typer.Typer(help='Inspect and manage shared memory', invoke_without_command=True)


def _get_settings() -> FridaySettings:
    settings = FridaySettings()
    settings.resolve_paths()
    return settings


def _parse_mode(value: str | None) -> AgentMode | None:
    if value is None:
        return None
    return AgentMode(value)


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


@model_app.callback(invoke_without_command=True)
def models_root(
    ctx: typer.Context,
    provider: Annotated[str | None, typer.Argument(help='Optional provider filter')] = None,
) -> None:
    if ctx.invoked_subcommand is None:
        list_models(_get_settings(), provider)


@model_app.command('show')
def models_list(
    provider: Annotated[str | None, typer.Argument(help='Optional provider filter')] = None,
) -> None:
    list_models(_get_settings(), provider)


@model_app.command('set')
def models_set(
    model: Annotated[str | None, typer.Argument(help='Model name to persist')] = None,
) -> None:
    settings = _get_settings()
    selected = model or interactive_model_pick(settings, current=settings.default_model)
    if not selected:
        raise typer.Exit(1)
    set_default_model(settings, selected)


@mode_app.callback(invoke_without_command=True)
def modes_root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        for mode in list_mode_names():
            console.print(mode)


@mode_app.command('show')
def modes_list() -> None:
    for mode in list_mode_names():
        console.print(mode)


@mode_app.command('set')
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


@session_app.callback(invoke_without_command=True)
def sessions_root(
    ctx: typer.Context,
    plain: Annotated[bool, typer.Option('--plain', help='Print IDs only')] = False,
) -> None:
    if ctx.invoked_subcommand is None:
        _sessions_list(plain=plain)


@session_app.command('show')
def sessions_list(
    plain: Annotated[bool, typer.Option('--plain', help='Print IDs only')] = False,
) -> None:
    _sessions_list(plain=plain)


@session_app.command('resume')
def sessions_resume(
    session_id: Annotated[str | None, typer.Argument(help='Session ID')] = None,
) -> None:
    settings = _get_settings()
    store = JsonSessionStore(settings.session_dir)
    selected = session_id or interactive_session_pick(store)
    if not selected:
        raise typer.Exit(1)
    run_chat_with_session(selected, settings)


@session_app.command('delete')
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


@session_app.command('new')
def sessions_new() -> None:
    settings = _get_settings()
    run_chat(settings.default_mode, settings)


@setting_app.callback(invoke_without_command=True)
def settings_root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        _settings_list()


@setting_app.command('show')
def settings_list() -> None:
    _settings_list()


@setting_app.command('get')
def settings_get(
    key: Annotated[str, typer.Argument(help='Config key to show')],
) -> None:
    settings = _get_settings()
    if key not in FridaySettings.model_fields:
        print_error(f'Unknown setting: {key}')
        raise typer.Exit(1)
    value = getattr(settings, key)
    console.print(f'{key} = {value}')


@memory_app.callback(invoke_without_command=True)
def memories_root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        _memories_list()


@memory_app.command('show')
def memories_list() -> None:
    _memories_list()


@memory_app.command('search')
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


@memory_app.command('add')
def memories_add(
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


@memory_app.command('get')
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


@memory_app.command('delete')
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


def _sessions_list(*, plain: bool) -> None:
    settings = _get_settings()
    store = JsonSessionStore(settings.session_dir)
    sessions = store.list_sessions(limit=20)
    if plain:
        for s in sessions:
            msg = s.last_user_message[:40].replace('\n', ' ') if s.last_user_message else ''
            ts = s.created_at[:16].replace('T', ' ') if s.created_at else ''
            console.print(f'{s.id}\t{ts}\t{s.turn_count}t\t{msg}')
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


app.add_typer(model_app, name='model')
app.add_typer(mode_app, name='mode')
app.add_typer(session_app, name='session')
app.add_typer(setting_app, name='setting')
app.add_typer(memory_app, name='memory')


def main() -> None:
    app()
