"""Optional MCP transport client helpers.

The harness keeps the transport dependency optional: importing the package and
using pure schema translation does not require ``fastmcp``. A transport is
constructed only when an MCP manager actually connects to a server.
"""

from __future__ import annotations

import importlib
from typing import Any


def _fastmcp_components() -> tuple[Any, Any, Any]:
    """Load FastMCP lazily so the core harness stays importable without it."""
    try:
        fastmcp = importlib.import_module("fastmcp")
        Client = vars(fastmcp)["Client"]
        try:
            client_module = importlib.import_module("fastmcp.client")
            client_exports = vars(client_module)
            PythonStdioTransport = client_exports["PythonStdioTransport"]
            StreamableHttpTransport = client_exports["StreamableHttpTransport"]
        except (ImportError, KeyError):
            transports = importlib.import_module("fastmcp.client.transports")
            transport_exports = vars(transports)
            PythonStdioTransport = transport_exports["PythonStdioTransport"]
            StreamableHttpTransport = transport_exports["StreamableHttpTransport"]
    except (ImportError, KeyError) as exc:
        raise RuntimeError(
            "MCP transports require the optional 'fastmcp' package"
        ) from exc
    return Client, PythonStdioTransport, StreamableHttpTransport


def make_transport(config: Any) -> Any:
    """Build a FastMCP transport for an MCP server configuration."""
    _, python_stdio_transport, streamable_http_transport = _fastmcp_components()
    if config.url:
        return streamable_http_transport(url=config.url, headers=config.headers)
    if config.command is None:
        raise ValueError(f"MCPServerConfig '{config.name}' has no command or URL")
    return python_stdio_transport(
        script_path=config.args[0] if config.args else config.command,
        args=config.args[1:] if config.args else [],
        env=config.env,
    )


class MCPClient:
    """Small async wrapper around a FastMCP client connection."""

    def __init__(self, transport: Any) -> None:
        client_class, _, _ = _fastmcp_components()
        self._client = client_class(transport)

    async def __aenter__(self) -> MCPClient:
        await self._client.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any:
        return await self._client.__aexit__(exc_type, exc, traceback)

    async def list_tools(self) -> Any:
        return await self._client.list_tools()

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return await self._client.call_tool(name, arguments)


TransportClient = MCPClient
