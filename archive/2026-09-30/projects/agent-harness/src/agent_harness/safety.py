"""Approval system, command classification, and loop detection."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from enum import StrEnum

from agent_harness.config import ApprovalPolicy, Config
from agent_harness.tools.base import Tool, ToolKind

logger = logging.getLogger(__name__)


class CommandVerdict(StrEnum):
    """Coarse command classification used by the approval policy."""

    SAFE = "safe"
    DANGEROUS = "dangerous"
    UNKNOWN = "unknown"


class ApprovalManager:
    """Decides whether tool calls need user approval."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._safe_commands: set[str] = {
            "ls",
            "cat",
            "head",
            "tail",
            "grep",
            "find",
            "wc",
            "echo",
            "pwd",
            "which",
            "env",
            "whoami",
            "date",
            "file",
            "stat",
            "du",
            "df",
            "uname",
            "python --version",
            "git status",
            "git log",
            "git diff",
        }
        self._dangerous_patterns: list[str] = [
            "rm -rf",
            "rm -r",
            "sudo",
            "chmod 777",
            "kill -9",
            "pkill",
            "mkfs",
            "dd if=",
            "shutdown",
            "reboot",
            "> /dev/",
            "| sh",
            "| bash",
            "curl.*| sh",
            "wget.*| sh",
        ]

    def needs_approval(self, tool: Tool, params: dict) -> bool:
        """Decide whether *tool* called with *params* requires approval."""
        policy = self._config.approval

        if policy == ApprovalPolicy.YOLO:
            logger.debug("YOLO mode: auto-approving %s", tool.name)
            return False
        if policy == ApprovalPolicy.NEVER:
            logger.debug("NEVER mode: requiring approval for %s", tool.name)
            return True
        if tool.kind == ToolKind.READ:
            logger.debug("READ tool %s: auto-approved", tool.name)
            return False

        if policy == ApprovalPolicy.AUTO:
            if tool.kind == ToolKind.SHELL:
                command = self._extract_command(params)
                return bool(self.is_dangerous_command(command))
            return False

        if tool.kind == ToolKind.SHELL:
            command = self._extract_command(params)
            return not self.is_safe_command(command)
        return True

    def classify_command(self, command: str) -> CommandVerdict:
        """Classify a shell command as safe, dangerous, or unknown."""
        if self.is_dangerous_command(command):
            return CommandVerdict.DANGEROUS
        if self.is_safe_command(command):
            return CommandVerdict.SAFE
        return CommandVerdict.UNKNOWN

    def is_dangerous_command(self, command: str) -> bool:
        """Check if *command* matches any dangerous pattern."""
        cmd = command.strip().lower()
        for pattern in self._dangerous_patterns:
            if ".*" in pattern:
                if re.search(pattern, cmd):
                    return True
            elif pattern in cmd:
                return True
        return False

    def is_safe_command(self, command: str) -> bool:
        """Check if *command* starts with a known safe command."""
        cmd = command.strip().lower()
        if not cmd:
            return False
        # A safe-looking first command must not bless a compound command.
        if any(token in cmd for token in (";", "|", "&", "\n", "`", "$(", ">", "<")):
            return False

        for safe in sorted(self._safe_commands, key=len, reverse=True):
            if " " in safe:
                if cmd == safe or cmd.startswith(safe + " "):
                    return True
            elif cmd.split()[0] == safe:
                return True
        return False

    def get_approval_reason(self, tool: Tool, params: dict) -> str:
        """Return a human-readable reason why approval is needed."""
        if tool.kind == ToolKind.SHELL:
            command = self._extract_command(params)
            normalized = command.lower()
            for pattern in self._dangerous_patterns:
                if ".*" in pattern:
                    if re.search(pattern, normalized):
                        label = pattern.split(".*")[0].strip()
                        return f"Dangerous command detected: {label}... | sh"
                elif pattern in normalized:
                    return f"Dangerous command detected: {pattern}"
            return "Shell command requires approval"
        if tool.kind == ToolKind.WRITE:
            return "File write requires approval"
        if tool.kind == ToolKind.NETWORK:
            return "Network access requires approval"
        if tool.kind == ToolKind.MEMORY:
            return "Memory modification requires approval"
        return f"{tool.name} requires approval"

    @staticmethod
    def _extract_command(params: dict) -> str:
        """Pull the shell command string from tool params."""
        return params.get("command", "")


class LoopDetector:
    """Detect repetitive patterns in the agent's behavior."""

    def __init__(self, max_repeats: int = 3, window_size: int = 10) -> None:
        self.max_repeats = max_repeats
        self.window_size = window_size
        self._signatures: list[str] = []

    def record(self, action: str, params: dict | None = None) -> None:
        """Record an action signature and retain only the rolling window."""
        params_json = json.dumps(params, sort_keys=True) if params else ""
        raw = f"{action}:{params_json}"
        self._signatures.append(hashlib.md5(raw.encode()).hexdigest())
        if len(self._signatures) > self.window_size:
            self._signatures = self._signatures[-self.window_size :]

    def is_looping(self) -> bool:
        """Return ``True`` if the latest signature repeats too often."""
        if not self._signatures:
            return False
        return self._signatures.count(self._signatures[-1]) >= self.max_repeats

    def detect_cycle(self, min_cycle_length: int = 2, max_cycle_length: int = 5) -> list[str] | None:
        """Look for a repeating cycle in the recent signatures."""
        n = len(self._signatures)
        for length in range(min_cycle_length, max_cycle_length + 1):
            if n < 2 * length:
                continue
            cycle = self._signatures[-length:]
            preceding = self._signatures[-2 * length : -length]
            if cycle == preceding:
                return cycle
        return None

    def get_loop_message(self) -> str:
        """Return a diagnostic message to inject when a loop is detected."""
        cycle = self.detect_cycle()
        if cycle is not None:
            return (
                "SYSTEM: Loop detected — you have been repeating the same "
                f"sequence of {len(cycle)} actions. Please stop and try a "
                "fundamentally different approach to solve the problem."
            )
        return (
            "SYSTEM: Loop detected — you are repeating the same action. "
            "Please stop and try a different approach. Consider:\n"
            "  1. Re-reading the relevant code or error message carefully.\n"
            "  2. Trying an alternative tool or strategy.\n"
            "  3. Asking the user for clarification."
        )

    def reset(self) -> None:
        """Clear all recorded signatures."""
        self._signatures = []
