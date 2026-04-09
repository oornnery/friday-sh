"""Agent dependencies — shared by core, router, and tools."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from friday.agent.context import WorkspaceContext
from friday.agent.stats import TurnStats
from friday.domain.models import WorkingMemory
from friday.infra.config import FridaySettings
from friday.infra.memory import MemoryStore, SharedMemorySnapshot


@dataclass(slots=True)
class AgentDeps:
    """Dependencies injected into every tool call via RunContext."""

    workspace_root: Path
    context: WorkspaceContext
    settings: FridaySettings
    memory: WorkingMemory = field(default_factory=WorkingMemory)
    memory_store: MemoryStore | None = None
    shared_memory: SharedMemorySnapshot = field(default_factory=SharedMemorySnapshot)
    session_id: str | None = None
    interactive: bool = True
    before_approval: Callable[[], None] | None = None
    after_approval: Callable[[], None] | None = None
    turn_stats: TurnStats = field(default_factory=TurnStats)
