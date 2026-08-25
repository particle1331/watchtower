"""Sub-agent orchestration tool.

Allows the main agent to spawn a focused sub-agent to handle a specific
sub-task, such as gathering information about the codebase, reviewing a
diff, writing tests, or any other specialized operation.

The sub-agent runs in an isolated ``Session`` with:
  - Its own conversation history (starts fresh)
  - A configurable system prompt for specialization
  - An optionally restricted tool set
  - The same working directory and LLM client credentials as the parent

This implements the sub-agent / orchestrator pattern: the orchestrator
(parent) delegates well-scoped sub-tasks to focused sub-agents and folds
their outputs back into its own reasoning.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from agent_harness.config import ApprovalPolicy, Config
from agent_harness.tools.base import Tool, ToolInvocation, ToolKind, ToolResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Built-in sub-agent role definitions
# ---------------------------------------------------------------------------

#: Mapping of role name -> (system_prompt, allowed_tool_names | None)
#: ``None`` for allowed_tools means the sub-agent inherits all parent tools.
BUILTIN_ROLES: dict[str, tuple[str, list[str] | None]] = {
    "codebase_investigator": (
        "You are a precise codebase investigator. Your job is to thoroughly "
        "explore the repository structure, read relevant source files, and "
        "answer the given question with specific, accurate findings. "
        "Reference exact file paths and line numbers wherever possible. "
        "Do NOT modify any files.",
        ["read_file", "list_dir", "glob", "grep", "shell"],
    ),
    "code_reviewer": (
        "You are a rigorous code reviewer. Analyze the provided code for "
        "correctness, style, performance, and security issues. "
        "Produce a structured review with specific, actionable feedback. "
        "Reference file paths and line numbers. Do NOT modify any files.",
        ["read_file", "list_dir", "glob", "grep"],
    ),
    "test_writer": (
        "You are a test engineer. Write clear, thorough tests for the code "
        "you are given. Use the project's existing test patterns and "
        "frameworks. Output the complete test file(s) and explain your "
        "testing strategy.",
        None,
    ),
    "code_fixer": (
        "You are a focused bug fixer. Diagnose the described issue, locate "
        "the root cause in the codebase, apply a minimal and correct fix, "
        "and report exactly what you changed and why.",
        None,
    ),
    "doc_writer": (
        "You are a technical writer. Produce clear, accurate documentation "
        "for the given code or feature. Follow the existing doc style in the "
        "project. Output markdown or docstrings as appropriate.",
        ["read_file", "list_dir", "glob", "grep", "write_file"],
    ),
}


class SubAgentParams(BaseModel):
    """Parameters for the sub-agent tool."""

    task: str = Field(
        ...,
        description=(
            "A complete, self-contained description of the task the sub-agent "
            "should perform. Include all relevant context: file paths, error "
            "messages, code snippets, and the expected output format."
        ),
    )
    role: str = Field(
        default="codebase_investigator",
        description=(
            "The sub-agent's specialized role. "
            f"Built-in roles: {', '.join(BUILTIN_ROLES)}. "
            "You may also pass 'custom' and supply a system_prompt."
        ),
    )
    system_prompt: str | None = Field(
        default=None,
        description=(
            "Custom system prompt for the sub-agent. Required when "
            "role='custom'; ignored for built-in roles."
        ),
    )
    allowed_tools: list[str] | None = Field(
        default=None,
        description=(
            "If set, restricts which tools the sub-agent may use. Defaults to "
            "the role's built-in tool restriction, or all tools when no restriction is defined."
        ),
    )
    max_turns: int = Field(
        default=30,
        ge=1,
        le=100,
        description="Maximum number of agentic turns for the sub-agent.",
    )


class SubAgentTool(Tool):
    """Spawns a focused sub-agent to handle a specific sub-task.

    The parent agent calls this tool with a complete task description and an
    optional role specialization. The sub-agent runs to completion, or until
    its turn budget is exhausted, and its final response is returned as the
    tool output.
    """

    name = "run_sub_agent"
    description = (
        "Spawn a focused sub-agent to handle a specific sub-task. "
        "The sub-agent runs to completion and returns its findings or "
        "output. Use this to delegate well-scoped work such as codebase "
        "investigation, code review, test writing, or targeted bug fixing."
    )
    kind = ToolKind.MEMORY
    schema = SubAgentParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        """Run the sub-agent and return its output."""
        # Lazy imports avoid circular dependencies at module load time.
        from agent_harness.agent import Agent
        from agent_harness.events import AgentEventType
        from agent_harness.session import Session

        params = SubAgentParams(**invocation.params)
        role_prompt, role_tools = self._resolve_role(params)
        child_config = self._build_child_config(params, role_prompt, role_tools)

        child_session = Session(child_config)
        child_session.messages[0]["content"] = role_prompt
        child_agent = Agent(config=child_config, session=child_session)

        logger.info(
            "Spawning sub-agent (role=%s, max_turns=%d) for task: %.120s...",
            params.role,
            params.max_turns,
            params.task,
        )

        final_response = ""
        error_messages: list[str] = []

        async for event in child_agent.run(params.task):
            if event.type == AgentEventType.TEXT_COMPLETE:
                final_response = event.data.get("content", "")
            elif event.type == AgentEventType.AGENT_ERROR:
                error_messages.append(event.data.get("error", "Unknown error"))

        if error_messages and not final_response:
            return ToolResult.error_result(
                f"Sub-agent failed: {'; '.join(error_messages)}",
                metadata={"role": params.role, "task_preview": params.task[:200]},
            )

        output = self._format_output(params, final_response, error_messages)
        return ToolResult.success_result(
            output,
            metadata={
                "role": params.role,
                "turns": child_session.turn_count,
                "total_tokens": child_session.total_usage.total_tokens,
            },
        )

    def _resolve_role(self, params: SubAgentParams) -> tuple[str, list[str] | None]:
        """Return (system_prompt, allowed_tools) for the requested role."""
        if params.role == "custom":
            if not params.system_prompt:
                raise ValueError("role='custom' requires a non-empty system_prompt.")
            return params.system_prompt, params.allowed_tools

        role_def = BUILTIN_ROLES.get(params.role)
        if role_def is None:
            available = ", ".join(BUILTIN_ROLES)
            raise ValueError(
                f"Unknown role '{params.role}'. Available built-in roles: {available}. "
                "Use role='custom' with a system_prompt for a custom role."
            )

        role_prompt, role_tools = role_def
        return role_prompt, params.allowed_tools if params.allowed_tools is not None else role_tools

    def _build_child_config(
        self,
        params: SubAgentParams,
        role_prompt: str,
        role_tools: list[str] | None,
    ) -> Config:
        """Build a child Config with role-appropriate overrides."""
        return Config(
            model=self.config.model.model_copy(),
            cwd=self.config.cwd,
            shell_environment=self.config.shell_environment,
            approval=ApprovalPolicy.YOLO,
            max_turns=params.max_turns,
            allowed_tools=role_tools,
            developer_instructions=role_prompt,
        )

    @staticmethod
    def _format_output(
        params: SubAgentParams,
        response: str,
        errors: list[str],
    ) -> str:
        """Format the sub-agent's output for insertion into the parent context."""
        header = f"[Sub-agent result | role={params.role}]\n"
        body = response or "(no text response)"
        warning = "\n\n[Sub-agent encountered errors: " + "; ".join(errors) + "]" if errors else ""
        return header + body + warning


# The old public name remains available while the course-facing name is TaskTool.
TaskTool = SubAgentTool
