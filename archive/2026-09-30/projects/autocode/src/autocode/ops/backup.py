"""Portable backup and restore primitives for the local data tier."""

from __future__ import annotations

import shutil
from pathlib import Path


def backup_directory(source: str | Path, destination: str | Path) -> Path:
    source = Path(source)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)
    return destination


def restore_directory(backup: str | Path, destination: str | Path) -> Path:
    return backup_directory(backup, destination)
