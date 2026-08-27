from pathlib import Path

import pytest

from proof_lm.artifacts import artifact_path, ensure_artifact_root
from proof_lm.config import load_config


def test_named_profiles_are_complete_and_distinct() -> None:
    smoke = load_config("smoke")
    standard = load_config("standard")
    assert smoke.name == "smoke"
    assert standard.name == "standard"
    assert smoke.device == "cpu"
    assert standard.device == "cuda"
    assert smoke.artifact_root == "artifacts"
    assert standard.output_namespace == "prooflm/standard"
    assert smoke.training.token_budget == 2_000_000
    assert standard.training.token_budget == 1_000_000_000
    assert smoke.config_id != standard.config_id


def test_unknown_profile_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown ProofLM profile"):
        load_config("debug")


def test_artifact_root_has_stable_categories_and_safe_paths(tmp_path: Path) -> None:
    root = ensure_artifact_root(tmp_path / "artifacts")
    assert (root / "checkpoints").is_dir()
    assert artifact_path(root, "reports", "report-v1") == root / "reports" / "report-v1"
    with pytest.raises(ValueError):
        artifact_path(root, "reports", "../outside")
    with pytest.raises(ValueError):
        artifact_path(root, "unknown", "report-v1")
