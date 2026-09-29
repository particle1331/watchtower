"""Async headless coding agent package.

Quick start::

    from agent_harness import Agent, Config

    agent = Agent(Config())
    async for event in agent.run("List the Python files here"):
        print(event)
"""

from agent_harness.agent import Agent
from agent_harness.client import LLMClient
from agent_harness.compaction import ChatCompactor
from agent_harness.config import (
    ApprovalPolicy,
    Config,
    ConfigError,
    HookConfig,
    HookTrigger,
    ModelConfig,
    ShellEnvironmentPolicy,
    load_config,
)
from agent_harness.context import ContextManager
from agent_harness.eval import (
    CriterionResult,
    EvalSuite,
    EvalTask,
    Judge,
    JudgeResult,
    Scorecard,
    TaskSuite,
    Trajectory,
    TrajectoryStore,
)
from agent_harness.events import (
    AgentEvent,
    AgentEventType,
    EventBus,
    StreamEvent,
    StreamEventType,
    TokenUsage,
)
from agent_harness.hooks import HookSystem
from agent_harness.safety import ApprovalManager, CommandVerdict, LoopDetector
from agent_harness.sandbox import (
    DockerSandbox,
    HostSandbox,
    LocalSandbox,
    Sandbox,
    SandboxBackend,
    SandboxConfig,
    SandboxError,
    SandboxExecutionResult,
    SandboxResult,
    create_sandbox,
)
from agent_harness.session import Session
from agent_harness.tools import (
    BUILTIN_ROLES,
    FileDiff,
    MCPManager,
    MCPServerConfig,
    MCPToolAdapter,
    SubAgentParams,
    SubAgentTool,
    TaskTool,
    Tool,
    ToolConfirmation,
    ToolInvocation,
    ToolKind,
    ToolRegistry,
    ToolResult,
    create_default_registry,
)

__all__ = [
    # Core
    "Agent",
    "Session",
    "LLMClient",
    # Config
    "Config",
    "ModelConfig",
    "ShellEnvironmentPolicy",
    "ApprovalPolicy",
    "HookConfig",
    "HookTrigger",
    "ConfigError",
    "load_config",
    # Events
    "AgentEvent",
    "AgentEventType",
    "EventBus",
    "StreamEvent",
    "StreamEventType",
    "TokenUsage",
    # Evaluation
    "EvalTask",
    "EvalSuite",
    "TaskSuite",
    "Trajectory",
    "TrajectoryStore",
    "Judge",
    "JudgeResult",
    "CriterionResult",
    "Scorecard",
    # Hardening
    "ContextManager",
    "ChatCompactor",
    "LoopDetector",
    "CommandVerdict",
    "ApprovalManager",
    "HookSystem",
    # Sandbox
    "Sandbox",
    "SandboxBackend",
    "SandboxConfig",
    "SandboxError",
    "SandboxResult",
    "SandboxExecutionResult",
    "LocalSandbox",
    "HostSandbox",
    "DockerSandbox",
    "create_sandbox",
    # Tools
    "FileDiff",
    "Tool",
    "ToolConfirmation",
    "ToolInvocation",
    "ToolKind",
    "ToolResult",
    "ToolRegistry",
    "create_default_registry",
    "SubAgentParams",
    "SubAgentTool",
    "TaskTool",
    "BUILTIN_ROLES",
    # MCP
    "MCPServerConfig",
    "MCPToolAdapter",
    "MCPManager",
]
