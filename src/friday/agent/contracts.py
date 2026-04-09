"""Structured agent output contracts."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field
from pydantic_ai.tools import DeferredToolRequests

from friday.domain.models import AgentMode

__all__ = [
    'AgentReply',
    'ReplyStatus',
    'RouterDecision',
    'RouterDecisionAction',
    'TurnOutput',
]


class ReplyStatus(StrEnum):
    SUCCESS = 'success'
    BLOCKED = 'blocked'
    FAILED = 'failed'
    INFO = 'info'


class AgentReply(BaseModel):
    """Final structured response produced by Friday agents."""

    markdown: str
    status: ReplyStatus = ReplyStatus.SUCCESS
    changed_files: list[str] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class RouterDecisionAction(StrEnum):
    RESPOND = 'respond'
    DELEGATE = 'delegate'


class RouterDecision(BaseModel):
    """Structured auto-mode routing decision produced by the LLM."""

    action: RouterDecisionAction
    reply: str = ''
    delegate_mode: AgentMode | None = None
    task: str = ''


type TurnOutput = AgentReply | DeferredToolRequests
