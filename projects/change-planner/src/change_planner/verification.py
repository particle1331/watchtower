"""Bounded, explicitly authorized test execution for local repositories."""

import hashlib
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from change_planner.schemas import VerificationResult

DEFAULT_ALLOWED_PROGRAMS = frozenset({"python", "python3", Path(sys.executable).name, "pytest"})


def run_targeted_test(
    root: str | Path,
    command: Sequence[str],
    *,
    authorized: bool,
    timeout_seconds: float = 30.0,
    allowed_programs: frozenset[str] = DEFAULT_ALLOWED_PROGRAMS,
) -> VerificationResult:
    """Run one argument-vector command, never through a shell.

    The caller must explicitly authorize execution. Shell interpreters and
    commands outside the allowlist are recorded as blocked, not attempted.
    Standard output and error are retained for inspection and fingerprinted so
    a later plan can distinguish repeated or changed observations.
    """

    root_path = Path(root).resolve()
    argv = list(command)
    started = time.monotonic()
    if not argv:
        return _result(argv, root_path, "blocked", None, "", "empty command", started)
    program = Path(argv[0]).name
    if not authorized:
        return _result(argv, root_path, "blocked", None, "", "execution policy denied", started)
    if program not in allowed_programs:
        return _result(argv, root_path, "blocked", None, "", f"program not allowed: {program}", started)
    if not root_path.is_dir():
        return _result(argv, root_path, "blocked", None, "", "working directory is missing", started)
    try:
        completed = subprocess.run(
            argv,
            cwd=root_path,
            capture_output=True,
            check=False,
            shell=False,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = _text(exc.stdout)
        stderr = _text(exc.stderr)
        return _result(argv, root_path, "timed_out", None, stdout, stderr, started)
    status = "passed" if completed.returncode == 0 else "failed"
    return _result(
        argv,
        root_path,
        status,
        completed.returncode,
        completed.stdout,
        completed.stderr,
        started,
    )


def _text(value: bytes | str | None) -> str:
    if value is None:
        return ""
    return value.decode(errors="replace") if isinstance(value, bytes) else value


def _result(
    command: list[str],
    root: Path,
    status: Literal["passed", "failed", "blocked", "timed_out"],
    returncode: int | None,
    stdout: str,
    stderr: str,
    started: float,
) -> VerificationResult:
    payload = stdout + "\x00" + stderr
    fingerprint = hashlib.sha256(payload.encode()).hexdigest()
    return VerificationResult(
        command=command,
        cwd=str(root),
        status=status,
        returncode=returncode,
        output_fingerprint=f"sha256:{fingerprint}",
        stdout=stdout,
        stderr=stderr,
        duration_ms=max(0, round((time.monotonic() - started) * 1000)),
        reason="command completed successfully" if status == "passed" else (stderr or status),
    )
