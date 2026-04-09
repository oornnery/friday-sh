"""Shared-memory orchestration for prompt retrieval and auto-promotion."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from friday.agent.deps import AgentDeps
from friday.domain.models import MemoryKind, MemoryScope
from friday.domain.permissions import clip
from friday.infra.memory import MemorySearchResult, SharedMemorySnapshot

__all__ = [
    'MemoryCandidate',
    'load_relevant_shared_memory',
    'record_completed_turn',
    'sync_shared_memory_to_working_memory',
]

log = logging.getLogger(__name__)

_SECRET_RE = re.compile(
    r'\b(api[_ -]?key|token|secret|password|passwd|senha|chave)\b',
    re.IGNORECASE,
)
_NAME_RE = re.compile(
    r'\b(?:meu nome (?:e|é)|me chamo|my name is|i am)\s+([A-Za-zÀ-ÿ][\wÀ-ÿ\'-]*)',
    re.IGNORECASE,
)
_PREFERENCE_RE = re.compile(
    r'\b(?:eu prefiro|prefiro|i prefer)\s+(.+)$',
    re.IGNORECASE,
)
_PROJECT_DECISION_MARKERS = (
    'vamos usar',
    "we'll use",
    'we will use',
    'neste projeto',
    'nesse projeto',
    'no projeto',
    'for this project',
)
_GLOBAL_WORKFLOW_MARKERS = (
    'sempre ',
    'always ',
    'por padrão',
    'por padrao',
    'default to',
    'use essa mesma lógica',
    'use essa mesma logica',
    'use this same logic',
)
_STICKY_MEMORY_KINDS = frozenset(
    {
        MemoryKind.PROFILE,
        MemoryKind.PREFERENCE,
        MemoryKind.WORKFLOW,
        MemoryKind.DECISION,
        MemoryKind.PROJECT_FACT,
    }
)


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    """Structured candidate produced by the conservative memory heuristics."""

    text: str
    kind: MemoryKind
    scope: MemoryScope
    pinned: bool = True
    entity: str = ''
    decision: str = ''
    note: str = ''


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
    """Persist the useful parts of a completed top-level turn."""
    if deps.memory_store is None:
        return

    workspace_key = deps.context.repo_root.resolve().as_posix()
    sensitive_turn = _SECRET_RE.search(user_prompt) is not None

    if record_chat_chunk and deps.session_id and not sensitive_turn:
        log.debug('indexing chat turn for shared memory: session=%s', deps.session_id)
        deps.memory_store.index_chat_turn(
            session_id=deps.session_id,
            workspace_key=workspace_key,
            user_prompt=user_prompt,
            assistant_reply=reply_markdown,
        )

    if sensitive_turn or not deps.settings.memory_auto_promote:
        log.debug(
            'skipping auto-promotion: sensitive=%s auto_promote=%s',
            sensitive_turn,
            deps.settings.memory_auto_promote,
        )
        return

    for candidate in _extract_candidates(user_prompt):
        log.debug(
            'auto-promoting memory: kind=%s scope=%s text=%s',
            candidate.kind.value,
            candidate.scope.value,
            clip(candidate.text, 120),
        )
        deps.memory_store.save_memory(
            candidate.text,
            kind=candidate.kind,
            scope=candidate.scope,
            workspace_key=workspace_key,
            pinned=candidate.pinned,
        )
        if candidate.entity:
            deps.memory.remember(deps.memory.entities, candidate.entity, 6)
        if candidate.decision:
            deps.memory.remember(deps.memory.decisions, candidate.decision, 6)
        if candidate.note:
            deps.memory.remember(deps.memory.notes, candidate.note, 8)


def _extract_candidates(user_prompt: str) -> list[MemoryCandidate]:
    text = user_prompt.strip()
    lower_text = text.casefold()
    if not text or _SECRET_RE.search(lower_text):
        return []

    candidates: list[MemoryCandidate] = []

    if match := _NAME_RE.search(text):
        name = _normalize_person_name(match.group(1).strip().strip('.,!?:;'))
        candidates.append(
            MemoryCandidate(
                text=f'Nome do usuário / user name: {name}.',
                kind=MemoryKind.PROFILE,
                scope=MemoryScope.GLOBAL,
                entity=f'user_name={name}',
            )
        )

    if match := _PREFERENCE_RE.search(text):
        preference = _clean_sentence(match.group(1))
        if preference:
            candidates.append(
                MemoryCandidate(
                    text=f'Preferência do usuário / user preference: {preference}.',
                    kind=MemoryKind.PREFERENCE,
                    scope=MemoryScope.GLOBAL,
                    note=f'preference: {preference}',
                )
            )

    if any(marker in lower_text for marker in _PROJECT_DECISION_MARKERS):
        decision = clip(_clean_sentence(text), 220)
        if decision:
            candidates.append(
                MemoryCandidate(
                    text=f'Project decision: {decision}.',
                    kind=MemoryKind.DECISION,
                    scope=MemoryScope.REPO,
                    decision=decision,
                )
            )
    elif any(marker in lower_text for marker in _GLOBAL_WORKFLOW_MARKERS):
        workflow = clip(_clean_sentence(text), 220)
        if workflow:
            candidates.append(
                MemoryCandidate(
                    text=f'Workflow preference: {workflow}.',
                    kind=MemoryKind.WORKFLOW,
                    scope=MemoryScope.GLOBAL,
                    note=f'workflow: {workflow}',
                )
            )

    return _dedupe_candidates(candidates)


def _clean_sentence(text: str) -> str:
    cleaned = ' '.join(text.strip().split())
    return cleaned.strip(' .')


def _normalize_person_name(name: str) -> str:
    if name.islower():
        return name.title()
    return name


def _dedupe_candidates(candidates: list[MemoryCandidate]) -> list[MemoryCandidate]:
    seen: set[tuple[str, MemoryKind, MemoryScope]] = set()
    unique: list[MemoryCandidate] = []
    for candidate in candidates:
        key = (candidate.text.casefold(), candidate.kind, candidate.scope)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


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
