"""Tests for watchtower.scaffold — filesystem-writing functions."""

from __future__ import annotations

import nbformat
import pytest

from watchtower import scaffold


# ---------------------------------------------------------------------------
# Notes and articles
# ---------------------------------------------------------------------------

def test_new_note_creates_file(repo):
    path = scaffold.new_note("my-note")
    assert path == scaffold.NOTES_DIR / "my-note.ipynb"
    assert (repo / "notes" / "my-note.ipynb").exists()


def test_new_note_custom_title(repo):
    path = scaffold.new_note("my-note", title="Custom Title")
    nb = nbformat.read(path, as_version=nbformat.NO_CONVERT)
    assert 'title: "Custom Title"' in nb.cells[0].source


def test_new_note_default_title_is_name(repo):
    path = scaffold.new_note("my-note")
    nb = nbformat.read(path, as_version=nbformat.NO_CONVERT)
    assert 'title: "my-note"' in nb.cells[0].source


def test_new_article_creates_file(repo):
    path = scaffold.new_article("svd")
    assert (repo / "articles" / "svd.ipynb").exists()


def test_new_article_derives_title(repo):
    path = scaffold.new_article("singular-value-decomposition")
    nb = nbformat.read(path, as_version=nbformat.NO_CONVERT)
    assert 'title: "Singular Value Decomposition"' in nb.cells[0].source


def test_new_article_custom_title(repo):
    path = scaffold.new_article("svd", title="SVD Deep Dive")
    nb = nbformat.read(path, as_version=nbformat.NO_CONVERT)
    assert 'title: "SVD Deep Dive"' in nb.cells[0].source


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------

def test_new_course_creates_directory(repo):
    course_dir = scaffold.new_course("ml", "Machine Learning")
    assert (repo / "courses" / "ml").is_dir()
    assert (repo / "courses" / "ml" / "index.ipynb").exists()
    assert (repo / "courses" / "ml" / "01-introduction.ipynb").exists()


def test_new_course_registers_sidebar(repo):
    scaffold.new_course("ml", "Machine Learning")
    data = scaffold._load_yaml(repo / "_quarto.yml")
    sidebar = data["website"]["sidebar"]
    ids = [e.get("id") for e in sidebar if isinstance(e, dict)]
    assert "ml" in ids


def test_new_course_idempotent_registration(repo):
    scaffold.new_course("ml", "Machine Learning")
    scaffold.new_course("ml", "Machine Learning")  # second call should not duplicate
    data = scaffold._load_yaml(repo / "_quarto.yml")
    ids = [e.get("id") for e in data["website"]["sidebar"] if isinstance(e, dict)]
    assert ids.count("ml") == 1


# ---------------------------------------------------------------------------
# Chapters
# ---------------------------------------------------------------------------

def test_new_chapter_creates_file(repo):
    scaffold.new_course("ml", "Machine Learning")
    path = scaffold.new_course_chapter("ml", "02-regression")
    assert (repo / "courses" / "ml" / "02-regression.ipynb").exists()


def test_new_chapter_derives_title(repo):
    scaffold.new_course("ml", "Machine Learning")
    path = scaffold.new_course_chapter("ml", "02-linear-regression")
    nb = nbformat.read(path, as_version=nbformat.NO_CONVERT)
    assert 'title: "02 Linear Regression"' in nb.cells[0].source


def test_new_chapter_custom_title(repo):
    scaffold.new_course("ml", "Machine Learning")
    path = scaffold.new_course_chapter("ml", "02-regression", title="Linear Regression")
    nb = nbformat.read(path, as_version=nbformat.NO_CONVERT)
    assert 'title: "Linear Regression"' in nb.cells[0].source


def test_new_chapter_registered_in_sidebar(repo):
    scaffold.new_course("ml", "Machine Learning")
    scaffold.new_course_chapter("ml", "02-regression", title="Regression")
    data = scaffold._load_yaml(repo / "_quarto.yml")
    entry = scaffold._find_course_sidebar_entry(data, "ml")
    hrefs = [
        c.get("href")
        for section in entry["contents"]
        if isinstance(section, dict)
        for c in section.get("contents", [])
        if isinstance(c, dict)
    ]
    assert "courses/ml/02-regression.ipynb" in hrefs


def test_new_chapter_missing_course_raises(repo):
    with pytest.raises(FileNotFoundError):
        scaffold.new_course_chapter("nonexistent", "01-intro")


def test_new_chapter_duplicate_raises(repo):
    scaffold.new_course("ml", "Machine Learning")
    scaffold.new_course_chapter("ml", "02-regression")
    with pytest.raises(FileExistsError):
        scaffold.new_course_chapter("ml", "02-regression")


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def test_new_section_added_to_sidebar(repo):
    scaffold.new_course("ml", "Machine Learning")
    scaffold.new_course_section("ml", "Advanced Topics")
    data = scaffold._load_yaml(repo / "_quarto.yml")
    entry = scaffold._find_course_sidebar_entry(data, "ml")
    sections = [c.get("section") for c in entry["contents"] if isinstance(c, dict)]
    assert "Advanced Topics" in sections


def test_new_chapter_in_named_section(repo):
    scaffold.new_course("ml", "Machine Learning")
    scaffold.new_course_section("ml", "Advanced Topics")
    path = scaffold.new_course_chapter("ml", "03-svm", section="Advanced Topics")
    assert path.exists()


def test_new_chapter_missing_section_raises(repo):
    scaffold.new_course("ml", "Machine Learning")
    with pytest.raises(ValueError, match="section 'Nonexistent'"):
        scaffold.new_course_chapter("ml", "03-svm", section="Nonexistent")


def test_new_section_missing_course_raises(repo):
    with pytest.raises(FileNotFoundError):
        scaffold.new_course_section("nonexistent", "Part 1")


def test_new_section_duplicate_raises(repo):
    scaffold.new_course("ml", "Machine Learning")
    scaffold.new_course_section("ml", "Part 1")
    with pytest.raises(ValueError, match="already exists"):
        scaffold.new_course_section("ml", "Part 1")
