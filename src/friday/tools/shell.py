"""Shell tool — run commands with timeout, output cap, and input validation."""

from __future__ import annotations

import logging
import subprocess

from pydantic_ai import RunContext

from friday.agent.deps import AgentDeps
from friday.domain.permissions import clip
from friday.domain.validation import MAX_COMMAND_LENGTH, validate_command

log = logging.getLogger(__name__)

MAX_SHELL_OUTPUT = 8000


async def run_shell(ctx: RunContext[AgentDeps], command: str, timeout: int = 30) -> str:
    """Run a shell command in the workspace root. Timeout in seconds (max 120)."""
    try:
        validate_command(command)
    except ValueError:
        return f'error: command too long (max {MAX_COMMAND_LENGTH} chars)'

    timeout = min(timeout, 120)
    log.info(
        'run_shell: cwd=%s timeout=%s command=%s',
        ctx.deps.workspace_root,
        timeout,
        clip(command, 200),
    )
    ctx.deps.memory.remember(ctx.deps.memory.notes, f'shell: {clip(command, 80)}', 8)

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=ctx.deps.workspace_root,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        output = result.stdout + result.stderr
        exit_info = f'[exit {result.returncode}]'
        return clip(f'{exit_info}\n{output.strip()}', MAX_SHELL_OUTPUT)
    except subprocess.TimeoutExpired:
        return f'error: command timed out after {timeout}s'
