"""Runtime context — immutable snapshot of the workspace and shell state."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from friday.domain.permissions import sanitize_for_prompt

ANCHOR_FILES = ('AGENTS.md', 'CLAUDE.md', 'README.md', 'pyproject.toml', 'package.json')
DOC_SNIPPET_LIMIT = 1200


def _git(args: list[str], cwd: Path, fallback: str = '') -> str:
    """Run git silently. Return stdout or *fallback* on any failure."""
    try:
        result = subprocess.run(
            ['git', *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return fallback
    return result.stdout.strip() or fallback


@dataclass(frozen=True, slots=True)
class WorkspaceContext:
    """Immutable snapshot of the current workspace for the agent's system prompt."""

    cwd: Path
    repo_root: Path
    branch: str
    status: str
    recent_commits: tuple[str, ...]
    project_docs: dict[str, str] = field(default_factory=dict)
    shell_env: dict[str, str] = field(default_factory=dict)

    @classmethod
    def discover(cls, cwd: Path | None = None) -> WorkspaceContext:
        cwd = (cwd or Path.cwd()).resolve()
        repo_root = Path(_git(['rev-parse', '--show-toplevel'], cwd, str(cwd))).resolve()

        docs: dict[str, str] = {}
        for name in ANCHOR_FILES:
            path = repo_root / name
            if path.is_file():
                text = path.read_text(encoding='utf-8', errors='replace')
                docs[name] = text[:DOC_SNIPPET_LIMIT]

        # Shell state from ZSH plugin hooks — sanitized to avoid leaking secrets
        shell_env: dict[str, str] = {}
        last_exit = os.environ.get('FRIDAY_LAST_EXIT')
        if last_exit:
            shell_env['FRIDAY_LAST_EXIT'] = last_exit[:10]
        last_cmd = os.environ.get('FRIDAY_LAST_CMD')
        if last_cmd:
            shell_env['FRIDAY_LAST_CMD'] = sanitize_for_prompt(last_cmd, limit=200)

        return cls(
            cwd=cwd,
            repo_root=repo_root,
            branch=_git(['branch', '--show-current'], cwd, '-'),
            status=_git(['status', '--short'], cwd, 'clean'),
            recent_commits=tuple(_git(['log', '--oneline', '-5'], cwd).splitlines()),
            project_docs=docs,
            shell_env=shell_env,
        )

    def render(self) -> str:
        commits = '\n'.join(f'  - {c}' for c in self.recent_commits) or '  - none'
        docs = '\n'.join(f'## {name}\n{body}' for name, body in self.project_docs.items())
        parts = [
            f'cwd: {self.cwd}',
            f'repo_root: {self.repo_root}',
            f'branch: {self.branch}',
            f'status:\n{self.status}',
            f'recent_commits:\n{commits}',
        ]
        if self.shell_env:
            env = ', '.join(f'{k}={v}' for k, v in self.shell_env.items())
            parts.append(f'shell: {env}')
        if docs:
            parts.append(f'project_docs:\n{docs}')
        return '\n'.join(parts)

    def render_summary(self) -> str:
        """Compact workspace summary for routing turns and small-talk requests."""
        parts = [
            f'cwd: {self.cwd}',
            f'repo_root: {self.repo_root}',
            f'branch: {self.branch}',
        ]
        if self.shell_env:
            env = ', '.join(f'{k}={v}' for k, v in self.shell_env.items())
            parts.append(f'shell: {env}')
        return '\n'.join(parts)
