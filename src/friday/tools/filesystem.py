"""Filesystem tools — read, write, patch, list, search."""

from __future__ import annotations

import logging
import subprocess

from pydantic_ai import RunContext

from friday.agent.deps import AgentDeps
from friday.domain.permissions import clip, safe_path

log = logging.getLogger(__name__)


async def read_file(ctx: RunContext[AgentDeps], path: str, start: int = 1, end: int = 200) -> str:
    """Read a UTF-8 file by line range."""
    log.debug('tool read_file: path=%s start=%s end=%s', path, start, end)
    resolved = safe_path(ctx.deps.workspace_root, path)
    ctx.deps.memory.remember(ctx.deps.memory.files, path, 8)
    lines = resolved.read_text(encoding='utf-8', errors='replace').splitlines()
    numbered = [f'{i:>4}: {line}' for i, line in enumerate(lines[start - 1 : end], start)]
    return '\n'.join(numbered)


async def write_file(ctx: RunContext[AgentDeps], path: str, content: str) -> str:
    """Write content to a file, creating parent directories as needed."""
    log.debug('tool write_file: path=%s chars=%s', path, len(content))
    resolved = safe_path(ctx.deps.workspace_root, path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding='utf-8')
    ctx.deps.memory.remember(ctx.deps.memory.files, path, 8)
    return f'wrote {len(content)} chars to {path}'


async def patch_file(ctx: RunContext[AgentDeps], path: str, old: str, new: str) -> str:
    """Replace an exact string in a file. Fails if old is not found or not unique."""
    log.debug('tool patch_file: path=%s old_chars=%s new_chars=%s', path, len(old), len(new))
    resolved = safe_path(ctx.deps.workspace_root, path)
    text = resolved.read_text(encoding='utf-8', errors='replace')
    count = text.count(old)
    if count == 0:
        return f'error: old string not found in {path}'
    if count > 1:
        return f'error: old string found {count} times in {path} — must be unique'

    resolved.write_text(text.replace(old, new, 1), encoding='utf-8')
    ctx.deps.memory.remember(ctx.deps.memory.files, path, 8)
    return f'patched {path}'


async def list_files(ctx: RunContext[AgentDeps], path: str = '.', pattern: str = '*') -> str:
    """List files matching a glob pattern relative to workspace root."""
    log.debug('tool list_files: path=%s pattern=%s', path, pattern)
    resolved = safe_path(ctx.deps.workspace_root, path)
    matches = sorted(resolved.glob(pattern))
    lines = [str(m.relative_to(ctx.deps.workspace_root)) for m in matches[:100]]
    if len(matches) > 100:
        lines.append(f'...[{len(matches) - 100} more]')
    return '\n'.join(lines) or 'no matches'


async def search(ctx: RunContext[AgentDeps], pattern: str, path: str = '.', glob: str = '') -> str:
    """Search file contents using ripgrep (falls back to grep)."""
    log.debug('tool search: pattern=%s path=%s glob=%s', pattern, path, glob)
    search_path = safe_path(ctx.deps.workspace_root, path)
    ctx.deps.memory.remember(ctx.deps.memory.files, str(path), 8)
    cmd: list[str] = [
        'rg',
        '--no-heading',
        '-n',
        '--max-count=50',
        pattern,
        str(search_path),
    ]
    if glob:
        cmd.insert(1, f'--glob={glob}')
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
        output = result.stdout.strip()
    except FileNotFoundError:
        cmd = ['grep', '-rn', '--max-count=50', pattern, str(search_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
        output = result.stdout.strip()
    return clip(output) if output else 'no matches'
