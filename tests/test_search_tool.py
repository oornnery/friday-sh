"""Tests for the search filesystem tool."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from friday.domain.models import WorkingMemory


@dataclass
class FakeDeps:
    workspace_root: Path
    memory: WorkingMemory = field(default_factory=WorkingMemory)


def _make_ctx(workspace: Path) -> MagicMock:
    ctx = MagicMock()
    ctx.deps = FakeDeps(workspace_root=workspace)
    return ctx


class TestSearch:
    def test_finds_content(self, tmp_workspace: Path) -> None:
        from friday.tools.filesystem import search

        ctx = _make_ctx(tmp_workspace)
        result = asyncio.run(search(ctx, 'hello'))
        assert 'hello' in result

    def test_no_matches(self, tmp_workspace: Path) -> None:
        from friday.tools.filesystem import search

        ctx = _make_ctx(tmp_workspace)
        result = asyncio.run(search(ctx, 'nonexistent_string_xyz'))
        assert result == 'no matches'

    def test_rejects_traversal_in_pattern(self, tmp_workspace: Path) -> None:
        from friday.tools.filesystem import search

        ctx = _make_ctx(tmp_workspace)
        with pytest.raises(ValueError, match='must not contain'):
            asyncio.run(search(ctx, 'test', glob='../../**'))

    def test_rejects_long_pattern(self, tmp_workspace: Path) -> None:
        from friday.tools.filesystem import search

        ctx = _make_ctx(tmp_workspace)
        with pytest.raises(ValueError, match='pattern too long'):
            asyncio.run(search(ctx, 'x' * 300))
