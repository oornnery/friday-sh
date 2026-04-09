"""Application configuration via pydantic-settings."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

from friday.domain.models import AgentMode, ApprovalPolicy


class MCPServerConfig(BaseModel):
    """A single MCP server connection."""

    name: str
    transport: Literal['http', 'stdio'] = 'stdio'
    url: str = ''
    command: str = ''
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class FridaySettings(BaseSettings):
    """Global Friday configuration — TOML file + env vars."""

    model_config = SettingsConfigDict(
        env_prefix='FRIDAY_',
        env_file='.env',
        extra='ignore',
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            TomlConfigSettingsSource(
                settings_cls,
                toml_file=[
                    Path('~/.config/friday/config.toml').expanduser(),
                    'friday.toml',
                ],
            ),
        )

    # Model
    default_model: str = 'zai:glm-5-turbo'
    fallback_model: str = 'mistral:devstral-latest'

    # Z.AI (ZhipuAI / GLM) — OpenAI-compatible provider
    zai_api_key: str = ''
    zai_base_url: str = 'https://api.z.ai/api/coding/paas/v4'

    # Behavior
    default_mode: AgentMode = AgentMode.AUTO
    approval_policy: ApprovalPolicy = ApprovalPolicy.ASK
    max_steps: int = 25

    # Paths
    session_dir: Path = Path('~/.local/share/friday/sessions')
    config_dir: Path = Path('~/.config/friday')
    memory_db_path: Path = Path('memory.db')

    # Memory
    memory_top_k: int = 6
    memory_auto_promote: bool = True

    # MCP
    mcp_servers: list[MCPServerConfig] = Field(default_factory=list)

    def resolve_paths(self) -> None:
        """Expand ~ and ensure directories exist."""
        self.session_dir = self.session_dir.expanduser()
        self.config_dir = self.config_dir.expanduser()
        self.memory_db_path = self.memory_db_path.expanduser()
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        if not self.memory_db_path.is_absolute():
            self.memory_db_path = self.config_dir / self.memory_db_path
        self.memory_db_path.parent.mkdir(parents=True, exist_ok=True)
