from watchtower import paths


def test_repo_root_contains_project_files():
    """Find AGENTS.md and pyproject.toml in repo root."""
    root_path = paths.repo_root()
    assert (root_path / "AGENTS.md").exists()
    assert (root_path / "pyproject.toml").exists()
