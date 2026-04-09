"""MCP server connection factory with command validation."""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic_ai.mcp import MCPServerSSE, MCPServerStdio

from friday.infra.config import MCPServerConfig

log = logging.getLogger(__name__)

# Bare shells that should never be used as MCP server commands
_BLOCKED_COMMANDS = frozenset(
    {
        'sh',
        'bash',
        'zsh',
        'fish',
        'dash',
        'csh',
        'ksh',
        '/bin/sh',
        '/bin/bash',
        '/bin/zsh',
        '/usr/bin/sh',
        '/usr/bin/bash',
    }
)


def _validate_stdio_command(entry: MCPServerConfig) -> None:
    """Warn if the MCP server command looks dangerous."""
    cmd = entry.command.strip()
    cmd_name = Path(cmd).name

    if cmd in _BLOCKED_COMMANDS or cmd_name in _BLOCKED_COMMANDS:
        log.warning(
            'MCP server %r uses bare shell %r as command — this is a security risk',
            entry.name,
            cmd,
        )


def create_mcp_servers(
    configs: list[MCPServerConfig],
) -> list[MCPServerSSE | MCPServerStdio]:
    """Create pydantic-ai MCP server instances from config entries."""
    servers: list[MCPServerSSE | MCPServerStdio] = []
    for entry in configs:
        match entry.transport:
            case 'http':
                servers.append(
                    MCPServerSSE(
                        url=entry.url,
                        id=entry.name,
                        tool_prefix=entry.name,
                    )
                )
            case 'stdio':
                _validate_stdio_command(entry)
                servers.append(
                    MCPServerStdio(
                        command=entry.command,
                        args=entry.args,
                        env=entry.env or None,
                        id=entry.name,
                        tool_prefix=entry.name,
                    )
                )
    return servers
