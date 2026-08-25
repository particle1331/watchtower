"""Tool primitives, builtin tools, task delegation, and registry helpers."""

from agent_harness.mcp.bridge import MCPManager, MCPServerConfig, MCPToolAdapter
from agent_harness.tools.base import (
    FileDiff,
    Tool,
    ToolConfirmation,
    ToolInvocation,
    ToolKind,
    ToolRegistry,
    ToolResult,
    create_default_registry,
)
from agent_harness.tools.files import (
    EditParams,
    EditTool,
    GlobParams,
    GlobTool,
    GrepParams,
    GrepTool,
    ListDirParams,
    ListDirTool,
    ReadFileParams,
    ReadFileTool,
    WriteFileParams,
    WriteFileTool,
)
from agent_harness.tools.memory import MemoryParams, MemoryTool
from agent_harness.tools.shell import ShellParams, ShellTool
from agent_harness.tools.task import BUILTIN_ROLES, SubAgentParams, SubAgentTool, TaskTool

__all__ = [
    "FileDiff",
    "Tool",
    "ToolConfirmation",
    "ToolInvocation",
    "ToolKind",
    "ToolResult",
    "ToolRegistry",
    "create_default_registry",
    "ReadFileParams",
    "ReadFileTool",
    "WriteFileParams",
    "WriteFileTool",
    "EditParams",
    "EditTool",
    "GlobParams",
    "GlobTool",
    "GrepParams",
    "GrepTool",
    "ListDirParams",
    "ListDirTool",
    "ShellParams",
    "ShellTool",
    "MemoryParams",
    "MemoryTool",
    "SubAgentParams",
    "SubAgentTool",
    "TaskTool",
    "BUILTIN_ROLES",
    "MCPServerConfig",
    "MCPToolAdapter",
    "MCPManager",
]
