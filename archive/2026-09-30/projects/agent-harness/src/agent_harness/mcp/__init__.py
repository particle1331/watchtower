"""Optional Model Context Protocol integration."""

from agent_harness.mcp.bridge import (
    MCPManager,
    MCPServerConfig,
    MCPToolAdapter,
    mcp_tool_to_openai_schema,
    namespace_tool_name,
    translate_mcp_tool_schema,
    translate_tool_schema,
)
from agent_harness.mcp.client import MCPClient, TransportClient, make_transport

__all__ = [
    "MCPClient",
    "TransportClient",
    "make_transport",
    "MCPManager",
    "MCPServerConfig",
    "MCPToolAdapter",
    "namespace_tool_name",
    "translate_tool_schema",
    "mcp_tool_to_openai_schema",
    "translate_mcp_tool_schema",
]
