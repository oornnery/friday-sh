"""Tests for filesystem tools."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock

import pytest

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


class TestReadFile:
    def test_reads_file_content(self, tmp_workspace: Path) -> None:
        from friday.tools.filesystem import read_file

        ctx = _make_ctx(tmp_workspace)
        result = asyncio.run(read_file(ctx, 'hello.py'))
        assert 'print("hello")' in result

    def test_line_numbers(self, tmp_workspace: Path) -> None:
        from friday.tools.filesystem import read_file

        (tmp_workspace / 'multi.txt').write_text('a\nb\nc\n')
        ctx = _make_ctx(tmp_workspace)
        result = asyncio.run(read_file(ctx, 'multi.txt', start=2, end=3))
        assert '2:' in result
        assert '3:' in result
        assert '1:' not in result

    def test_escape_raises(self, tmp_workspace: Path) -> None:
        from friday.tools.filesystem import read_file

        ctx = _make_ctx(tmp_workspace)
        with pytest.raises(PermissionError):
            asyncio.run(read_file(ctx, '../../../etc/passwd'))


class TestWriteFile:
    def test_creates_file(self, tmp_workspace: Path) -> None:
        from friday.tools.filesystem import write_file

        ctx = _make_ctx(tmp_workspace)
        result = asyncio.run(write_file(ctx, 'new.txt', 'hello'))
        assert 'wrote' in result
        assert (tmp_workspace / 'new.txt').read_text() == 'hello'

    def test_creates_parent_dirs(self, tmp_workspace: Path) -> None:
        from friday.tools.filesystem import write_file

        ctx = _make_ctx(tmp_workspace)
        asyncio.run(write_file(ctx, 'sub/dir/file.txt', 'nested'))
        assert (tmp_workspace / 'sub/dir/file.txt').read_text() == 'nested'


class TestPatchFile:
    def test_replaces_exact_match(self, tmp_workspace: Path) -> None:
        from friday.tools.filesystem import patch_file

        ctx = _make_ctx(tmp_workspace)
        result = asyncio.run(patch_file(ctx, 'hello.py', 'print("hello")', 'print("world")'))
        assert 'patched' in result
        assert 'print("world")' in (tmp_workspace / 'hello.py').read_text()

    def test_not_found(self, tmp_workspace: Path) -> None:
        from friday.tools.filesystem import patch_file

        ctx = _make_ctx(tmp_workspace)
        result = asyncio.run(patch_file(ctx, 'hello.py', 'nonexistent', 'x'))
        assert 'not found' in result


class TestListFiles:
    def test_lists_files(self, tmp_workspace: Path) -> None:
        from friday.tools.filesystem import list_files

        ctx = _make_ctx(tmp_workspace)
        result = asyncio.run(list_files(ctx))
        assert 'hello.py' in result
