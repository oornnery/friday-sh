"""Domain models used across the Friday runtime and CLI."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

__all__ = [
    'SPECIALIST_MODES',
    'AgentMode',
    'ApprovalPolicy',
    'MemoryKind',
    'MemoryScope',
    'WorkingMemory',
]


class AgentMode(StrEnum):
    AUTO = 'auto'
    CODE = 'code'
    READER = 'reader'
    WRITE = 'write'
    DEBUG = 'debug'


SPECIALIST_MODES: tuple[AgentMode, ...] = (
    AgentMode.CODE,
    AgentMode.READER,
    AgentMode.WRITE,
    AgentMode.DEBUG,
)


class ApprovalPolicy(StrEnum):
    ASK = 'ask'
    AUTO = 'auto'
    NEVER = 'never'


class MemoryScope(StrEnum):
    GLOBAL = 'global'
    REPO = 'repo'


class MemoryKind(StrEnum):
    PROFILE = 'profile'
    PREFERENCE = 'preference'
    PROJECT_FACT = 'project_fact'
    DECISION = 'decision'
    WORKFLOW = 'workflow'
    NOTE = 'note'


@dataclass(slots=True)
class WorkingMemory:
    """Small deterministic memory rendered into agent instructions."""

    task: str = ''
    files: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    mode: AgentMode = AgentMode.AUTO

    def remember(self, bucket: list[str], item: str, limit: int) -> None:
        if not item:
            return
        if item in bucket:
            bucket.remove(item)
        bucket.append(item)
        del bucket[:-limit]

    def reset(self, *, mode: AgentMode | None = None) -> None:
        self.task = ''
        self.files.clear()
        self.notes.clear()
        self.entities.clear()
        self.decisions.clear()
        if mode is not None:
            self.mode = mode

    def render(self) -> str:
        files = ', '.join(self.files) or '-'
        notes_text = '\n'.join(f'  - {note}' for note in self.notes) or '  - none'
        entities_text = '\n'.join(f'  - {entity}' for entity in self.entities) or '  - none'
        decisions_text = '\n'.join(f'  - {decision}' for decision in self.decisions) or '  - none'
        return (
            f'task: {self.task or "-"}\n'
            f'mode: {self.mode}\n'
            f'files: {files}\n'
            f'notes:\n{notes_text}\n'
            f'entities:\n{entities_text}\n'
            f'decisions:\n{decisions_text}'
        )
