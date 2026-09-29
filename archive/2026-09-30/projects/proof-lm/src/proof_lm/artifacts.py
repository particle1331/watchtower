"""Project-owned paths for large, reproducible-but-untracked artifacts."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_ROOT = PROJECT_ROOT / "artifacts"
ARTIFACT_KINDS = ("checkpoints", "datasets", "reports", "runs", "tokenizers")


def ensure_artifact_root(root: Path = DEFAULT_ARTIFACT_ROOT) -> Path:
    """Create the ignored root and its stable category directories."""

    root.mkdir(parents=True, exist_ok=True)
    for kind in ARTIFACT_KINDS:
        (root / kind).mkdir(exist_ok=True)
    return root


def artifact_path(root: Path, kind: str, artifact_id: str) -> Path:
    """Resolve one artifact path while rejecting traversal and unknown kinds."""

    if kind not in ARTIFACT_KINDS:
        raise ValueError(f"unknown artifact kind: {kind}")
    if not artifact_id or Path(artifact_id).name != artifact_id:
        raise ValueError("artifact_id must be one path component")
    return root / kind / artifact_id
