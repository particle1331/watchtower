"""Tests for watchtower.problems — resolver, formatters, and CLI commands."""


import io
import json

import nbformat
import pytest
from rich.console import Console
from typer.testing import CliRunner

from watchtower import cli, problems

runner = CliRunner()

PROBLEMS = {
    "course": "cla",
    "problems": [
        {
            "chapter": "01-foundations",
            "id": "01-1",
            "title": "Frobenius submultiplicativity",
            "type": "theory",
            "parts": ["(a)", "(b)", "(c)"],
            "statement": "Show that ||AB||_F <= ||A||_F ||B||_F.",
            "solution": {
                "text": "Apply Cauchy-Schwarz.",
                "answer": "||AB||_F <= ||A||_F ||B||_F",
            },
        },
        {
            "chapter": "02-spectral-theorem",
            "id": "02-1",
            "title": "Rayleigh quotient bounds",
            "type": "theory",
            "parts": ["(a)", "(b)", "(c)"],
            "statement": "Show lambda_min <= R_A(x) <= lambda_max.",
            "solution": {
                "text": "Write x in the eigenbasis.",
                "answer": "lambda_min <= R_A(x) <= lambda_max",
            },
        },
        {
            "chapter": "07-projection-and-orthogonalization",
            "id": "07-3",
            "title": "Three routes to the projector",
            "type": "implementation",
            "parts": ["(a)", "(b)"],
            "statement": "Build the projector onto the column space of A three ways.",
            "starter_code": "import numpy as np\nA = np.array([[1.0, 2.0], [3.0, 4.0]])",
            "solution": {
                "text": "All three routes agree to machine precision.",
                "answer": "P = A (A^T A)^{-1} A^T",
                "checks": [
                    {"description": "max deviation", "expected": 0.0, "tolerance": 1e-12},
                ],
                "code": "import numpy as np\nP = A @ np.linalg.inv(A.T @ A) @ A.T",
            },
        },
    ],
}


@pytest.fixture
def problems_file(tmp_path, monkeypatch):
    """cwd = tmp_path with courses/cla/problems.json written."""
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "courses" / "cla" / "problems.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(PROBLEMS), encoding="utf-8")
    return path


@pytest.fixture
def cli_console(monkeypatch):
    """Redirect the module-level rich console into a buffer for assertions."""
    buf = io.StringIO()
    monkeypatch.setattr(cli, "console", Console(file=buf, force_terminal=False))
    return buf


# ---------------------------------------------------------------------------
# resolver
# ---------------------------------------------------------------------------

def test_resolve_dot_form(problems_file):
    p = problems.resolve_problem(problems.load_problems("cla"), "7.3")
    assert p["id"] == "07-3"


def test_resolve_full_id_form(problems_file):
    p = problems.resolve_problem(problems.load_problems("cla"), "07-3")
    assert p["id"] == "07-3"


def test_resolve_space_number_form(problems_file):
    p = problems.resolve_problem(problems.load_problems("cla"), "07 3")
    assert p["id"] == "07-3"


def test_resolve_stem_form(problems_file):
    p = problems.resolve_problem(
        problems.load_problems("cla"), "07-projection-and-orthogonalization 3"
    )
    assert p["id"] == "07-3"


def test_resolve_fuzzy_form(problems_file):
    p = problems.resolve_problem(problems.load_problems("cla"), "projection 3")
    assert p["id"] == "07-3"


def test_resolve_numeric_chapter_exact(problems_file):
    p = problems.resolve_problem(problems.load_problems("cla"), "1.1")
    assert p["id"] == "01-1"


def test_resolve_invalid_raises(problems_file):
    with pytest.raises(ValueError):
        problems.resolve_problem(problems.load_problems("cla"), "99.1")


def test_resolve_ambiguous_raises(problems_file):
    with pytest.raises(ValueError):
        problems.resolve_problem(problems.load_problems("cla"), "a 1")


# ---------------------------------------------------------------------------
# formatters
# ---------------------------------------------------------------------------

def test_format_problem(problems_file):
    p = problems.resolve_problem(problems.load_problems("cla"), "7.3")
    out = problems.format_problem(p)
    assert "### Problem 3 — Three routes to the projector" in out
    assert "Build the projector onto the column space of A three ways." in out
    assert "```python" in out
    assert "import numpy as np" in out


def test_format_solution(problems_file):
    p = problems.resolve_problem(problems.load_problems("cla"), "7.3")
    out = problems.format_solution(p)
    assert "### Problem 3 — Three routes to the projector" in out
    assert "**Solution.**" in out
    assert "All three routes agree to machine precision." in out
    assert "**Answer:**" in out
    assert "P = A (A^T A)^{-1} A^T" in out
    assert "expected 0.0 ± 1e-12" in out
    assert "**Reference code.**" in out
    assert "```python" in out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def test_cli_problem(problems_file):
    result = runner.invoke(cli.app, ["problem", "cla", "7.3"])
    assert result.exit_code == 0
    assert "### Problem 3 — Three routes to the projector" in result.output
    assert "Build the projector onto the column space of A three ways." in result.output


def test_cli_solution(problems_file):
    result = runner.invoke(cli.app, ["solution", "cla", "7.3"])
    assert result.exit_code == 0
    assert "**Solution.**" in result.output
    assert "All three routes agree to machine precision." in result.output


def test_cli_missing_file(tmp_path, monkeypatch, cli_console):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(cli.app, ["problem", "nope", "7.3"])
    assert result.exit_code == 1
    assert "no problems file" in cli_console.getvalue()


# ---------------------------------------------------------------------------
# sync-problems
# ---------------------------------------------------------------------------

STMT_01 = (
    "### Problem 1 — Frobenius submultiplicativity\n\n"
    "Show that ||AB||_F <= ||A||_F ||B||_F."
)
STMT_02 = (
    "### Problem 1 — Rayleigh quotient bounds\n\n"
    "Show lambda_min <= R_A(x) <= lambda_max."
)
STMT_07 = (
    "### Problem 3 — Three routes to the projector\n\n"
    "Build the projector onto the column space of A three ways."
)
STARTER_07 = "import numpy as np\nA = np.array([[1.0, 2.0], [3.0, 4.0]])"


def _problem_cell(source: str) -> nbformat.NotebookNode:
    """A markdown cell tagged ``problem`` (a statement cell)."""
    cell = nbformat.v4.new_markdown_cell(source)
    cell.metadata["tags"] = ["problem"]
    return cell


@pytest.fixture
def sync_course(tmp_path, monkeypatch):
    """cwd = tmp_path with courses/cla/problems.json plus chapter notebooks
    whose problem cells match the fixture problems by order (in sync)."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path / "courses" / "cla"
    base.mkdir(parents=True, exist_ok=True)
    data = {
        "course": PROBLEMS["course"],
        "problems": [dict(p) for p in PROBLEMS["problems"]],
    }
    data["problems"][0]["statement"] = STMT_01
    data["problems"][1]["statement"] = STMT_02
    data["problems"][2]["statement"] = STMT_07
    (base / "problems.json").write_text(json.dumps(data), encoding="utf-8")

    def write_notebook(name, cells):
        nb = nbformat.v4.new_notebook()
        nb.cells = cells
        nbformat.write(nb, base / name)

    write_notebook("01-foundations.ipynb", [_problem_cell(STMT_01)])
    write_notebook("02-spectral-theorem.ipynb", [_problem_cell(STMT_02)])
    write_notebook(
        "07-projection-and-orthogonalization.ipynb",
        [_problem_cell(STMT_07), nbformat.v4.new_code_cell(STARTER_07)],
    )
    return base


def test_sync_updates_and_preserves(sync_course):
    # simulate drift: stale statement + missing starter in the JSON
    data = problems.load_problems("cla")
    data["problems"][0]["statement"] = "OLD STATEMENT"
    data["problems"][2].pop("starter_code")
    (sync_course / "problems.json").write_text(json.dumps(data), encoding="utf-8")

    warnings = problems.sync_problems("cla")
    assert len(warnings) == 2  # 01-1 statement and 07-3 starter changed

    data = problems.load_problems("cla")
    p1 = data["problems"][0]
    assert p1["statement"] == STMT_01
    assert p1["title"] == "Frobenius submultiplicativity"
    assert p1["type"] == "theory"
    assert p1["parts"] == ["(a)", "(b)", "(c)"]
    assert p1["solution"]["answer"] == "||AB||_F <= ||A||_F ||B||_F"
    p3 = data["problems"][2]
    assert p3["statement"] == STMT_07
    assert p3["starter_code"] == STARTER_07
    assert p3["solution"]["code"].startswith("import numpy as np\nP = A @")
    # written with indent=2, ensure_ascii=False, trailing newline
    raw = (sync_course / "problems.json").read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert '  "problems": [' in raw


def test_sync_no_warnings_when_in_sync(sync_course):
    assert problems.sync_problems("cla") == []


def test_sync_warns_when_statement_changed(sync_course):
    nb = nbformat.read(
        sync_course / "01-foundations.ipynb", as_version=nbformat.NO_CONVERT
    )
    nb.cells[0].source = "### Problem 1 — Frobenius submultiplicativity\n\nNEW STATEMENT"
    nbformat.write(nb, sync_course / "01-foundations.ipynb")

    warnings = problems.sync_problems("cla")
    assert warnings == [
        "01-1 statement/starter changed — verify the solution in problems.json "
        "is still accurate"
    ]
    assert problems.load_problems("cla")["problems"][0]["statement"].endswith(
        "NEW STATEMENT"
    )


def test_sync_warns_for_notebook_problem_missing_from_json(sync_course):
    nb = nbformat.read(
        sync_course / "01-foundations.ipynb", as_version=nbformat.NO_CONVERT
    )
    nb.cells.append(_problem_cell("### Problem 2 — Extra problem\n\nNot in JSON."))
    nbformat.write(nb, sync_course / "01-foundations.ipynb")

    warnings = problems.sync_problems("cla")
    assert (
        "01-foundations: problem 2 in notebook has no entry in problems.json — "
        "add it manually" in warnings
    )


def test_sync_warns_for_json_problem_without_cell(sync_course):
    nb = nbformat.read(
        sync_course / "07-projection-and-orthogonalization.ipynb",
        as_version=nbformat.NO_CONVERT,
    )
    nb.cells = [c for c in nb.cells if "problem" not in c.metadata.get("tags", [])]
    nbformat.write(nb, sync_course / "07-projection-and-orthogonalization.ipynb")

    warnings = problems.sync_problems("cla")
    assert (
        "07-3 in problems.json has no matching problem cell in "
        "07-projection-and-orthogonalization notebook" in warnings
    )


def test_cli_sync_problems(sync_course):
    result = runner.invoke(cli.app, ["sync-problems", "cla"])
    assert result.exit_code == 0
    assert "synced problems for cla (3 problems, 0 changed)" in result.output


def test_cli_sync_problems_missing_course(tmp_path, monkeypatch, cli_console):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(cli.app, ["sync-problems", "nope"])
    assert result.exit_code == 1
    assert "no problems file" in cli_console.getvalue()