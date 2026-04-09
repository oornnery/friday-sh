"""MCP server connection factory."""

from __future__ import annotations

from pydantic_ai.mcp import MCPServerSSE, MCPServerStdio

from friday.infra.config import MCPServerConfig


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
