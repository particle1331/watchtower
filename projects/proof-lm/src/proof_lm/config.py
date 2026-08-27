"""Loading and inspecting the named ProofLM execution profiles."""

from __future__ import annotations

from pathlib import Path

import yaml

from .schemas import RunConfig

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_ROOT = PROJECT_ROOT / "configs"


def config_path(name: str, config_root: Path = CONFIG_ROOT) -> Path:
    """Return the path for a named profile without accepting path traversal."""

    if name not in {"smoke", "standard"}:
        raise ValueError(f"unknown ProofLM profile: {name}")
    return config_root / f"{name}.yaml"


def load_config(name: str, config_root: Path = CONFIG_ROOT) -> RunConfig:
    """Load and validate one of the course's named profiles."""

    path = config_path(name, config_root)
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    return RunConfig.model_validate(raw)
