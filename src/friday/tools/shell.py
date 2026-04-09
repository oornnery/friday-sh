"""Shell tool — run commands with timeout and containment."""

from __future__ import annotations

import logging
import subprocess

from pydantic_ai import RunContext

from friday.agent.deps import AgentDeps
from friday.domain.permissions import clip

log = logging.getLogger(__name__)


async def run_shell(ctx: RunContext[AgentDeps], command: str, timeout: int = 30) -> str:
    """Run a shell command in the workspace root. Timeout in seconds (max 120)."""
    timeout = min(timeout, 120)
    log.debug('tool run_shell: timeout=%s command=%s', timeout, command)
    ctx.deps.memory.remember(ctx.deps.memory.notes, f'shell: {command}', 8)
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
        return clip(f'{exit_info}\n{output.strip()}')
    except subprocess.TimeoutExpired:
        return f'error: command timed out after {timeout}s'
