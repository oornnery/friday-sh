"""Tests for the unified agent runtime."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.output import DeferredToolRequests
from pydantic_ai.tools import ToolDenied
from pydantic_ai.toolsets import FunctionToolset
from pydantic_ai.usage import RunUsage

from friday.agent.contracts import AgentReply, RouterDecision, RouterDecisionAction
from friday.agent.core import _prepare_turn, create_agent, execute_agent
from friday.agent.deps import AgentDeps
from friday.agent.memory import record_completed_turn
from friday.agent.modes import MODE_CONFIGS
from friday.domain.models import AgentMode, MemoryKind, MemoryScope
from friday.infra.config import FridaySettings
from friday.infra.memory import SQLiteMemoryStore


class FakeRunResult:
    """Small stand-in for a pydantic-ai run result."""

    def __init__(self, output) -> None:
        self.output = output
        self.response = SimpleNamespace(
            model_name='test-model',
            provider_name='test',
            provider_details=None,
        )

    def usage(self) -> RunUsage:
        return RunUsage()

    def all_messages(self) -> list:
        return []


class FakeAgent:
    """Agent stub that yields a deferred approval first, then a final reply."""

    def __init__(self, call: ToolCallPart) -> None:
        self.call = call
        self.calls: list[dict] = []

    async def run(self, user_prompt, **kwargs):
        self.calls.append({'user_prompt': user_prompt, **kwargs})
        if len(self.calls) == 1:
            return FakeRunResult(DeferredToolRequests(approvals=[self.call]))
        return FakeRunResult(AgentReply(markdown='done'))


def _settings(tmp_path: Path, **updates) -> FridaySettings:
    settings = FridaySettings(
        default_model='anthropic:claude-sonnet-4-20250514',
        session_dir=tmp_path / 'sessions',
        config_dir=tmp_path / 'config',
        **updates,
    )
    settings.resolve_paths()
    return settings


def _deps(tmp_path: Path, settings: FridaySettings, mode: AgentMode = AgentMode.AUTO) -> AgentDeps:
    deps = AgentDeps(
        workspace_root=tmp_path,
        context=SimpleNamespace(repo_root=tmp_path, render=lambda: 'workspace'),
        settings=settings,
        memory_store=SQLiteMemoryStore(settings.memory_db_path),
        session_id='session-1',
        interactive=True,
    )
    deps.memory.mode = mode
    return deps


def test_execute_agent_auto_approves_deferred_tools(tmp_path: Path) -> None:
    call = ToolCallPart('run_shell', {'command': 'echo hi'})
    agent = FakeAgent(call)
    deps = _deps(tmp_path, _settings(tmp_path, approval_policy='auto'), mode=AgentMode.DEBUG)

    executed = asyncio.run(
        execute_agent(
            agent,
            deps=deps,
            user_prompt='test',
            requested_model=deps.settings.default_model,
        )
    )

    assert executed.reply.markdown == 'done'
    assert agent.calls[1]['deferred_tool_results'].approvals[call.tool_call_id] is True


def test_execute_agent_never_policy_denies_deferred_tools(tmp_path: Path) -> None:
    call = ToolCallPart('run_shell', {'command': 'echo hi'})
    agent = FakeAgent(call)
    deps = _deps(tmp_path, _settings(tmp_path, approval_policy='never'), mode=AgentMode.DEBUG)

    executed = asyncio.run(
        execute_agent(
            agent,
            deps=deps,
            user_prompt='test',
            requested_model=deps.settings.default_model,
        )
    )

    denied = agent.calls[1]['deferred_tool_results'].approvals[call.tool_call_id]
    assert executed.reply.markdown == 'done'
    assert isinstance(denied, ToolDenied)


def test_execute_agent_pauses_status_around_interactive_approval(
    monkeypatch,
    tmp_path: Path,
) -> None:
    call = ToolCallPart('run_shell', {'command': 'echo hi'})
    agent = FakeAgent(call)
    deps = _deps(tmp_path, _settings(tmp_path, approval_policy='ask'), mode=AgentMode.DEBUG)
    events: list[str] = []
    deps.before_approval = lambda: events.append('stop')
    deps.after_approval = lambda: events.append('start')
    monkeypatch.setattr('friday.agent.core.confirm_deferred_tool', lambda deferred_call: True)

    executed = asyncio.run(
        execute_agent(
            agent,
            deps=deps,
            user_prompt='test',
            requested_model=deps.settings.default_model,
        )
    )

    assert executed.reply.markdown == 'done'
    assert events == ['stop', 'start']


def test_execute_agent_passes_mode_usage_limits(tmp_path: Path) -> None:
    call = ToolCallPart('run_shell', {'command': 'echo hi'})
    agent = FakeAgent(call)
    settings = _settings(tmp_path, max_steps=3, approval_policy='auto')
    deps = _deps(tmp_path, settings, mode=AgentMode.DEBUG)

    asyncio.run(
        execute_agent(
            agent,
            deps=deps,
            user_prompt='test',
            requested_model=settings.default_model,
        )
    )

    limits = agent.calls[0]['usage_limits']
    expected_steps = min(settings.max_steps, MODE_CONFIGS[AgentMode.DEBUG].max_steps)

    assert limits.tool_calls_limit == expected_steps
    assert limits.request_limit == expected_steps + 5


def test_execute_agent_auto_mode_can_answer_directly_without_tools(
    monkeypatch,
    tmp_path: Path,
) -> None:
    deps = _deps(tmp_path, _settings(tmp_path), mode=AgentMode.AUTO)
    monkeypatch.setattr(
        'friday.agent.core._resolve_model',
        lambda model_name, settings: TestModel(),
    )
    agent = create_agent(AgentMode.AUTO, deps.settings, deps.context)

    async def fake_run(user_prompt, **kwargs):
        return FakeRunResult(
            RouterDecision(
                action=RouterDecisionAction.RESPOND,
                reply='Oi! Como posso ajudar?',
            )
        )

    agent.run = fake_run  # type: ignore[method-assign]

    executed = asyncio.run(
        execute_agent(
            agent,
            deps=deps,
            user_prompt='oi',
            requested_model=deps.settings.default_model,
        )
    )

    assert executed.reply.markdown == 'Oi! Como posso ajudar?'
    assert len(executed.messages) == 2


def test_execute_agent_auto_mode_direct_reply_still_saves_memory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    deps = _deps(tmp_path, _settings(tmp_path), mode=AgentMode.AUTO)
    monkeypatch.setattr(
        'friday.agent.core._resolve_model',
        lambda model_name, settings: TestModel(),
    )
    agent = create_agent(AgentMode.AUTO, deps.settings, deps.context)

    async def fake_run(user_prompt, **kwargs):
        return FakeRunResult(
            RouterDecision(
                action=RouterDecisionAction.RESPOND,
                reply='Prazer, Fabio. Vou lembrar disso.',
            )
        )

    agent.run = fake_run  # type: ignore[method-assign]

    executed = asyncio.run(
        execute_agent(
            agent,
            deps=deps,
            user_prompt='meu nome e Fabio',
            requested_model=deps.settings.default_model,
        )
    )

    assert 'Fabio' in executed.reply.markdown
    # Memory promotion is now the agent's job via save_memory tool, not regex.
    # The harness only indexes the chat chunk for cross-chat search.
    results = deps.memory_store.search(
        'Fabio',
        workspace_key=tmp_path.as_posix(),
        current_session_id='other',
        limit=5,
    )
    assert any('Fabio' in r.snippet for r in results)


def test_execute_agent_auto_delegate_keeps_user_visible_history(
    monkeypatch,
    tmp_path: Path,
) -> None:
    deps = _deps(tmp_path, _settings(tmp_path), mode=AgentMode.AUTO)
    monkeypatch.setattr(
        'friday.agent.core._resolve_model',
        lambda model_name, settings: TestModel(),
    )
    agent = create_agent(AgentMode.AUTO, deps.settings, deps.context)

    async def fake_run(user_prompt, **kwargs):
        return FakeRunResult(
            RouterDecision(
                action=RouterDecisionAction.DELEGATE,
                delegate_mode=AgentMode.READER,
                task='Inspect the repo and answer the question.',
            )
        )

    async def fake_specialist_runner(
        deps,
        *,
        delegate_mode,
        delegate_task,
        message_history,
        usage,
        requested_model,
    ):
        return SimpleNamespace(
            reply=AgentReply(markdown='Resposta final do especialista.'),
            messages=[ModelRequest.user_text_prompt(delegate_task)],
        )

    agent.run = fake_run  # type: ignore[method-assign]
    monkeypatch.setattr('friday.agent.core._run_specialist_from_auto', fake_specialist_runner)

    executed = asyncio.run(
        execute_agent(
            agent,
            deps=deps,
            user_prompt='Quem sou eu?',
            requested_model=deps.settings.default_model,
        )
    )

    request = executed.messages[-2]
    assert isinstance(request, ModelRequest)
    assert request.parts[0].content == 'Quem sou eu?'
    assert executed.reply.markdown == 'Resposta final do especialista.'


def test_create_agent_includes_mcp_toolsets(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    context = SimpleNamespace(repo_root=tmp_path, render=lambda: 'workspace')
    sentinel_toolset = FunctionToolset(id='mcp-sentinel')
    monkeypatch.setattr(
        'friday.agent.core._resolve_model',
        lambda model_name, settings: TestModel(),
    )
    monkeypatch.setattr('friday.agent.core.create_mcp_servers', lambda configs: [sentinel_toolset])

    agent = create_agent(AgentMode.READER, settings, context)

    assert sentinel_toolset in agent.toolsets


def test_create_auto_agent_has_no_runtime_toolsets(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    context = SimpleNamespace(repo_root=tmp_path, render=lambda: 'workspace')
    monkeypatch.setattr(
        'friday.agent.core._resolve_model',
        lambda model_name, settings: TestModel(),
    )
    monkeypatch.setattr('friday.agent.core.create_mcp_servers', lambda configs: [])

    agent = create_agent(AgentMode.AUTO, settings, context)
    toolset_ids = [toolset.id for toolset in agent.toolsets if hasattr(toolset, 'id')]

    assert toolset_ids == ['<agent>']
    assert 'shell-tools' not in toolset_ids
    assert 'filesystem-tools' not in toolset_ids
    assert 'filesystem-write-tools' not in toolset_ids
    assert 'memory-tools' not in toolset_ids


def test_create_agent_accepts_function_model(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    context = SimpleNamespace(repo_root=tmp_path, render=lambda: 'workspace')

    def function_model(messages, info):
        return ModelResponse(
            parts=[TextPart('ok')],
            model_name='fn-model',
            provider_name='function',
        )

    sentinel_model = FunctionModel(function_model)
    monkeypatch.setattr(
        'friday.agent.core._resolve_model',
        lambda model_name, settings: sentinel_model,
    )

    agent = create_agent(AgentMode.READER, settings, context)

    assert agent.model is sentinel_model


def test_prepare_turn_loads_relevant_shared_memory(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    deps = _deps(tmp_path, settings)
    deps.memory_store.save_memory(
        'User name is Fabio.',
        kind=MemoryKind.PROFILE,
        scope=MemoryScope.GLOBAL,
        workspace_key=tmp_path.as_posix(),
        pinned=True,
    )

    _prepare_turn(deps, 'Fabio')

    assert deps.memory.task == 'Fabio'
    assert deps.shared_memory.records
    assert 'Fabio' in deps.shared_memory.render()
    assert any('Fabio' in entity for entity in deps.memory.entities)


def test_record_completed_turn_indexes_chat_chunk(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    deps = _deps(tmp_path, settings)

    record_completed_turn(
        deps,
        user_prompt='meu nome e Fabio',
        reply_markdown='Prazer em te conhecer.',
        record_chat_chunk=True,
    )

    # Chat chunk should be indexed for cross-chat search
    results = deps.memory_store.search(
        'Fabio',
        workspace_key=tmp_path.as_posix(),
        current_session_id='other-session',
        limit=5,
    )
    assert any('Fabio' in r.snippet for r in results)
