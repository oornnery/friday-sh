"""Tests for the run_shell tool — timeout, output cap, input validation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock

from friday.domain.models import ApprovalPolicy, WorkingMemory


@dataclass
class FakeSettings:
    approval_policy: ApprovalPolicy = ApprovalPolicy.AUTO


@dataclass
class FakeDeps:
    workspace_root: Path
    settings: FakeSettings = field(default_factory=FakeSettings)
    memory: WorkingMemory = field(default_factory=WorkingMemory)


def _make_ctx(workspace: Path) -> MagicMock:
    ctx = MagicMock()
    ctx.deps = FakeDeps(workspace_root=workspace)
    return ctx


class TestRunShell:
    def test_runs_command_and_returns_output(self, tmp_workspace: Path) -> None:
        from friday.tools.shell import run_shell

        ctx = _make_ctx(tmp_workspace)
        result = asyncio.run(run_shell(ctx, 'echo hello'))
        assert '[exit 0]' in result
        assert 'hello' in result

    def test_captures_exit_code(self, tmp_workspace: Path) -> None:
        from friday.tools.shell import run_shell

        ctx = _make_ctx(tmp_workspace)
        result = asyncio.run(run_shell(ctx, 'exit 42'))
        assert '[exit 42]' in result

    def test_rejects_long_command(self, tmp_workspace: Path) -> None:
        from friday.tools.shell import run_shell

        ctx = _make_ctx(tmp_workspace)
        long_cmd = 'echo ' + 'x' * 3000
        result = asyncio.run(run_shell(ctx, long_cmd))
        assert 'error' in result
        assert 'too long' in result

    def test_output_is_clipped(self, tmp_workspace: Path) -> None:
        from friday.tools.shell import MAX_SHELL_OUTPUT, run_shell

        ctx = _make_ctx(tmp_workspace)
        # Generate lots of output
        result = asyncio.run(run_shell(ctx, 'seq 1 100000'))
        assert len(result) <= MAX_SHELL_OUTPUT + 200  # clip adds truncation message

    def test_timeout_returns_error(self, tmp_workspace: Path) -> None:
        from friday.tools.shell import run_shell

        ctx = _make_ctx(tmp_workspace)
        result = asyncio.run(run_shell(ctx, 'sleep 10', timeout=1))
        assert 'timed out' in result

    def test_remembers_command_in_memory(self, tmp_workspace: Path) -> None:
        from friday.tools.shell import run_shell

        ctx = _make_ctx(tmp_workspace)
        asyncio.run(run_shell(ctx, 'echo test'))
        assert any('shell:' in n for n in ctx.deps.memory.notes)
