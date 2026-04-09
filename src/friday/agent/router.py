"""Delegate tools used by the auto/router mode."""

from __future__ import annotations

from pydantic_ai import RunContext

from friday.agent.contracts import AgentReply
from friday.agent.core import create_agent, execute_agent
from friday.agent.deps import AgentDeps
from friday.domain.models import AgentMode

__all__ = ['DELEGATE_TOOLS', 'create_router_agent']


async def _run_sub_agent(ctx: RunContext[AgentDeps], mode: AgentMode, task: str) -> AgentReply:
    agent = create_agent(mode, ctx.deps.settings, ctx.deps.context)
    original_mode = ctx.deps.memory.mode
    original_shared_memory = ctx.deps.shared_memory
    try:
        ctx.deps.memory.mode = mode
        executed = await execute_agent(
            agent,
            deps=ctx.deps,
            user_prompt=task,
            usage=ctx.usage,
            requested_model=ctx.deps.settings.default_model,
            record_memory=False,
        )
    finally:
        ctx.deps.memory.mode = original_mode
        ctx.deps.shared_memory = original_shared_memory
    return executed.reply


async def delegate_code(ctx: RunContext[AgentDeps], task: str) -> AgentReply:
    """Delegate a coding task that may read, edit, or verify code."""
    return await _run_sub_agent(ctx, AgentMode.CODE, task)


async def delegate_reader(ctx: RunContext[AgentDeps], task: str) -> AgentReply:
    """Delegate a read-only analysis task over project files."""
    return await _run_sub_agent(ctx, AgentMode.READER, task)


async def delegate_writer(ctx: RunContext[AgentDeps], task: str) -> AgentReply:
    """Delegate a documentation or writing task."""
    return await _run_sub_agent(ctx, AgentMode.WRITE, task)


async def delegate_debug(ctx: RunContext[AgentDeps], task: str) -> AgentReply:
    """Delegate a debugging task."""
    return await _run_sub_agent(ctx, AgentMode.DEBUG, task)


DELEGATE_TOOLS = {
    'delegate_code': delegate_code,
    'delegate_reader': delegate_reader,
    'delegate_writer': delegate_writer,
    'delegate_debug': delegate_debug,
}


def create_router_agent(settings, context):
    """Compatibility wrapper for the auto/router mode."""
    return create_agent(AgentMode.AUTO, settings, context)
