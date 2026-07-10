"""Scaffold new artifacts: notes, writings, projects.

New notebooks are minimal `.ipynb` files with a Python kernelspec. Pairing to
the mirror is driven by the sync module (no jupytext metadata in the notebook).
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

NOTES_SRC = Path("notes/src")
WRITINGS_SRC = Path("writings/src")
PROJECTS = Path("projects")


def _minimal_notebook() -> dict:
    return {
        "cells": [],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def _write_nb(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_minimal_notebook(), indent=1))


def new_note(name: str) -> Path:
    """Create notes/src/<name>.ipynb.

    The mirror is regenerated on the next `wt sync` — no jupytext metadata
    is embedded in the notebook; pairing is driven by sync.py.
    """
    path = NOTES_SRC / f"{name}.ipynb"
    _write_nb(path)
    return path


def new_writing(slug: str) -> Path:
    """Create writings/src/<YYYY-MM-DD>-<slug>.ipynb."""
    date = datetime.now().strftime("%Y-%m-%d")
    path = WRITINGS_SRC / f"{date}-{slug}.ipynb"
    _write_nb(path)
    return path


def new_project(name: str) -> Path:
    """uv init projects/<name> as a workspace member."""
    path = PROJECTS / name
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["uv", "init", "--package", str(path)], check=True)
    return path