"""Shared-memory tools exposed to the agent."""

from __future__ import annotations

import logging

from pydantic_ai import RunContext

from friday.agent.deps import AgentDeps
from friday.domain.models import MemoryKind, MemoryScope
from friday.domain.permissions import clip

__all__ = ['list_memories', 'save_memory', 'search_memory']

log = logging.getLogger(__name__)


def _workspace_key(ctx: RunContext[AgentDeps]) -> str:
    return ctx.deps.context.repo_root.resolve().as_posix()


async def search_memory(ctx: RunContext[AgentDeps], query: str) -> str:
    """Search shared memory and indexed chat snippets for relevant context."""
    log.debug('tool search_memory: query=%s', query)
    if ctx.deps.memory_store is None:
        return 'shared memory is unavailable'

    results = ctx.deps.memory_store.search(
        query,
        workspace_key=_workspace_key(ctx),
        current_session_id=ctx.deps.session_id,
        limit=max(4, ctx.deps.settings.memory_top_k),
    )
    if not results:
        return 'no shared memory matches'

    lines: list[str] = []
    for result in results:
        header = f'[{result.source}] score={result.score:.2f}'
        if result.source == 'memory':
            scope = result.scope.value if result.scope is not None else '-'
            kind = result.kind.value if result.kind is not None else '-'
            header = f'{header} scope={scope} kind={kind}'
        if result.session_id:
            header = f'{header} session={result.session_id}'
        lines.append(header)
        lines.append(clip(result.snippet, 320))
        lines.append('')
    return '\n'.join(lines).strip()


async def save_memory(
    ctx: RunContext[AgentDeps],
    text: str,
    kind: MemoryKind = MemoryKind.NOTE,
    scope: MemoryScope = MemoryScope.GLOBAL,
    pinned: bool = False,
) -> str:
    """Save durable shared memory for future chats."""
    log.debug(
        'tool save_memory: kind=%s scope=%s pinned=%s text=%s',
        kind.value,
        scope.value,
        pinned,
        clip(text, 120),
    )
    if ctx.deps.memory_store is None:
        return 'shared memory is unavailable'

    record, created = ctx.deps.memory_store.save_memory(
        text,
        kind=kind,
        scope=scope,
        workspace_key=_workspace_key(ctx),
        pinned=pinned,
    )
    ctx.deps.memory.remember(ctx.deps.memory.notes, f'memory:{record.id}', 8)
    action = 'saved' if created else 'updated'
    return f'{action} memory {record.id} ({record.scope.value}/{record.kind.value})'


async def list_memories(
    ctx: RunContext[AgentDeps],
    limit: int = 20,
    scope: MemoryScope | None = None,
) -> str:
    """List saved shared memories visible from the current repo."""
    log.debug('tool list_memories: limit=%s scope=%s', limit, scope)
    if ctx.deps.memory_store is None:
        return 'shared memory is unavailable'

    records = ctx.deps.memory_store.list_memories(
        workspace_key=_workspace_key(ctx),
        limit=min(limit, 50),
        scope=scope,
    )
    if not records:
        return 'no shared memories saved'

    return '\n'.join(
        f'{record.id} [{record.scope.value}/{record.kind.value}] {clip(record.text, 180)}'
        for record in records
    )
