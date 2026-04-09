"""Tests for WorkspaceContext — discovery and sanitization."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from friday.agent.context import WorkspaceContext


class TestWorkspaceContext:
    def test_discover_returns_valid_context(self, tmp_workspace: Path) -> None:
        ctx = WorkspaceContext.discover(tmp_workspace)
        assert ctx.cwd == tmp_workspace
        assert ctx.repo_root.is_dir()

    def test_discover_reads_project_docs(self, tmp_workspace: Path) -> None:
        (tmp_workspace / 'README.md').write_text('# Test')
        ctx = WorkspaceContext.discover(tmp_workspace)
        assert 'README.md' in ctx.project_docs

    def test_shell_env_sanitizes_secrets(self, tmp_workspace: Path) -> None:
        secret_cmd = 'curl -H "Bearer eyJsecrettoken" https://api.example.com'
        with patch.dict(os.environ, {'FRIDAY_LAST_CMD': secret_cmd}):
            ctx = WorkspaceContext.discover(tmp_workspace)
            last_cmd = ctx.shell_env.get('FRIDAY_LAST_CMD', '')
            assert 'eyJsecrettoken' not in last_cmd
            assert 'redacted' in last_cmd

    def test_shell_env_clips_exit_code(self, tmp_workspace: Path) -> None:
        with patch.dict(os.environ, {'FRIDAY_LAST_EXIT': '0'}):
            ctx = WorkspaceContext.discover(tmp_workspace)
            assert ctx.shell_env.get('FRIDAY_LAST_EXIT') == '0'

    def test_shell_env_clips_long_exit(self, tmp_workspace: Path) -> None:
        with patch.dict(os.environ, {'FRIDAY_LAST_EXIT': 'x' * 100}):
            ctx = WorkspaceContext.discover(tmp_workspace)
            assert len(ctx.shell_env.get('FRIDAY_LAST_EXIT', '')) <= 10

    def test_render_includes_branch(self, tmp_workspace: Path) -> None:
        ctx = WorkspaceContext.discover(tmp_workspace)
        rendered = ctx.render()
        assert 'branch:' in rendered

    def test_render_summary_is_compact(self, tmp_workspace: Path) -> None:
        ctx = WorkspaceContext.discover(tmp_workspace)
        summary = ctx.render_summary()
        assert 'cwd:' in summary
        assert 'recent_commits' not in summary
