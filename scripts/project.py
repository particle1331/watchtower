"""Create a uv workspace project with make project NAME=<name>."""

import os
import subprocess
import sys
from pathlib import Path

ROOT_PATH = Path(__file__).resolve().parents[1]


def new_project() -> Path:
    name = os.environ.get("NAME", "").strip()
    if not name:
        raise ValueError("pass NAME=<name> to make project")
    if name in {".", ".."} or "/" in name or "\\" in name:
        raise ValueError("NAME must be a project directory name")
    path = ROOT_PATH / "projects" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["uv", "init", "--package", str(path)], cwd=ROOT_PATH, check=True)
    return path


if __name__ == "__main__":
    try:
        print(f"created {new_project()}")
    except (OSError, ValueError) as error:
        sys.exit(str(error))
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
