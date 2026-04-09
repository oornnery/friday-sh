"""Interactive REPL backed by the unified Friday runtime."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from pydantic_ai.exceptions import UserError
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from rich.status import Status

from friday.agent.context import WorkspaceContext
from friday.agent.core import create_agent, execute_agent
from friday.agent.deps import AgentDeps
from friday.agent.stats import format_turn_summary
from friday.cli.catalog import LEGACY_COMMAND_SUGGESTIONS, REPL_COMMANDS
from friday.cli.completer import FridayCompleter
from friday.cli.debug import format_debug_status, print_debug_traceback, set_debug_logging
from friday.cli.models import list_models
from friday.cli.output import console, print_error, print_info, print_markdown, print_run_summary
from friday.cli.resources import (
    interactive_memory_pick,
    interactive_mode_pick,
    interactive_model_pick,
    interactive_session_pick,
    list_mode_names,
    print_memory_search_results,
    print_memory_table,
    print_session_table,
)
from friday.cli.theme import PT_STYLE, make_prompt_message
from friday.domain.models import AgentMode, MemoryKind, MemoryScope
from friday.infra.config import FridaySettings
from friday.infra.memory import SharedMemorySnapshot, SQLiteMemoryStore
from friday.infra.sessions import (
    JsonSessionStore,
    SessionData,
    SessionMeta,
    extract_last_user_message,
    extract_turn_count,
)

log = logging.getLogger(__name__)


@dataclass(slots=True)
class ChatState:
    """Mutable state for the current REPL session."""

    model: str
    mode: AgentMode
    session_meta: SessionMeta
    message_history: list[ModelMessage] = field(default_factory=list)
    rebuild_agent: bool = True
    debug_enabled: bool = False


def _session_id() -> str:
    return f'{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}'


def _new_session_meta(model: str, mode: AgentMode) -> SessionMeta:
    return SessionMeta(
        id=_session_id(),
        created_at=datetime.now().isoformat(),
        model=model,
        mode=mode.value,
    )


def _parse_mode(value: str, fallback: AgentMode) -> AgentMode:
    try:
        return AgentMode(value)
    except ValueError:
        return fallback


def _effective_settings(settings: FridaySettings, state: ChatState) -> FridaySettings:
    return settings.model_copy(
        update={
            'default_model': state.model,
            'default_mode': state.mode,
        }
    )


def _print_settings(settings: FridaySettings) -> None:
    for field_name in FridaySettings.model_fields:
        console.print(f'  {field_name} = {getattr(settings, field_name)}')


def _workspace_key(context: WorkspaceContext) -> str:
    return context.repo_root.resolve().as_posix()


def _save_session(
    store: JsonSessionStore,
    state: ChatState,
    context: WorkspaceContext,
) -> None:
    serialized = ModelMessagesTypeAdapter.dump_python(state.message_history, mode='json')
    meta = state.session_meta.model_copy(deep=True)
    meta.turn_count = extract_turn_count(serialized)
    meta.last_user_message = extract_last_user_message(serialized)
    meta.model = state.model
    meta.mode = state.mode.value
    meta.workspace_key = _workspace_key(context)
    store.save(SessionData(meta=meta, messages=state.message_history))
    state.session_meta = meta
    log.debug('session saved: id=%s turns=%s', meta.id, meta.turn_count)


def _print_help() -> None:
    for name, desc in REPL_COMMANDS.items():
        console.print(f'  [info]{name:<12}[/info] {desc}')


def _handle_debug(args: list[str], state: ChatState) -> bool:
    subcommand = args[0] if args else 'toggle'

    if subcommand == 'status':
        print_info(f'Debug is {format_debug_status(state.debug_enabled)}')
        return True

    if subcommand in {'toggle', 'on', 'off'}:
        enabled = not state.debug_enabled if subcommand == 'toggle' else subcommand == 'on'
        state.debug_enabled = set_debug_logging(enabled)
        print_info(f'Debug is {format_debug_status(state.debug_enabled)}')
        return True

    print_error(f'Unknown command: /debug {" ".join(args)}')
    print_info('Usage: /debug [on|off|status]')
    return True


def _handle_models(args: list[str], state: ChatState, settings: FridaySettings) -> bool:
    if not args or args[0] == 'list':
        provider = args[1] if len(args) > 1 else None
        list_models(settings, provider)
        return True

    if args[0] == 'set':
        selected = (
            args[1]
            if len(args) > 1
            else interactive_model_pick(settings, current=state.model)
        )
        if not selected:
            return True
        state.model = selected
        state.rebuild_agent = True
        print_info(f'Switched to model: {selected}')
        return True

    print_error(f'Unknown command: /models {" ".join(args)}')
    print_info('Usage: /models [list [provider]] | /models set [model]')
    return True


def _handle_modes(args: list[str], state: ChatState) -> bool:
    if not args or args[0] == 'list':
        for mode in list_mode_names():
            console.print(mode)
        return True

    if args[0] == 'set':
        selected = args[1] if len(args) > 1 else interactive_mode_pick(current=state.mode.value)
        if not selected:
            return True
        state.mode = AgentMode(selected)
        state.rebuild_agent = True
        print_info(f'Switched to mode: {state.mode.value}')
        return True

    print_error(f'Unknown command: /modes {" ".join(args)}')
    print_info('Usage: /modes [list] | /modes set [mode]')
    return True


def _handle_sessions(
    args: list[str],
    state: ChatState,
    store: JsonSessionStore,
    deps: AgentDeps | None = None,
) -> bool:
    subcommand = args[0] if args else 'list'
    log.debug('sessions command: %s', subcommand)

    if subcommand == 'list':
        print_session_table(store.list_sessions(limit=20), active_id=state.session_meta.id)
        return True

    if subcommand == 'new':
        state.message_history = []
        state.session_meta = _new_session_meta(state.model, state.mode)
        state.rebuild_agent = True
        if deps is not None:
            _reset_repl_runtime_state(deps, state)
        print_info(f'New session: {state.session_meta.id}')
        return True

    if subcommand == 'set':
        session_id = args[1] if len(args) > 1 else interactive_session_pick(
            store,
            current=state.session_meta.id,
        )
        if not session_id:
            return True
        try:
            data = store.load(session_id)
        except FileNotFoundError:
            print_error(f'Session not found: {session_id}')
            return True

        state.message_history = list(data.messages)
        state.model = data.meta.model or state.model
        state.mode = _parse_mode(data.meta.mode, state.mode)
        state.session_meta = data.meta
        state.rebuild_agent = True
        if deps is not None:
            _reset_repl_runtime_state(deps, state)
        print_info(f'Switched to session {data.meta.id} ({data.meta.turn_count} turns)')
        return True

    if subcommand == 'delete':
        session_id = args[1] if len(args) > 1 else interactive_session_pick(
            store,
            current=state.session_meta.id,
        )
        if not session_id:
            return True
        if store.delete(session_id):
            print_info(f'Deleted session {session_id}')
        else:
            print_error(f'Session not found: {session_id}')
        return True

    print_error(f'Unknown command: /sessions {" ".join(args)}')
    print_info(
        'Usage: /sessions [list] | /sessions set [id] | /sessions new '
        '| /sessions delete [id]'
    )
    return True


def _reset_repl_runtime_state(deps: AgentDeps, state: ChatState) -> None:
    deps.memory.reset(mode=state.mode)
    deps.shared_memory = SharedMemorySnapshot()
    deps.session_id = state.session_meta.id


def _handle_memories(
    command: str,
    args: list[str],
    deps: AgentDeps | None,
    memory_store: SQLiteMemoryStore | None,
) -> bool:
    if deps is None or memory_store is None:
        print_error('Shared memory is unavailable in this context.')
        return True

    subcommand = args[0] if args else 'list'
    workspace_key = _workspace_key(deps.context)
    log.debug('memories command: %s workspace=%s', subcommand, workspace_key)

    if subcommand == 'list':
        print_memory_table(memory_store.list_memories(workspace_key=workspace_key, limit=20))
        return True

    if subcommand == 'search':
        query = command.removeprefix('/memories').strip().removeprefix('search').strip()
        if not query:
            print_error('Usage: /memories search <query>')
            return True
        results = memory_store.search(
            query,
            workspace_key=workspace_key,
            current_session_id=deps.session_id,
            limit=max(6, deps.settings.memory_top_k),
        )
        print_memory_search_results(results)
        return True

    if subcommand == 'set':
        text = command.removeprefix('/memories').strip().removeprefix('set').strip()
        if not text:
            print_error('Usage: /memories set <text>')
            return True
        record, created = memory_store.save_memory(
            text,
            kind=MemoryKind.NOTE,
            scope=MemoryScope.GLOBAL,
            workspace_key=workspace_key,
            pinned=True,
        )
        deps.memory.remember(deps.memory.notes, f'memory:{record.id}', 8)
        action = 'Saved' if created else 'Updated'
        print_info(f'{action} memory {record.id}')
        return True

    if subcommand == 'get':
        memory_id = args[1] if len(args) > 1 else interactive_memory_pick(
            memory_store,
            workspace_key=workspace_key,
        )
        if not memory_id:
            return True
        record = memory_store.get_memory(memory_id)
        if record is None:
            print_error(f'Memory not found: {memory_id}')
            return True
        console.print(f'id = {record.id}')
        console.print(f'scope = {record.scope.value}')
        console.print(f'kind = {record.kind.value}')
        console.print(f'pinned = {record.pinned}')
        console.print(f'text = {record.text}')
        return True

    if subcommand == 'delete':
        memory_id = args[1] if len(args) > 1 else interactive_memory_pick(
            memory_store,
            workspace_key=workspace_key,
        )
        if not memory_id:
            return True
        if memory_store.delete_memory(memory_id):
            print_info(f'Deleted memory {memory_id}')
        else:
            print_error(f'Memory not found: {memory_id}')
        return True

    print_error(f'Unknown command: /memories {" ".join(args)}')
    print_info(
        'Usage: /memories [list] | /memories search <query> | /memories set <text> '
        '| /memories get [id] | /memories delete [id]'
    )
    return True


def _handle_settings(args: list[str], state: ChatState, settings: FridaySettings) -> bool:
    effective = _effective_settings(settings, state)
    subcommand = args[0] if args else 'list'

    if subcommand == 'list':
        _print_settings(effective)
        return True

    if subcommand == 'get':
        if len(args) < 2:
            print_error('Usage: /settings get <key>')
            return True
        key = args[1]
        if key not in FridaySettings.model_fields:
            print_error(f'Unknown setting: {key}')
            return True
        console.print(f'{key} = {getattr(effective, key)}')
        return True

    print_error(f'Unknown command: /settings {" ".join(args)}')
    print_info('Usage: /settings [list] | /settings get <key>')
    return True


def _handle_slash(
    command: str,
    state: ChatState,
    settings: FridaySettings,
    store: JsonSessionStore,
    deps: AgentDeps | None = None,
    memory_store: SQLiteMemoryStore | None = None,
) -> bool:
    parts = command.strip().split()
    if not parts:
        return True

    cmd = parts[0].lower()
    args = parts[1:]

    if cmd in ('/quit', '/exit'):
        raise EOFError

    if cmd in LEGACY_COMMAND_SUGGESTIONS:
        replacement = LEGACY_COMMAND_SUGGESTIONS[cmd]
        print_error(f'`{cmd}` no longer exists.')
        print_info(f'Use `{replacement}` instead.')
        return True

    if cmd == '/help':
        _print_help()
        return True

    if cmd == '/debug':
        return _handle_debug(args, state)

    if cmd == '/models':
        return _handle_models(args, state, settings)

    if cmd == '/modes':
        return _handle_modes(args, state)

    if cmd == '/sessions':
        return _handle_sessions(args, state, store, deps)

    if cmd == '/memories':
        return _handle_memories(command, args, deps, memory_store)

    if cmd == '/settings':
        return _handle_settings(args, state, settings)

    if cmd == '/clear':
        state.message_history = []
        state.session_meta = _new_session_meta(state.model, state.mode)
        state.rebuild_agent = True
        if deps is not None:
            _reset_repl_runtime_state(deps, state)
        print_info('Conversation cleared (new session)')
        return True

    return False


def _initial_state(
    mode: AgentMode,
    settings: FridaySettings,
    resume_session: SessionData | None,
) -> ChatState:
    if resume_session is None:
        return ChatState(
            model=settings.default_model,
            mode=mode,
            session_meta=_new_session_meta(settings.default_model, mode),
        )

    session_mode = _parse_mode(resume_session.meta.mode, mode)
    session_model = resume_session.meta.model or settings.default_model
    return ChatState(
        model=session_model,
        mode=session_mode,
        session_meta=resume_session.meta,
        message_history=list(resume_session.messages),
    )


def _build_agent(
    base_settings: FridaySettings,
    context: WorkspaceContext,
    deps: AgentDeps,
    state: ChatState,
):
    effective_settings = _effective_settings(base_settings, state)
    deps.settings = effective_settings
    deps.memory.mode = state.mode
    deps.session_id = state.session_meta.id
    log.debug('building agent: mode=%s model=%s', state.mode.value, state.model)
    return create_agent(state.mode, effective_settings, context)


def run_chat(
    mode: AgentMode,
    settings: FridaySettings,
    resume_session: SessionData | None = None,
) -> None:
    """Start the interactive REPL, optionally resuming a saved session."""
    history_path = settings.config_dir.expanduser() / 'repl_history'
    history_path.parent.mkdir(parents=True, exist_ok=True)

    context = WorkspaceContext.discover()
    store = JsonSessionStore(settings.session_dir)
    memory_store = SQLiteMemoryStore(settings.memory_db_path)
    state = _initial_state(mode, settings, resume_session)
    deps = AgentDeps(
        workspace_root=context.repo_root,
        context=context,
        settings=_effective_settings(settings, state),
        memory_store=memory_store,
        session_id=state.session_meta.id,
        interactive=True,
    )
    deps.memory.mode = state.mode

    prompt_session: PromptSession[str] = PromptSession(
        history=FileHistory(str(history_path)),
        completer=FridayCompleter(
            context.repo_root,
            settings.session_dir,
            settings.memory_db_path,
        ),
        style=PT_STYLE,
        complete_while_typing=True,
    )

    try:
        agent = _build_agent(settings, context, deps, state)
    except UserError as exc:
        print_error(f'{exc}')
        print_info('Check your API keys in .env or use /models set to pick another provider.')
        return

    state.rebuild_agent = False

    console.print()
    console.print('[accent]Friday[/accent] [muted]v0.1.0[/muted]')
    console.print(
        f'[muted]mode:[/muted] [info]{state.mode.value}[/info]  '
        f'[muted]model:[/muted] {state.model}'
    )
    if resume_session:
        console.print(
            f'[muted]session:[/muted] {state.session_meta.id} '
            f'[muted]({state.session_meta.turn_count} turns)[/muted]'
        )
    else:
        console.print(f'[muted]session:[/muted] {state.session_meta.id}')
    console.print('[muted]/help for commands · /quit to exit[/muted]')
    console.print()
    log.debug(
        'chat started: session=%s mode=%s model=%s',
        state.session_meta.id,
        state.mode.value,
        state.model,
    )

    while True:
        try:
            user_input = prompt_session.prompt(
                make_prompt_message(
                    state.mode.value,
                    state.model,
                    debug_enabled=state.debug_enabled,
                )
            ).strip()
        except (EOFError, KeyboardInterrupt):
            if state.message_history:
                _save_session(store, state, context)
                print_info(f'\nSession saved: {state.session_meta.id}')
            print_info('Bye!')
            break

        if not user_input:
            continue

        if user_input.startswith('/'):
            log.debug('slash command: %s', user_input)
            handled = _handle_slash(
                user_input,
                state,
                settings,
                store,
                deps=deps,
                memory_store=memory_store,
            )
            if handled:
                continue
            print_error(f'Unknown command: {user_input}')
            print_info('Use /help to list commands.')
            continue

        if state.rebuild_agent:
            try:
                agent = _build_agent(settings, context, deps, state)
            except UserError as exc:
                print_error(f'{exc}')
                print_info('Use /models set to pick another provider, or /models to list models.')
                continue
            state.rebuild_agent = False

        try:
            log.debug('user prompt: %s', user_input)
            deps.turn_stats.reset()
            with Status('Thinking...', console=console, spinner='dots') as status:
                if status is not None:
                    deps.before_approval = status.stop
                    deps.after_approval = status.start
                executed = asyncio.run(
                    execute_agent(
                        agent,
                        deps=deps,
                        user_prompt=user_input,
                        message_history=state.message_history or None,
                        requested_model=state.model,
                    )
                )
            print_markdown(executed.reply.markdown)
            print_run_summary(format_turn_summary(deps.turn_stats))
            state.message_history = executed.messages
            _save_session(store, state, context)
        except UserError as exc:
            print_error(f'{exc}')
            log.exception('user-facing error during chat turn')
            if state.debug_enabled:
                print_debug_traceback(exc)
            print_info('Use /models set to pick another provider, or /models to list models.')
        except KeyboardInterrupt:
            print_error('\nInterrupted. Type /quit to exit.')
        except Exception as exc:
            log.exception('unexpected chat error')
            if state.debug_enabled:
                print_debug_traceback(exc)
            else:
                print_error(f'Error: {exc}')


def run_chat_with_session(session_id: str, settings: FridaySettings) -> None:
    """Resume a saved session and enter chat."""
    store = JsonSessionStore(settings.session_dir)
    try:
        data = store.load(session_id)
    except FileNotFoundError:
        print_error(f'Session not found: {session_id}')
        return

    run_chat(settings.default_mode, settings, resume_session=data)
