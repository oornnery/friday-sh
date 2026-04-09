"""Shared-memory orchestration — retrieval, injection, and chat indexing.

Memory promotion is handled by the agent via the save_memory tool,
not by heuristic regex patterns. The harness only manages retrieval
and chat-chunk indexing.
"""

from __future__ import annotations

import logging

from friday.agent.deps import AgentDeps
from friday.domain.models import MemoryKind, MemoryScope
from friday.domain.permissions import clip, contains_secret
from friday.infra.memory import MemorySearchResult, SharedMemorySnapshot

__all__ = [
    'load_relevant_shared_memory',
    'record_completed_turn',
    'sync_shared_memory_to_working_memory',
]

log = logging.getLogger(__name__)

_STICKY_MEMORY_KINDS = frozenset(
    {
        MemoryKind.PROFILE,
        MemoryKind.PREFERENCE,
        MemoryKind.WORKFLOW,
        MemoryKind.DECISION,
        MemoryKind.PROJECT_FACT,
    }
)


def load_relevant_shared_memory(deps: AgentDeps, user_prompt: str) -> SharedMemorySnapshot:
    """Query cross-chat memory for the current top-level user prompt."""
    if deps.memory_store is None or deps.settings.memory_top_k <= 0:
        return SharedMemorySnapshot()

    workspace_key = deps.context.repo_root.resolve().as_posix()
    half = max(1, deps.settings.memory_top_k // 2)
    retrieved = deps.memory_store.select_prompt_snapshot(
        user_prompt,
        workspace_key=workspace_key,
        current_session_id=deps.session_id,
        memory_limit=half,
        chat_limit=max(1, deps.settings.memory_top_k - half),
    )
    sticky = _sticky_memory_records(deps, workspace_key, limit=half)
    records = _merge_memory_results(sticky, retrieved.records, limit=half + 1)
    snapshot = SharedMemorySnapshot(records=records, chats=retrieved.chats)
    log.debug(
        'shared memory lookup: session=%s prompt=%s records=%s chats=%s',
        deps.session_id,
        clip(user_prompt, 120),
        len(snapshot.records),
        len(snapshot.chats),
    )
    return snapshot


def sync_shared_memory_to_working_memory(deps: AgentDeps) -> None:
    """Mirror the highest-signal shared-memory hits into short-term working memory."""
    for result in deps.shared_memory.records[:3]:
        snippet = clip(result.snippet, 120)
        if result.kind is MemoryKind.PROFILE:
            deps.memory.remember(deps.memory.entities, f'shared profile: {snippet}', 6)
            continue
        if result.kind in {MemoryKind.DECISION, MemoryKind.PROJECT_FACT}:
            deps.memory.remember(deps.memory.decisions, f'shared decision: {snippet}', 6)
            continue
        deps.memory.remember(deps.memory.notes, f'shared memory: {snippet}', 8)

    for result in deps.shared_memory.chats[:2]:
        deps.memory.remember(
            deps.memory.notes,
            f'shared chat: {clip(result.snippet, 120)}',
            8,
        )


def record_completed_turn(
    deps: AgentDeps,
    *,
    user_prompt: str,
    reply_markdown: str,
    record_chat_chunk: bool,
) -> None:
    """Index the completed turn for cross-chat search.

    Memory promotion (deciding what facts to save long-term) is the
    agent's job via save_memory — the harness does not try to parse
    user intent with regex.
    """
    if deps.memory_store is None:
        return

    workspace_key = deps.context.repo_root.resolve().as_posix()

    if record_chat_chunk and deps.session_id and not contains_secret(user_prompt):
        log.debug('indexing chat turn: session=%s', deps.session_id)
        deps.memory_store.index_chat_turn(
            session_id=deps.session_id,
            workspace_key=workspace_key,
            user_prompt=user_prompt,
            assistant_reply=reply_markdown,
        )


# ── Internal helpers ───────────────────────────────────────────


def _sticky_memory_records(
    deps: AgentDeps,
    workspace_key: str,
    *,
    limit: int,
) -> list[MemorySearchResult]:
    if deps.memory_store is None:
        return []

    records = deps.memory_store.list_memories(
        workspace_key=workspace_key,
        limit=max(limit * 4, 12),
    )
    sticky: list[MemorySearchResult] = []
    for record in records:
        if not record.pinned or record.kind not in _STICKY_MEMORY_KINDS:
            continue
        score = 5.0
        if record.scope is MemoryScope.REPO:
            score += 0.5
        sticky.append(
            MemorySearchResult(
                id=record.id,
                source='memory',
                score=score,
                snippet=record.text,
                workspace_key=record.workspace_key,
                created_at=record.created_at,
                scope=record.scope,
                kind=record.kind,
                pinned=record.pinned,
            )
        )
        if len(sticky) >= limit:
            break
    return sticky


def _merge_memory_results(
    sticky: list[MemorySearchResult],
    retrieved: list[MemorySearchResult],
    *,
    limit: int,
) -> list[MemorySearchResult]:
    merged: list[MemorySearchResult] = []
    seen: set[str] = set()
    for item in [*sticky, *retrieved]:
        if item.id in seen:
            continue
        seen.add(item.id)
        merged.append(item)
        if len(merged) >= limit:
            break
    return merged
