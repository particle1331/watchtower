"""Tests for watchtower.scaffold — filesystem-writing functions."""


import nbformat
import pytest

from watchtower import scaffold

# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------

def test_new_post_creates_file(repo):
    path = scaffold.new_post("my-post")
    assert path == scaffold.POSTS_DIR / "my-post.ipynb"
    assert (repo / "nb" / "posts" / "my-post.ipynb").exists()


def test_new_post_custom_title(repo):
    path = scaffold.new_post("my-post", title="Custom Title")
    nb = nbformat.read(path, as_version=nbformat.NO_CONVERT)
    assert 'title: "Custom Title"' in nb.cells[0].source


def test_new_post_duplicate_raises(repo):
    scaffold.new_post("my-post")
    with pytest.raises(FileExistsError):
        scaffold.new_post("my-post")


def test_new_post_default_title_is_titleized(repo):
    path = scaffold.new_post("my-post")
    nb = nbformat.read(path, as_version=nbformat.NO_CONVERT)
    assert 'title: "My Post"' in nb.cells[0].source


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------

def test_new_course_creates_directory(repo):
    scaffold.new_course("ml", "Machine Learning")
    assert (repo / "nb" / "courses" / "ml").is_dir()
    assert (repo / "nb" / "courses" / "ml" / "index.ipynb").exists()
    assert (repo / "nb" / "courses" / "ml" / "01-introduction.ipynb").exists()


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
    scaffold.new_course_chapter("ml", "02-regression")
    assert (repo / "nb" / "courses" / "ml" / "02-regression.ipynb").exists()


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
    assert "nb/courses/ml/02-regression.ipynb" in hrefs


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
