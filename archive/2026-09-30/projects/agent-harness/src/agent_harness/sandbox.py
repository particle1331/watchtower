"""Small execution backends for commands that should be isolated from the host.

The local backend is deliberately an execution *adapter*, not a security
boundary.  It is useful for deterministic tests and for installations where a
container runtime is unavailable.  ``DockerSandbox`` provides the stronger
boundary when Docker is available and keeps the Docker dependency optional by
invoking the command-line client directly.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import time
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

from pydantic import AliasChoices, BaseModel, Field


class SandboxError(RuntimeError):
    """Raised when a sandbox cannot prepare an execution request."""


class SandboxBackend(StrEnum):
    """Available command execution backends."""

    LOCAL = "local"
    DOCKER = "docker"


class SandboxConfig(BaseModel):
    """Configuration shared by the local and Docker sandbox backends.

    ``local`` is the default so the library remains usable without Docker.
    It confines the subprocess working directory, but cannot prevent a shell
    command from accessing other host resources.  Select ``docker`` when a
    process boundary is required.
    """

    workspace: Path = Field(
        default_factory=Path.cwd,
        validation_alias=AliasChoices("workspace", "root", "root_dir", "cwd"),
        description="Workspace mounted or used as the sandbox root",
    )
    backend: SandboxBackend = SandboxBackend.LOCAL
    image: str = "python:3.14-slim"
    timeout: float = Field(
        120.0,
        ge=0.001,
        validation_alias=AliasChoices("timeout", "timeout_sec"),
    )
    network: bool = False
    read_only: bool = False
    env: dict[str, str] = Field(default_factory=dict)
    memory_limit: str | None = None
    cpu_limit: float | None = Field(None, gt=0)
    pids_limit: int | None = Field(None, gt=0)
    max_output_bytes: int = Field(100 * 1024, gt=0)

    @property
    def root(self) -> Path:
        """Compatibility alias for callers that call the workspace ``root``."""
        return self.workspace

    @property
    def timeout_sec(self) -> float:
        """Compatibility alias for the timeout setting."""
        return self.timeout


class SandboxResult:
    """The observable result of one sandbox execution.

    The result intentionally mirrors the useful portion of
    :class:`subprocess.CompletedProcess` while retaining timeout and output
    truncation information for an evaluator.
    """

    def __init__(
        self,
        command: str,
        stdout: str = "",
        stderr: str = "",
        exit_code: int | None = None,
        *,
        returncode: int | None = None,
        timed_out: bool = False,
        duration_ms: float = 0.0,
        backend: str = SandboxBackend.LOCAL.value,
        truncated: bool = False,
        error: str | None = None,
    ) -> None:
        self.command = command
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code if exit_code is not None else returncode
        self.timed_out = timed_out
        self.duration_ms = duration_ms
        self.backend = backend
        self.truncated = truncated
        self.error = error

    @property
    def returncode(self) -> int | None:
        """Alias matching :class:`subprocess.CompletedProcess`."""
        return self.exit_code

    @property
    def success(self) -> bool:
        """Whether the command completed successfully."""
        return self.exit_code == 0 and not self.timed_out and self.error is None

    @property
    def output(self) -> str:
        """Return stdout, with stderr appended when it is present."""
        if not self.stderr:
            return self.stdout
        if not self.stdout:
            return self.stderr
        return f"{self.stdout}\n--- stderr ---\n{self.stderr}"

    @property
    def combined_output(self) -> str:
        """Explicit alias for :attr:`output`."""
        return self.output

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation."""
        return {
            "command": self.command,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "returncode": self.exit_code,
            "timed_out": self.timed_out,
            "duration_ms": self.duration_ms,
            "backend": self.backend,
            "truncated": self.truncated,
            "error": self.error,
            "success": self.success,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SandboxResult:
        """Restore a result from :meth:`to_dict` output."""
        return cls(
            command=str(data.get("command", "")),
            stdout=str(data.get("stdout", "")),
            stderr=str(data.get("stderr", "")),
            exit_code=data.get("exit_code", data.get("returncode")),
            timed_out=bool(data.get("timed_out", False)),
            duration_ms=float(data.get("duration_ms", 0.0)),
            backend=str(data.get("backend", SandboxBackend.LOCAL.value)),
            truncated=bool(data.get("truncated", False)),
            error=data.get("error"),
        )

    def __repr__(self) -> str:
        return (
            "SandboxResult("
            f"command={self.command!r}, exit_code={self.exit_code!r}, "
            f"timed_out={self.timed_out!r})"
        )


def _resolve_working_directory(workspace: Path, requested: str | Path | None) -> Path:
    """Resolve a requested directory without allowing it to leave *workspace*."""
    root = workspace.expanduser().resolve()
    candidate = Path(requested) if requested is not None else root
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise SandboxError(f"Working directory escapes workspace: {requested}")
    if not resolved.exists():
        raise SandboxError(f"Working directory does not exist: {resolved}")
    if not resolved.is_dir():
        raise SandboxError(f"Working directory is not a directory: {resolved}")
    return resolved


def _trim_output(data: bytes, maximum: int) -> tuple[str, bool]:
    """Decode output and cap it without splitting an encoded character."""
    truncated = len(data) > maximum
    if truncated:
        data = data[:maximum]
    return data.decode("utf-8", errors="replace"), truncated


def _terminate_process(process: asyncio.subprocess.Process) -> None:
    """Terminate a process group started by a sandbox command."""
    try:
        if sys.platform != "win32":
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        else:
            process.kill()
    except (ProcessLookupError, OSError):
        pass


class LocalSandbox:
    """Run commands on the host with workspace and timeout handling."""

    def __init__(self, config: SandboxConfig) -> None:
        self.config = config

    async def run(
        self,
        command: str,
        cwd: str | Path | None = None,
        *,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> SandboxResult:
        started = time.monotonic()
        try:
            working_directory = _resolve_working_directory(self.config.workspace, cwd)
        except SandboxError as exc:
            return SandboxResult(
                command,
                backend=SandboxBackend.LOCAL.value,
                error=str(exc),
                duration_ms=_duration_ms(started),
            )

        process_env = os.environ.copy()
        process_env.update(self.config.env)
        if env:
            process_env.update(env)

        try:
            process = await asyncio.create_subprocess_exec(
                "/bin/bash" if sys.platform != "win32" else "cmd.exe",
                "-c" if sys.platform != "win32" else "/c",
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(working_directory),
                env=process_env,
                start_new_session=sys.platform != "win32",
            )
        except OSError as exc:
            return SandboxResult(
                command,
                backend=SandboxBackend.LOCAL.value,
                error=str(exc),
                duration_ms=_duration_ms(started),
            )

        limit = timeout if timeout is not None else self.config.timeout
        try:
            stdout_data, stderr_data = await asyncio.wait_for(
                process.communicate(), timeout=limit
            )
        except TimeoutError:
            _terminate_process(process)
            await process.wait()
            return SandboxResult(
                command,
                stderr="Command timed out",
                exit_code=process.returncode,
                timed_out=True,
                backend=SandboxBackend.LOCAL.value,
                duration_ms=_duration_ms(started),
            )

        stdout, stdout_truncated = _trim_output(stdout_data, self.config.max_output_bytes)
        stderr, stderr_truncated = _trim_output(stderr_data, self.config.max_output_bytes)
        return SandboxResult(
            command,
            stdout=stdout,
            stderr=stderr,
            exit_code=process.returncode,
            backend=SandboxBackend.LOCAL.value,
            truncated=stdout_truncated or stderr_truncated,
            duration_ms=_duration_ms(started),
        )

    execute = run


class DockerSandbox:
    """Run commands in a disposable Docker container.

    The workspace is the only host path mounted into the container. Network is
    disabled unless explicitly enabled in :class:`SandboxConfig`.
    """

    def __init__(self, config: SandboxConfig) -> None:
        self.config = config

    def _docker_args(
        self,
        command: str,
        working_directory: Path,
        env: dict[str, str] | None,
    ) -> list[str]:
        root = self.config.workspace.expanduser().resolve()
        relative_cwd = working_directory.relative_to(root).as_posix()
        container_cwd = "/workspace" if relative_cwd == "." else f"/workspace/{relative_cwd}"
        args = ["run", "--rm", "--init"]
        if not self.config.network:
            args.extend(["--network", "none"])
        mode = "ro" if self.config.read_only else "rw"
        args.extend(
            [
                "--mount",
                f"type=bind,source={root},target=/workspace,{mode}",
                "--workdir",
                container_cwd,
            ]
        )
        if self.config.memory_limit:
            args.extend(["--memory", self.config.memory_limit])
        if self.config.cpu_limit is not None:
            args.extend(["--cpus", str(self.config.cpu_limit)])
        if self.config.pids_limit is not None:
            args.extend(["--pids-limit", str(self.config.pids_limit)])
        for key, value in {**self.config.env, **(env or {})}.items():
            args.extend(["--env", f"{key}={value}"])
        args.extend([self.config.image, "/bin/sh", "-lc", command])
        return args

    async def run(
        self,
        command: str,
        cwd: str | Path | None = None,
        *,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> SandboxResult:
        started = time.monotonic()
        try:
            working_directory = _resolve_working_directory(self.config.workspace, cwd)
        except SandboxError as exc:
            return SandboxResult(
                command,
                backend=SandboxBackend.DOCKER.value,
                error=str(exc),
                duration_ms=_duration_ms(started),
            )

        try:
            process = await asyncio.create_subprocess_exec(
                "docker",
                *self._docker_args(command, working_directory, env),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=sys.platform != "win32",
            )
        except OSError as exc:
            return SandboxResult(
                command,
                backend=SandboxBackend.DOCKER.value,
                error=f"Unable to start Docker: {exc}",
                duration_ms=_duration_ms(started),
            )

        limit = timeout if timeout is not None else self.config.timeout
        try:
            stdout_data, stderr_data = await asyncio.wait_for(
                process.communicate(), timeout=limit
            )
        except TimeoutError:
            _terminate_process(process)
            await process.wait()
            return SandboxResult(
                command,
                stderr="Command timed out",
                exit_code=process.returncode,
                timed_out=True,
                backend=SandboxBackend.DOCKER.value,
                duration_ms=_duration_ms(started),
            )

        stdout, stdout_truncated = _trim_output(stdout_data, self.config.max_output_bytes)
        stderr, stderr_truncated = _trim_output(stderr_data, self.config.max_output_bytes)
        return SandboxResult(
            command,
            stdout=stdout,
            stderr=stderr,
            exit_code=process.returncode,
            backend=SandboxBackend.DOCKER.value,
            truncated=stdout_truncated or stderr_truncated,
            duration_ms=_duration_ms(started),
        )

    execute = run


def _duration_ms(started: float) -> float:
    return round((time.monotonic() - started) * 1000, 3)


class Sandbox:
    """Facade selecting the configured execution backend."""

    def __init__(
        self,
        config: SandboxConfig | Path | str | None = None,
        *,
        backend: SandboxBackend | str | None = None,
        **config_overrides: Any,
    ) -> None:
        if isinstance(config, (str, Path)):
            config_overrides = {"workspace": config, **config_overrides}
            config = None
        if config is None:
            config = SandboxConfig(**config_overrides)
        elif config_overrides:
            config = config.model_copy(update=config_overrides)
        sandbox_config = cast(SandboxConfig, config)
        if backend is not None:
            sandbox_config = sandbox_config.model_copy(update={"backend": backend})
        self.config = sandbox_config
        if sandbox_config.backend == SandboxBackend.LOCAL:
            self._runner: LocalSandbox | DockerSandbox = LocalSandbox(sandbox_config)
        elif sandbox_config.backend == SandboxBackend.DOCKER:
            self._runner = DockerSandbox(sandbox_config)
        else:
            raise ValueError(f"Unknown sandbox backend: {sandbox_config.backend}")

    @property
    def backend(self) -> SandboxBackend:
        return self.config.backend

    async def run(
        self,
        command: str,
        cwd: str | Path | None = None,
        *,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> SandboxResult:
        return await self._runner.run(command, cwd=cwd, env=env, timeout=timeout)

    execute = run

    async def __aenter__(self) -> Sandbox:
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None


def create_sandbox(config: SandboxConfig | None = None, **kwargs: Any) -> Sandbox:
    """Construct a :class:`Sandbox` from a config or config keyword values."""
    return Sandbox(config, **kwargs)


# Compatibility names used by callers that prefer an explicit result/backend
# name.  The aliases keep the public surface small without duplicating types.
SandboxExecutionResult = SandboxResult
HostSandbox = LocalSandbox
SandboxRunner = Sandbox
SandboxPolicy = SandboxConfig


__all__ = [
    "DockerSandbox",
    "HostSandbox",
    "LocalSandbox",
    "Sandbox",
    "SandboxBackend",
    "SandboxConfig",
    "SandboxError",
    "SandboxExecutionResult",
    "SandboxPolicy",
    "SandboxResult",
    "SandboxRunner",
    "create_sandbox",
]
