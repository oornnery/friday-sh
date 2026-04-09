"""Single-shot ask command backed by the unified Friday runtime."""

from __future__ import annotations

import asyncio
import sys

from pydantic_ai.exceptions import UserError
from rich.status import Status

from friday.agent.context import WorkspaceContext
from friday.agent.core import create_agent, execute_agent
from friday.agent.deps import AgentDeps
from friday.agent.stats import format_turn_summary
from friday.cli.output import console, print_error, print_info, print_markdown, print_run_summary
from friday.domain.models import AgentMode
from friday.infra.config import FridaySettings
from friday.infra.memory import SQLiteMemoryStore


def run_ask(
    question: str,
    mode: AgentMode | None,
    settings: FridaySettings,
) -> None:
    """Ask a single question and print the answer."""
    stdin_is_tty = sys.stdin.isatty()
    stdout_is_tty = sys.stdout.isatty()

    if not stdin_is_tty:
        stdin_content = sys.stdin.read().strip()
        if stdin_content:
            question = f'{question}\n\n```\n{stdin_content}\n```'

    selected_mode = mode or settings.default_mode
    context = WorkspaceContext.discover()
    deps = AgentDeps(
        workspace_root=context.repo_root,
        context=context,
        settings=settings,
        memory_store=SQLiteMemoryStore(settings.memory_db_path),
        interactive=stdin_is_tty and stdout_is_tty,
    )
    deps.memory.mode = selected_mode

    try:
        agent = create_agent(selected_mode, settings, context)
        deps.turn_stats.reset()
        with Status('Thinking...', console=console, spinner='dots') as status:
            if status is not None:
                deps.before_approval = status.stop
                deps.after_approval = status.start
            executed = asyncio.run(
                execute_agent(
                    agent,
                    deps=deps,
                    user_prompt=question,
                    requested_model=settings.default_model,
                )
            )
        print_markdown(executed.reply.markdown)
        print_run_summary(format_turn_summary(deps.turn_stats))
    except UserError as exc:
        print_error(f'{exc}')
        print_info(
            'Check your API keys in .env or use --model to pick another provider.\n'
            'List available models: friday models'
        )
    except KeyboardInterrupt:
        print_error('\nInterrupted.')
