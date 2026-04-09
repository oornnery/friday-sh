"""Agent runtime built on top of Pydantic AI."""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, cast

from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import UserError
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.output import DeferredToolRequests
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import DeferredToolResults, ToolApproved, ToolDenied
from pydantic_ai.toolsets import ApprovalRequiredToolset, FunctionToolset
from pydantic_ai.usage import RunUsage, UsageLimits

from friday.agent.context import WorkspaceContext
from friday.agent.contracts import (
    AgentReply,
    RouterDecision,
    RouterDecisionAction,
    TurnOutput,
)
from friday.agent.deps import AgentDeps
from friday.agent.history import build_history_processor
from friday.agent.memory import (
    load_relevant_shared_memory,
    record_completed_turn,
    sync_shared_memory_to_working_memory,
)
from friday.agent.modes import MODE_CONFIGS, ModePromptConfig
from friday.agent.stats import record_turn_result
from friday.cli.confirm import confirm_deferred_tool
from friday.domain.models import AgentMode
from friday.domain.permissions import clip
from friday.infra.config import FridaySettings
from friday.infra.mcp import create_mcp_servers
from friday.tools import filesystem, shell
from friday.tools import memory as memory_tools

__all__ = [
    'TOOL_FUNCTIONS',
    'AgentDeps',
    'ExecutedTurn',
    'create_agent',
    'execute_agent',
    'resolve_model_with_fallback',
]

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _ToolSpec:
    name: str
    function: Callable[..., Any]
    domain: str
    requires_approval: bool = False


@dataclass(slots=True)
class ExecutedTurn:
    """A completed agent turn after resolving any deferred approvals."""

    reply: AgentReply
    messages: list[ModelMessage]


TOOL_FUNCTIONS: dict[str, Callable[..., Any]] = {
    'read_file': filesystem.read_file,
    'write_file': filesystem.write_file,
    'patch_file': filesystem.patch_file,
    'list_files': filesystem.list_files,
    'search': filesystem.search,
    'run_shell': shell.run_shell,
    'search_memory': memory_tools.search_memory,
    'save_memory': memory_tools.save_memory,
    'list_memories': memory_tools.list_memories,
}

_TOOL_SPECS: dict[str, _ToolSpec] = {
    'read_file': _ToolSpec('read_file', filesystem.read_file, domain='filesystem'),
    'write_file': _ToolSpec(
        'write_file',
        filesystem.write_file,
        domain='filesystem-write',
        requires_approval=True,
    ),
    'patch_file': _ToolSpec(
        'patch_file',
        filesystem.patch_file,
        domain='filesystem-write',
        requires_approval=True,
    ),
    'list_files': _ToolSpec('list_files', filesystem.list_files, domain='filesystem'),
    'search': _ToolSpec('search', filesystem.search, domain='filesystem'),
    'run_shell': _ToolSpec(
        'run_shell',
        shell.run_shell,
        domain='shell',
        requires_approval=True,
    ),
    'search_memory': _ToolSpec(
        'search_memory',
        memory_tools.search_memory,
        domain='memory',
    ),
    'save_memory': _ToolSpec(
        'save_memory',
        memory_tools.save_memory,
        domain='memory',
    ),
    'list_memories': _ToolSpec(
        'list_memories',
        memory_tools.list_memories,
        domain='memory',
    ),
}

_REQUEST_HISTORY_LIMIT = 12


def _resolve_model(model_name: str, settings: FridaySettings) -> Model:
    """Resolve model string to a concrete pydantic-ai Model."""
    if model_name.startswith('zai:'):
        api_key = settings.zai_api_key or os.environ.get('ZAI_API_KEY', '')
        base_url = settings.zai_base_url or os.environ.get('ZAI_BASE_URL', '')
        if not api_key:
            msg = 'Set `ZAI_API_KEY` in .env to use the zai: provider.'
            raise UserError(msg)
        return OpenAIChatModel(
            model_name.removeprefix('zai:'),
            provider=OpenAIProvider(base_url=base_url, api_key=api_key),
        )

    from pydantic_ai.models import infer_model

    return infer_model(model_name)


def resolve_model_with_fallback(model_name: str, settings: FridaySettings) -> Model | str:
    """Resolve the configured model, falling back when necessary."""
    try:
        return _resolve_model(model_name, settings)
    except UserError:
        if settings.fallback_model and settings.fallback_model != model_name:
            log.info(
                'Model %s unavailable, falling back to %s',
                model_name,
                settings.fallback_model,
            )
            return _resolve_model(settings.fallback_model, settings)
        raise


def _build_model_settings(mode_config: ModePromptConfig) -> ModelSettings | None:
    if not mode_config.thinking:
        return None
    return ModelSettings(thinking=mode_config.thinking)


def _lookup_tool_spec(name: str) -> _ToolSpec:
    if name in _TOOL_SPECS:
        return _TOOL_SPECS[name]

    from friday.agent.router import DELEGATE_TOOLS

    if name in DELEGATE_TOOLS:
        return _ToolSpec(name, DELEGATE_TOOLS[name], domain='delegation')

    msg = f'Unknown tool: {name}'
    raise KeyError(msg)


def _build_toolsets(mode_config: ModePromptConfig, settings: FridaySettings) -> list[Any]:
    grouped_tools: dict[str, list[Callable[..., Any]]] = defaultdict(list)
    approval_domains: set[str] = set()
    for tool_name in mode_config.tools:
        spec = _lookup_tool_spec(tool_name)
        grouped_tools[spec.domain].append(spec.function)
        if spec.requires_approval:
            approval_domains.add(spec.domain)

    toolsets: list[Any] = []
    for domain, tools in grouped_tools.items():
        toolset: Any = FunctionToolset(tools=tools, id=f'{domain}-tools')
        if domain in approval_domains:
            toolset = ApprovalRequiredToolset(toolset)
        toolsets.append(toolset)
    toolsets.extend(create_mcp_servers(settings.mcp_servers))
    log.debug(
        'built toolsets: mode_tools=%s toolset_ids=%s',
        list(mode_config.tools),
        [getattr(toolset, 'id', '<anonymous>') for toolset in toolsets],
    )
    return toolsets


def _instructions(
    mode_config: ModePromptConfig,
) -> list[str | Callable[[RunContext[AgentDeps]], str]]:
    def runtime_instructions(ctx: RunContext[AgentDeps]) -> str:
        return (
            '## Relevant Shared Memory\n'
            f'{ctx.deps.shared_memory.render()}\n\n'
            '## Working Memory\n'
            f'{ctx.deps.memory.render()}\n\n'
            '## Workspace\n'
            f'{ctx.deps.context.render()}'
        )

    return [mode_config.system_prompt, runtime_instructions]


def _auto_instructions(
    mode_config: ModePromptConfig,
) -> list[str | Callable[[RunContext[AgentDeps]], str]]:
    def runtime_instructions(ctx: RunContext[AgentDeps]) -> str:
        return (
            '## Relevant Shared Memory\n'
            f'{ctx.deps.shared_memory.render()}\n\n'
            '## Working Memory\n'
            f'{ctx.deps.memory.render()}\n\n'
            '## Workspace Summary\n'
            f'{ctx.deps.context.render_summary()}'
        )

    return [
        mode_config.system_prompt,
        (
            'Return a structured routing decision.\n'
            '- Use action="respond" and fill reply when you can answer directly.\n'
            '- Use action="delegate" and fill delegate_mode + task when a specialist is needed.\n'
            '- Prefer respond for greetings, conversation, names, preferences, simple facts, '
            'and anything that does not require specialist work.\n'
            '- Prefer delegate for shell commands, coding, debugging, '
            'documentation, or deep code reading.\n'
            '- Treat Relevant Shared Memory as trusted context for stable user and project facts.\n'
            '- If Relevant Shared Memory already answers the question, respond directly instead of '
            'asking the user to repeat it.\n'
        ),
        runtime_instructions,
    ]


def _build_usage_limits(settings: FridaySettings, mode_config: ModePromptConfig) -> UsageLimits:
    max_steps = min(settings.max_steps, mode_config.max_steps)
    return UsageLimits(
        request_limit=max_steps + 5,
        tool_calls_limit=max_steps,
    )


def create_agent(
    mode: AgentMode,
    settings: FridaySettings,
    context: WorkspaceContext,
) -> Agent[AgentDeps, Any]:
    """Build a mode-specific agent with structured output and toolsets."""
    mode_config = MODE_CONFIGS[mode]
    model_name = mode_config.model or settings.default_model

    try:
        model = _resolve_model(model_name, settings)
    except UserError:
        if settings.fallback_model and settings.fallback_model != model_name:
            log.info(
                'Model %s unavailable, falling back to %s',
                model_name,
                settings.fallback_model,
            )
            model = _resolve_model(settings.fallback_model, settings)
        else:
            raise

    if mode is AgentMode.AUTO:
        log.debug('creating auto router agent: model=%s', model_name)
        return cast(
            Agent[AgentDeps, RouterDecision],
            Agent(
                model=model,
                output_type=RouterDecision,
                instructions=_auto_instructions(mode_config),
                deps_type=AgentDeps,
                name='friday-auto',
                description=mode_config.description,
                model_settings=_build_model_settings(mode_config),
                retries=2,
                defer_model_check=True,
                history_processors=[build_history_processor(_REQUEST_HISTORY_LIMIT)],
            ),
        )

    log.debug(
        'creating specialist agent: mode=%s model=%s tools=%s',
        mode.value,
        model_name,
        list(mode_config.tools),
    )
    return cast(
        Agent[AgentDeps, TurnOutput],
        Agent(
            model=model,
            output_type=TurnOutput,
            instructions=_instructions(mode_config),
            deps_type=AgentDeps,
            name=f'friday-{mode.value}',
            description=mode_config.description,
            model_settings=_build_model_settings(mode_config),
            retries=2,
            toolsets=_build_toolsets(mode_config, settings),
            defer_model_check=True,
            history_processors=[build_history_processor(_REQUEST_HISTORY_LIMIT)],
        ),
    )


async def execute_agent(
    agent: Agent[AgentDeps, Any],
    *,
    deps: AgentDeps,
    user_prompt: str | None,
    message_history: Sequence[ModelMessage] | None = None,
    usage: RunUsage | None = None,
    requested_model: str = '',
    record_memory: bool = True,
) -> ExecutedTurn:
    """Run an agent to completion, resolving deferred approvals along the way."""
    history = list(message_history or [])
    deferred_results: DeferredToolResults | None = None
    next_prompt = user_prompt
    run_usage = usage or RunUsage()

    if user_prompt:
        _prepare_turn(deps, user_prompt)
        if deps.memory.mode is AgentMode.AUTO:
            return await _execute_auto_turn(
                agent,
                deps=deps,
                user_prompt=user_prompt,
                message_history=history,
                usage=run_usage,
                requested_model=requested_model,
                record_memory=record_memory,
            )

    while True:
        log.debug(
            'executing specialist turn: mode=%s prompt=%s history=%s',
            deps.memory.mode.value,
            clip(user_prompt or '', 120),
            len(history),
        )
        result = await agent.run(
            next_prompt,
            deps=deps,
            message_history=history or None,
            deferred_tool_results=deferred_results,
            usage_limits=_build_usage_limits(deps.settings, MODE_CONFIGS[deps.memory.mode]),
            usage=run_usage,
        )
        record_turn_result(deps.turn_stats, result, requested_model or deps.settings.default_model)
        history = result.all_messages()

        if isinstance(result.output, DeferredToolRequests):
            log.debug(
                'specialist returned deferred approvals: approvals=%s calls=%s',
                len(result.output.approvals),
                len(result.output.calls),
            )
            deferred_results = _resolve_deferred_requests(result.output, deps)
            next_prompt = None
            continue

        if user_prompt:
            record_completed_turn(
                deps,
                user_prompt=user_prompt,
                reply_markdown=result.output.markdown,
                record_chat_chunk=record_memory,
            )
        return ExecutedTurn(reply=result.output, messages=history)


def _prepare_turn(deps: AgentDeps, user_prompt: str) -> None:
    deps.memory.task = clip(str(user_prompt), 240)
    deps.shared_memory = load_relevant_shared_memory(deps, user_prompt)
    sync_shared_memory_to_working_memory(deps)
    log.debug(
        'prepared turn: mode=%s session=%s prompt=%s shared_records=%s shared_chats=%s',
        deps.memory.mode.value,
        deps.session_id,
        clip(user_prompt, 120),
        len(deps.shared_memory.records),
        len(deps.shared_memory.chats),
    )


def _visible_turn_messages(
    history: list[ModelMessage],
    *,
    user_prompt: str,
    reply_text: str,
    model_name: str,
) -> list[ModelMessage]:
    messages = list(history)
    messages.append(ModelRequest.user_text_prompt(user_prompt))
    messages.append(
        ModelResponse(
            parts=[TextPart(reply_text)],
            model_name=model_name,
            provider_name='friday',
        )
    )
    return messages


async def _run_specialist_from_auto(
    deps: AgentDeps,
    *,
    delegate_mode: AgentMode,
    delegate_task: str,
    message_history: list[ModelMessage],
    usage: RunUsage,
    requested_model: str,
) -> ExecutedTurn:
    specialist = create_agent(delegate_mode, deps.settings, deps.context)
    return await execute_agent(
        specialist,
        deps=deps,
        user_prompt=delegate_task,
        message_history=message_history or None,
        usage=usage,
        requested_model=requested_model,
        record_memory=False,
    )


async def _execute_auto_turn(
    agent: Agent[AgentDeps, Any],
    *,
    deps: AgentDeps,
    user_prompt: str,
    message_history: list[ModelMessage],
    usage: RunUsage,
    requested_model: str,
    record_memory: bool,
) -> ExecutedTurn:
    log.debug(
        'executing auto turn: session=%s prompt=%s history=%s',
        deps.session_id,
        clip(user_prompt, 120),
        len(message_history),
    )
    result = await agent.run(
        user_prompt,
        deps=deps,
        message_history=message_history or None,
        usage_limits=_build_usage_limits(deps.settings, MODE_CONFIGS[AgentMode.AUTO]),
        usage=usage,
    )
    record_turn_result(deps.turn_stats, result, requested_model or deps.settings.default_model)
    decision = cast(RouterDecision, result.output)
    log.debug(
        'auto router decision: action=%s delegate_mode=%s task=%s',
        decision.action,
        decision.delegate_mode,
        clip(decision.task, 160),
    )

    if decision.action is RouterDecisionAction.RESPOND:
        reply_text = decision.reply.strip() or 'Como posso ajudar?'
        messages = _visible_turn_messages(
            message_history,
            user_prompt=user_prompt,
            reply_text=reply_text,
            model_name=requested_model or deps.settings.default_model,
        )
        if record_memory:
            record_completed_turn(
                deps,
                user_prompt=user_prompt,
                reply_markdown=reply_text,
                record_chat_chunk=True,
            )
        return ExecutedTurn(reply=AgentReply(markdown=reply_text), messages=messages)

    delegate_mode = decision.delegate_mode
    delegate_task = decision.task.strip()
    if delegate_mode is None or delegate_mode is AgentMode.AUTO or not delegate_task:
        log.debug('auto decision invalid, falling back to clarification reply')
        reply = AgentReply(
            markdown='Não consegui classificar com confiança. Pode reformular o pedido?',
        )
        messages = _visible_turn_messages(
            message_history,
            user_prompt=user_prompt,
            reply_text=reply.markdown,
            model_name=requested_model or deps.settings.default_model,
        )
        return ExecutedTurn(reply=reply, messages=messages)

    original_mode = deps.memory.mode
    try:
        deps.memory.mode = delegate_mode
        log.debug(
            'delegating auto turn to specialist: mode=%s task=%s',
            delegate_mode.value,
            clip(delegate_task, 160),
        )
        executed = await _run_specialist_from_auto(
            deps=deps,
            delegate_mode=delegate_mode,
            delegate_task=delegate_task,
            message_history=message_history,
            usage=usage,
            requested_model=requested_model,
        )
    finally:
        deps.memory.mode = original_mode

    visible_messages = _visible_turn_messages(
        message_history,
        user_prompt=user_prompt,
        reply_text=executed.reply.markdown,
        model_name=requested_model or deps.settings.default_model,
    )
    if record_memory:
        record_completed_turn(
            deps,
            user_prompt=user_prompt,
            reply_markdown=executed.reply.markdown,
            record_chat_chunk=True,
        )
    return ExecutedTurn(reply=executed.reply, messages=visible_messages)


def _resolve_deferred_requests(
    deferred: DeferredToolRequests,
    deps: AgentDeps,
) -> DeferredToolResults:
    if deferred.calls:
        msg = 'Friday does not support externally executed deferred tools yet.'
        raise UserError(msg)

    approvals: dict[str, bool | ToolApproved | ToolDenied] = {}
    for call in deferred.approvals:
        tool_call_id = call.tool_call_id
        if not tool_call_id:
            msg = 'Deferred tool approval is missing a tool_call_id.'
            raise UserError(msg)

        if deps.settings.approval_policy == 'auto':
            log.info(
                'approval auto-granted: tool=%s args=%s',
                call.tool_name,
                clip(str(call.args), 120),
            )
            approvals[tool_call_id] = True
            continue

        if deps.settings.approval_policy == 'never':
            log.info('approval denied by policy: tool=%s', call.tool_name)
            approvals[tool_call_id] = ToolDenied(
                message='Friday approval policy denied this tool call.',
            )
            continue

        if not deps.interactive:
            log.debug(
                'approval denied due to non-interactive terminal: tool=%s id=%s',
                call.tool_name,
                tool_call_id,
            )
            approvals[tool_call_id] = ToolDenied(
                message='Approval required, but Friday is running without an interactive terminal.',
            )
            continue

        if deps.before_approval is not None:
            deps.before_approval()
        try:
            approved = confirm_deferred_tool(call)
        finally:
            if deps.after_approval is not None:
                deps.after_approval()

        if approved:
            log.info('approval granted: tool=%s', call.tool_name)
            approvals[tool_call_id] = True
            continue

        log.info('approval denied: tool=%s', call.tool_name)
        approvals[tool_call_id] = ToolDenied(message='The user denied this tool call.')

    return DeferredToolResults(approvals=approvals, metadata=deferred.metadata)
