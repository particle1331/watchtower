"""Tests for watchtower.inspect — repo map and notebook resolution."""


import json
from pathlib import Path

import nbformat
import pytest

from watchtower import inspect as wt_inspect


@pytest.fixture
def populated_repo(tmp_path, monkeypatch):
    """Repo with one note and one course chapter (nested one level deeper)."""
    monkeypatch.chdir(tmp_path)
    nb = nbformat.v4.new_notebook()
    nb.cells = [nbformat.v4.new_markdown_cell("hello")]

    # notes tier — flat
    (tmp_path / "notes").mkdir()
    nbformat.write(nb, tmp_path / "notes" / "001-test.ipynb")
    nbformat.write(nb, tmp_path / "notes" / "index.ipynb")  # must be excluded

    # courses tier — one level deeper: courses/<course>/<chapter>.ipynb
    (tmp_path / "courses" / "ml").mkdir(parents=True)
    nbformat.write(nb, tmp_path / "courses" / "ml" / "01-intro.ipynb")
    nbformat.write(nb, tmp_path / "courses" / "ml" / "index.ipynb")  # must be excluded

    return tmp_path


# ---------------------------------------------------------------------------
# list_ipynb
# ---------------------------------------------------------------------------

def test_list_ipynb_notes(populated_repo):
    items = wt_inspect.list_ipynb(Path("notes"))
    names = [Path(i).name for i in items]
    assert "001-test.ipynb" in names


def test_list_ipynb_excludes_index(populated_repo):
    items = wt_inspect.list_ipynb(Path("notes"))
    names = [Path(i).name for i in items]
    assert "index.ipynb" not in names


def test_list_ipynb_courses_nested(populated_repo):
    items = wt_inspect.list_ipynb(Path("courses"))
    names = [Path(i).name for i in items]
    assert "01-intro.ipynb" in names
    assert "index.ipynb" not in names


def test_list_ipynb_missing_dir_returns_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert wt_inspect.list_ipynb(Path("nonexistent")) == []


# ---------------------------------------------------------------------------
# repo_map
# ---------------------------------------------------------------------------

def test_repo_map_has_expected_keys(populated_repo):
    m = wt_inspect.repo_map()
    assert {"articles", "notes", "courses", "projects"}.issubset(m.keys())


def test_repo_map_json_is_valid(populated_repo):
    out = wt_inspect.repo_map_json()
    data = json.loads(out)
    assert "notes" in data


def test_repo_map_notes_content(populated_repo):
    m = wt_inspect.repo_map()
    assert any("001-test.ipynb" in n for n in m["notes"])


def test_repo_map_courses_nested(populated_repo):
    m = wt_inspect.repo_map()
    assert any("01-intro.ipynb" in n for n in m["courses"])


# ---------------------------------------------------------------------------
# resolve_ipynb
# ---------------------------------------------------------------------------

def test_resolve_bare_stem(populated_repo):
    p = wt_inspect.resolve_ipynb("001-test")
    assert p.exists()
    assert p.name == "001-test.ipynb"


def test_resolve_tier_prefix_notes(populated_repo):
    p = wt_inspect.resolve_ipynb("notes/001-test")
    assert p.exists()


def test_resolve_tier_prefix_course(populated_repo):
    # courses are one level deeper: courses/<course>/<chapter>
    p = wt_inspect.resolve_ipynb("courses/ml/01-intro")
    assert p.exists()
    assert p.name == "01-intro.ipynb"


def test_resolve_full_path(populated_repo):
    full = str(populated_repo / "notes" / "001-test.ipynb")
    p = wt_inspect.resolve_ipynb(full)
    assert p.exists()


def test_resolve_not_found_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError, match="no ipynb"):
        wt_inspect.resolve_ipynb("nope")


# ---------------------------------------------------------------------------
# find_in_src (pure Python — no rg dependency)
# ---------------------------------------------------------------------------

def test_find_returns_matching_lines(populated_repo):
    out = wt_inspect.find_in_src("hello")
    assert "001-test.ipynb" in out
    assert "[cell 0]" in out


def test_find_is_case_insensitive(populated_repo):
    out = wt_inspect.find_in_src("HELLO")
    assert "001-test.ipynb" in out


def test_find_no_match_returns_empty(populated_repo):
    out = wt_inspect.find_in_src("zzz_no_match_xyz")
    assert out == ""


def test_find_searches_courses(populated_repo):
    out = wt_inspect.find_in_src("hello")
    assert "01-intro.ipynb" in out
