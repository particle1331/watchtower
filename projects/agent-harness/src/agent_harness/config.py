"""Agent configuration using Pydantic models and layered file loading.

Provides the typed settings models as well as the optional system/project
configuration loader used for repeatable runs.
"""

from __future__ import annotations

import logging
import os
import tomllib
from enum import StrEnum
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir, user_data_dir
from pydantic import BaseModel, Field, ValidationError, model_validator

logger = logging.getLogger(__name__)


class ModelConfig(BaseModel):
    """LLM model configuration."""

    name: str = "anthropic/claude-sonnet-4"
    temperature: float = Field(default=1.0, ge=0.0, le=2.0)
    context_window: int = 200_000


class ShellEnvironmentPolicy(BaseModel):
    """Controls which env vars are visible to shell tool execution."""

    ignore_default_excludes: bool = False
    exclude_patterns: list[str] = Field(
        default_factory=lambda: ["*KEY*", "*TOKEN*", "*SECRET*"]
    )
    set_vars: dict[str, str] = Field(default_factory=dict)


class ApprovalPolicy(StrEnum):
    """How the agent handles approval for mutating operations."""

    ON_REQUEST = "on-request"
    AUTO = "auto"
    NEVER = "never"
    YOLO = "yolo"


class HookTrigger(StrEnum):
    """Lifecycle points at which a hook script can fire.

    The string values are surfaced to hook scripts via the
    ``AI_AGENT_TRIGGER`` environment variable.
    """

    BEFORE_AGENT = "before_agent"
    AFTER_AGENT = "after_agent"
    BEFORE_TOOL = "before_tool"
    AFTER_TOOL = "after_tool"
    ON_ERROR = "on_error"


class HookConfig(BaseModel):
    """One hook definition: a trigger and either a shell ``command``
    or an inline ``script`` to run when the trigger fires.

    Exactly one of ``command`` and ``script`` must be set. A ``command``
    is executed as-is (e.g. ``"python3 tests.py"``); a ``script`` is
    written to a temp file with a ``#!/bin/bash`` shebang and run.
    """

    name: str
    trigger: HookTrigger
    command: str | None = None
    script: str | None = None
    timeout_sec: float = 30.0
    enabled: bool = True

    @model_validator(mode="after")
    def validate_hook(self) -> HookConfig:
        if not self.command and not self.script:
            raise ValueError("Hook must have either 'command' or 'script'")
        if self.command and self.script:
            raise ValueError("Hook cannot have both 'command' and 'script'")
        return self


class Config(BaseModel):
    """Top-level agent configuration.

    API credentials are read from environment variables.  The OpenRouter
    names remain the defaults, while provider-specific aliases keep the
    OpenAI-compatible client usable with other endpoints:
      - AGENT_API_KEY, OPENROUTER_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY,
        or API_KEY
      - AGENT_BASE_URL, OPENROUTER_BASE_URL, ANTHROPIC_BASE_URL, or
        OPENAI_BASE_URL (default: https://openrouter.ai/api/v1)
    """

    model: ModelConfig = Field(default_factory=ModelConfig)
    cwd: Path = Field(default_factory=Path.cwd)
    shell_environment: ShellEnvironmentPolicy = Field(
        default_factory=ShellEnvironmentPolicy
    )
    approval: ApprovalPolicy = ApprovalPolicy.ON_REQUEST
    max_turns: int = 100

    allowed_tools: list[str] | None = Field(
        default=None,
        description="If set, only these tools will be available to the agent",
    )

    mcp_servers: list[Any] = Field(
        default_factory=list,
        description="MCP server configs (MCPServerConfig) to connect at startup",
    )

    hooks_enabled: bool = False
    hooks: list[HookConfig] = Field(default_factory=list)

    developer_instructions: str | None = None
    user_instructions: str | None = None
    debug: bool = False

    @property
    def api_key(self) -> str | None:
        for name in (
            "AGENT_API_KEY",
            "OPENROUTER_API_KEY",
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "API_KEY",
        ):
            if value := os.environ.get(name):
                return value
        return None

    @property
    def base_url(self) -> str:
        return next(
            (
                os.environ[name]
                for name in (
                    "AGENT_BASE_URL",
                    "OPENROUTER_BASE_URL",
                    "ANTHROPIC_BASE_URL",
                    "OPENAI_BASE_URL",
                )
                if os.environ.get(name)
            ),
            "https://openrouter.ai/api/v1",
        )

    @property
    def model_name(self) -> str:
        return self.model.name

    @model_name.setter
    def model_name(self, value: str) -> None:
        self.model.name = value

    @property
    def temperature(self) -> float:
        return self.model.temperature

    @property
    def context_window(self) -> int:
        return self.model.context_window

    def validate_config(self) -> list[str]:
        """Return a list of configuration errors (empty if valid)."""
        errors: list[str] = []
        if not self.api_key:
            errors.append(
                "No API key found. Set AGENT_API_KEY, OPENROUTER_API_KEY, "
                "ANTHROPIC_API_KEY, or OPENAI_API_KEY."
            )
        if not self.cwd.exists():
            errors.append(f"Working directory does not exist: {self.cwd}")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


CONFIG_FILE_NAME = "config.toml"
AGENT_MD_FILE = "AGENT.MD"
APP_NAME = "ai-agent"


class ConfigError(Exception):
    """Raised when configuration cannot be loaded or is invalid."""


def get_config_dir() -> Path:
    """Return the per-user configuration directory."""
    return Path(user_config_dir(APP_NAME))


def get_data_dir() -> Path:
    """Return the per-user data directory for sessions and logs."""
    return Path(user_data_dir(APP_NAME))


def get_system_config_path() -> Path:
    """Return the full path to the system-wide ``config.toml``."""
    return get_config_dir() / CONFIG_FILE_NAME


def get_project_config_path(cwd: Path) -> Path | None:
    """Locate a project-local config at ``<cwd>/.ai-agent/config.toml``."""
    candidate = cwd.resolve() / ".ai-agent" / CONFIG_FILE_NAME
    return candidate if candidate.is_file() else None


def get_agent_md_path(cwd: Path) -> Path | None:
    """Locate an ``AGENT.MD`` file at the working directory."""
    candidate = cwd.resolve() / AGENT_MD_FILE
    return candidate if candidate.is_file() else None


def _parse_toml(path: Path) -> dict[str, Any]:
    """Parse a TOML file, wrapping parse and I/O failures in ConfigError."""
    try:
        with path.open("rb") as file:
            return tomllib.load(file)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Failed to read config file {path}: {exc}") from exc


def _merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge ``override`` over ``base``."""
    result = base.copy()
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def load_config(cwd: Path | None = None) -> Config:
    """Load a :class:`Config` by layering system, project, and AGENT.MD data.

    Missing files contribute no settings. Invalid TOML files are logged and
    skipped, while a merged configuration that fails Pydantic validation
    raises :class:`ConfigError`.
    """
    cwd = (cwd or Path.cwd()).resolve()
    config_dict: dict[str, Any] = {}

    system_path = get_system_config_path()
    if system_path.is_file():
        try:
            config_dict = _parse_toml(system_path)
        except ConfigError:
            logger.warning("Skipping invalid system config: %s", system_path)

    project_path = get_project_config_path(cwd)
    if project_path:
        try:
            config_dict = _merge_dicts(config_dict, _parse_toml(project_path))
        except ConfigError:
            logger.warning("Skipping invalid project config: %s", project_path)

    config_dict.setdefault("cwd", cwd)

    if "developer_instructions" not in config_dict:
        agent_md = get_agent_md_path(cwd)
        if agent_md:
            config_dict["developer_instructions"] = agent_md.read_text(encoding="utf-8")

    try:
        return Config(**config_dict)
    except ValidationError as exc:
        raise ConfigError(f"Invalid configuration: {exc}") from exc
