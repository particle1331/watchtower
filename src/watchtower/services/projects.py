"""Stage the uv package scaffold shared by make project and portfolio start."""

import os
import re
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from .workspace import ServiceError


def project_name(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value):
        raise ServiceError("Project name must be a single safe directory name.")
    return value


def scaffold_project(root: Path, name: str) -> dict[str, bytes]:
    name = project_name(name)
    scratch = root / ".tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="project-scaffold-", dir=scratch) as directory:
        staged = Path(directory) / name
        try:
            subprocess.run(["uv", "init", "--package", "--name", name, "--no-workspace", "--vcs", "none",
                "--python", sys.executable, "--offline", "--no-cache", "--no-python-downloads", str(staged)],
                cwd=root, env={**os.environ, "TMPDIR": str(scratch)}, check=True, capture_output=True, text=True)
        except (OSError, subprocess.CalledProcessError) as error:
            message = error.stderr if isinstance(error, subprocess.CalledProcessError) else str(error)
            raise ServiceError(f"Could not scaffold project: {message}") from error
        return {f"projects/{name}/{path.relative_to(staged).as_posix()}": path.read_bytes()
            for path in staged.rglob("*") if path.is_file()}
