from pathlib import Path

from watchtower import paths


def test_repo_root_contains_project_files():
    """Find AGENTS.md and pyproject.toml in repo root."""
    root_path = paths.repo_root()
    assert (root_path / "AGENTS.md").exists()
    assert (root_path / "pyproject.toml").exists()


def test_notebook_content_is_grouped_under_nb():
    assert Path("nb") == paths.NB_DIR
    assert Path("nb/notes") == paths.NOTES_DIR
    assert Path("nb/articles") == paths.ARTICLES_DIR
    assert Path("nb/courses") == paths.COURSES_DIR
    assert Path("nb/portfolio/portfolio.ipynb") == paths.PORTFOLIO_PATH
