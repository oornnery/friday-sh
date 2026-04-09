"""Mode configurations loaded from Markdown prompt files with frontmatter."""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from friday.domain.models import AgentMode

__all__ = ['MODE_CONFIGS', 'ModePromptConfig', 'load_mode', 'load_prompt']

_PROMPTS_DIR = Path(__file__).parent / 'prompts'
_FRONTMATTER_RE = re.compile(r'\A---\s*\n(?P<meta>.*?)\n---\s*\n(?P<body>.*)', re.DOTALL)

_PROMPT_FILES: dict[AgentMode, str] = {
    AgentMode.AUTO: 'router.md',
    AgentMode.CODE: 'code.md',
    AgentMode.READER: 'reader.md',
    AgentMode.WRITE: 'writer.md',
    AgentMode.DEBUG: 'debug.md',
}


class ModePromptConfig(BaseModel):
    """Validated mode configuration parsed from prompt frontmatter."""

    name: str
    description: str = ''
    tools: tuple[str, ...] = ()
    max_steps: int = 25
    model: str | None = None
    provider: str | None = None
    thinking: bool = False
    system_prompt: str = Field(default='', exclude=True)


def _parse_prompt_file(path: Path) -> ModePromptConfig:
    raw = path.read_text(encoding='utf-8')
    match = _FRONTMATTER_RE.match(raw)
    if match is None:
        return ModePromptConfig(name=path.stem, system_prompt=raw.strip())

    meta = yaml.safe_load(match.group('meta')) or {}
    meta['system_prompt'] = match.group('body').strip()
    return ModePromptConfig.model_validate(meta)


def load_mode(mode: AgentMode) -> ModePromptConfig:
    filename = _PROMPT_FILES[mode]
    return _parse_prompt_file(_PROMPTS_DIR / filename)


def load_prompt(mode: AgentMode) -> str:
    return load_mode(mode).system_prompt


MODE_CONFIGS: dict[AgentMode, ModePromptConfig] = {mode: load_mode(mode) for mode in AgentMode}
