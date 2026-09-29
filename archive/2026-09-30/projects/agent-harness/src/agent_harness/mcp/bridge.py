"""MCP bridge: connect MCP servers to the agent's ToolRegistry.

Each tool discovered on a connected server becomes an ``MCPToolAdapter``
that delegates execution to the live transport client. FastMCP is loaded
only when a connection is requested, so schema translation remains usable
without a server or an optional transport installation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from agent_harness.mcp.client import MCPClient, make_transport
from agent_harness.tools.base import Tool, ToolInvocation, ToolKind, ToolRegistry, ToolResult

logger = logging.getLogger(__name__)

_SEP = "__"


@dataclass
class MCPServerConfig:
    """Connection parameters for one MCP server."""

    name: str
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None
    url: str | None = None
    headers: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if self.command is None and self.url is None:
            raise ValueError(
                f"MCPServerConfig '{self.name}': must set either 'command' (stdio) or 'url' (http)"
            )
        if self.command is not None and self.url is not None:
            raise ValueError(
                f"MCPServerConfig '{self.name}': 'command' and 'url' are mutually exclusive"
            )

    @property
    def transport_kind(self) -> str:
        return "stdio" if self.command else "http"


def namespace_tool_name(server_name: str, tool_name: str) -> str:
    """Return the collision-resistant name shown to the agent."""
    return f"{server_name}{_SEP}{tool_name}"


def translate_tool_schema(
    server_name: str,
    tool_name: str,
    description: str | None,
    input_schema: dict[str, Any] | None,
) -> dict[str, Any]:
    """Translate an MCP input schema into an OpenAI function schema."""
    return {
        "name": namespace_tool_name(server_name, tool_name),
        "description": f"[{server_name}] {description}" if description else f"[{server_name}] {tool_name}",
        "parameters": input_schema or {"type": "object", "properties": {}},
    }


def mcp_tool_to_openai_schema(server_name: str, mcp_tool: Any) -> dict[str, Any]:
    """Translate an MCP tool object or mapping into an OpenAI schema."""
    if isinstance(mcp_tool, dict):
        name = mcp_tool.get("name", "")
        description = mcp_tool.get("description")
        input_schema = mcp_tool.get("inputSchema", mcp_tool.get("input_schema"))
    else:
        name = getattr(mcp_tool, "name", "")
        description = getattr(mcp_tool, "description", None)
        input_schema = getattr(mcp_tool, "inputSchema", None)
    return translate_tool_schema(server_name, name, description, input_schema)


translate_mcp_tool_schema = mcp_tool_to_openai_schema


class MCPToolAdapter(Tool):
    """A ``Tool`` that delegates execution to an MCP server tool."""

    kind = ToolKind.NETWORK

    def __init__(
        self,
        server_name: str,
        mcp_tool_name: str,
        description: str,
        input_schema: dict[str, Any],
        client: Any,
        config: Any,
    ) -> None:
        super().__init__(config)
        self.server_name = server_name
        self.mcp_tool_name = mcp_tool_name
        self._client = client
        self.name = namespace_tool_name(server_name, mcp_tool_name)
        self.description = (
            f"[{server_name}] {description}" if description else f"[{server_name}] {mcp_tool_name}"
        )
        self.schema = {"parameters": input_schema}

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        try:
            result = await self._client.call_tool(self.mcp_tool_name, invocation.params)
        except Exception as exc:
            return ToolResult.error_result(
                f"MCP call failed ({self.server_name}/{self.mcp_tool_name}): {exc}"
            )

        if result.is_error:
            error_text = "\n".join(getattr(item, "text", str(item)) for item in result.content)
            return ToolResult.error_result(error_text)

        output_parts: list[str] = []
        for item in result.content:
            text = getattr(item, "text", None)
            output_parts.append(str(text) if text is not None else f"[{type(item).__name__} content]")

        output = "\n".join(output_parts) if output_parts else str(result.data)
        return ToolResult.success_result(
            output,
            metadata={"server": self.server_name, "tool": self.mcp_tool_name},
        )


class MCPManager:
    """Manage the lifecycle of configured MCP server connections."""

    def __init__(self, servers: list[MCPServerConfig]) -> None:
        self.servers = servers
        self._clients: dict[str, MCPClient] = {}
        self._registered: dict[str, list[str]] = {}

    async def connect_all(
        self,
        registry: ToolRegistry,
        *,
        skip_errors: bool = True,
    ) -> dict[str, list[str]]:
        """Connect to all configured servers and register their tools."""
        results: dict[str, list[str]] = {}
        for server_cfg in self.servers:
            try:
                names = await self._connect_one(server_cfg, registry)
                results[server_cfg.name] = names
                logger.info(
                    "Connected to MCP server %r, registered %d tools: %s",
                    server_cfg.name,
                    len(names),
                    names,
                )
            except Exception as exc:
                logger.warning("Failed to connect to MCP server %r: %s", server_cfg.name, exc)
                if not skip_errors:
                    raise
                results[server_cfg.name] = []
        return results

    async def _connect_one(
        self,
        cfg: MCPServerConfig,
        registry: ToolRegistry,
    ) -> list[str]:
        """Open a client, list tools, and register adapters."""
        client = MCPClient(make_transport(cfg))
        await client.__aenter__()
        self._clients[cfg.name] = client

        try:
            mcp_tools = await client.list_tools()
            registered_names: list[str] = []
            for mcp_tool in mcp_tools:
                translated = mcp_tool_to_openai_schema(cfg.name, mcp_tool)
                mcp_name = (
                    mcp_tool.get("name", "")
                    if isinstance(mcp_tool, dict)
                    else getattr(mcp_tool, "name", "")
                )
                adapter = MCPToolAdapter(
                    server_name=cfg.name,
                    mcp_tool_name=mcp_name,
                    description=translated["description"].removeprefix(f"[{cfg.name}] "),
                    input_schema=translated["parameters"],
                    client=client,
                    config=registry.config,
                )
                registry.register(adapter)
                registered_names.append(adapter.name)
        except Exception:
            await client.__aexit__(None, None, None)
            self._clients.pop(cfg.name, None)
            raise

        self._registered[cfg.name] = registered_names
        return registered_names

    @staticmethod
    def _make_transport(cfg: MCPServerConfig) -> Any:
        """Build a transport, retaining the old manager helper API."""
        return make_transport(cfg)

    async def close(self) -> None:
        """Close all open client connections."""
        for name, client in list(self._clients.items()):
            try:
                await client.__aexit__(None, None, None)
                logger.debug("Closed MCP client for %r", name)
            except Exception as exc:
                logger.warning("Error closing MCP client %r: %s", name, exc)
        self._clients.clear()

    def status(self) -> dict[str, Any]:
        """Return a summary of connected servers and registered tools."""
        return {
            cfg.name: {
                "connected": cfg.name in self._clients,
                "tools": self._registered.get(cfg.name, []),
            }
            for cfg in self.servers
        }
