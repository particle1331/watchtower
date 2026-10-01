"""Create a uv workspace project with make project NAME=<name>."""

import os
import sys
from pathlib import Path

ROOT_PATH = Path(__file__).resolve().parents[1]


def new_project() -> Path:
    name = os.environ.get("NAME", "").strip()
    if not name:
        raise ValueError("pass NAME=<name> to make project")
    from watchtower.services.content import ContentService

    result = ContentService(ROOT_PATH).create_project(name)
    return ROOT_PATH / result["project_path"]


if __name__ == "__main__":
    try:
        print(f"created {new_project()}")
    except (OSError, ValueError) as error:
        sys.exit(str(error))
