"""Tests for watchtower.problems — resolver, formatters, writes, and CLI commands."""


import io

import nbformat
import pytest
from rich.console import Console
from typer.testing import CliRunner

from watchtower import cli, obfuscate, problems

runner = CliRunner()


def make_notebook(path, cells):
    """Write a minimal notebook to *path* (creates parent dirs)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    nb = nbformat.v4.new_notebook()
    nb.cells = cells
    nbformat.write(nb, path)
    return path

# Per-problem spec: statement heading + body, optional starter, solution dict.
# Chapters 01/02 hold theory problems (no starter); 07-3 is an implementation
# problem with starter + checks + reference code.
SPECS = {
    "01-foundations": [
        {
            "number": 1,
            "title": "Frobenius submultiplicativity",
            "statement": "Show that ||AB||_F <= ||A||_F ||B||_F.",
            "solution": {
                "text": "Apply Cauchy-Schwarz.",
                "answer": "||AB||_F <= ||A||_F ||B||_F",
            },
        },
    ],
    "02-spectral-theorem": [
        {
            "number": 1,
            "title": "Rayleigh quotient bounds",
            "statement": "Show lambda_min <= R_A(x) <= lambda_max.",
            "solution": {
                "text": "Write x in the eigenbasis.",
                "answer": "lambda_min <= R_A(x) <= lambda_max",
            },
        },
    ],
    "07-projection-and-orthogonalization": [
        {
            "number": 3,
            "title": "Three routes to the projector",
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


def heading(chapter: int, num: int, title: str) -> str:
    return f"### [P{chapter}.{num}] {title}"


def build_course(base):
    """Build nb/courses/demo chapter notebooks from SPECS using wt add-exercise."""
    for stem, probs in SPECS.items():
        chapter = base / "nb" / "courses" / "demo" / f"{stem}.ipynb"
        if not chapter.exists():
            make_notebook(
                chapter,
                [nbformat.v4.new_markdown_cell(f"# {stem}")],
            )
        chapter_num = int("".join(ch for ch in stem if ch.isdigit()))
        for p in probs:
            problems.add_exercise(
                "demo",
                stem,
                f"{heading(chapter_num, p['number'], p['title'])}\n\n{p['statement']}",
                problems.format_solution_body(p["solution"]),
                starter=p.get("starter_code"),
                number=p["number"],
            )


@pytest.fixture
def course(tmp_path, monkeypatch):
    """cwd = tmp_path with a synthetic demo course built from SPECS."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "nb" / "courses" / "demo").mkdir(parents=True)
    build_course(tmp_path)
    return tmp_path


@pytest.fixture
def cli_console(monkeypatch):
    """Redirect the module-level rich console into a buffer for assertions."""
    buf = io.StringIO()
    monkeypatch.setattr(cli, "console", Console(file=buf, force_terminal=False))
    return buf


# ---------------------------------------------------------------------------
# resolver
# ---------------------------------------------------------------------------

def test_resolve_dot_form(course):
    p = problems.resolve_problem("demo", "7.3")
    assert p["id"] == "07-3"
    assert p["title"] == "Three routes to the projector"


def test_resolve_full_id_form(course):
    assert problems.resolve_problem("demo", "07-3")["id"] == "07-3"


def test_resolve_space_number_form(course):
    assert problems.resolve_problem("demo", "07 3")["id"] == "07-3"


def test_resolve_stem_form(course):
    assert (
        problems.resolve_problem("demo", "07-projection-and-orthogonalization 3")["id"]
        == "07-3"
    )


def test_resolve_fuzzy_form(course):
    assert problems.resolve_problem("demo", "projection 3")["id"] == "07-3"


def test_resolve_numeric_chapter_exact(course):
    assert problems.resolve_problem("demo", "1.1")["id"] == "01-1"


def test_resolve_invalid_raises(course):
    with pytest.raises(ValueError):
        problems.resolve_problem("demo", "99.1")


def test_resolve_ambiguous_raises(course):
    with pytest.raises(ValueError):
        problems.resolve_problem("demo", "a 1")


def test_resolve_missing_problem(course):
    with pytest.raises(ValueError, match="no problem 07-9"):
        problems.resolve_problem("demo", "7.9")


def test_resolve_no_starter(course):
    p = problems.resolve_problem("demo", "1.1")
    assert p["starter_code"] is None


# ---------------------------------------------------------------------------
# formatters
# ---------------------------------------------------------------------------

def test_format_problem(course):
    out = problems.format_problem(problems.resolve_problem("demo", "7.3"))
    assert "### [P7.3] Three routes to the projector" in out
    assert "Build the projector onto the column space of A three ways." in out
    assert "```python" in out
    assert "import numpy as np" in out


def test_format_problem_no_starter(course):
    out = problems.format_problem(problems.resolve_problem("demo", "1.1"))
    assert "### [P1.1] Frobenius submultiplicativity" in out
    assert "```python" not in out


def test_solution_plaintext(course):
    body = problems.solution_plaintext(problems.resolve_problem("demo", "7.3"))
    assert "**Solution.**" in body
    assert "All three routes agree to machine precision." in body
    assert "**Answer:**" in body
    assert "P = A (A^T A)^{-1} A^T" in body
    assert "expected 0.0 ± 1e-12" in body
    assert "**Reference code.**" in body
    assert "```python" in body


def test_stored_solution_is_encoded(course):
    prob = problems.resolve_problem("demo", "7.3")
    source = prob["solution_source"]
    assert obfuscate.is_wrapped(source)
    body = obfuscate.deobfuscate(obfuscate.unwrap(source))
    assert body == problems.format_solution_body(SPECS["07-projection-and-orthogonalization"][0]["solution"])


# ---------------------------------------------------------------------------
# hints
# ---------------------------------------------------------------------------

def test_hint_level1(course):
    hint = problems.hint_text(problems.resolve_problem("demo", "7.3"), level=1)
    assert "max deviation" in hint          # check description
    assert "expected" not in hint           # no expected values
    assert "0.0" not in hint
    assert "Hint:" in hint
    assert "All three routes agree to machine precision" in hint


def test_hint_level2(course):
    hint = problems.hint_text(problems.resolve_problem("demo", "7.3"), level=2)
    assert "All three routes agree to machine precision." in hint
    assert "P = A (A^T A)^{-1} A^T" not in hint   # never the answer
    assert "expected 0.0" not in hint


def test_hint_invalid_level(course):
    with pytest.raises(ValueError):
        problems.hint_text(problems.resolve_problem("demo", "7.3"), level=3)


# ---------------------------------------------------------------------------
# writes: add-exercise / solution-edit
# ---------------------------------------------------------------------------

def test_add_exercise_auto_number(course):
    pid, path = problems.add_exercise(
        "demo",
        "02",
        "### [P2.2] New theorem\n\nProve it.",
        "**Solution.** Trivial.",
    )
    assert pid == "02-2"
    nb = nbformat.read(path, as_version=nbformat.NO_CONVERT)
    stmt = nb.cells[-2]
    sol = nb.cells[-1]
    assert stmt.cell_type == "markdown"
    assert set(stmt.metadata["tags"]) == {"problem", "02-2"}
    assert "New theorem" in stmt.source
    assert sol.cell_type == "code"
    assert set(sol.metadata["tags"]) == {"solution", "02-2"}
    assert sol.source.startswith("#| echo: false")
    assert obfuscate.is_wrapped(sol.source)
    assert obfuscate.deobfuscate(obfuscate.unwrap(sol.source)) == "**Solution.** Trivial."
    assert problems.check_course("demo") == []


def test_add_exercise_with_starter(course):
    pid, path = problems.add_exercise(
        "demo", "07", "Extra exercise", "**Solution.** Done.",
        starter="x = 1", number=9,
    )
    assert pid == "07-9"
    nb = nbformat.read(path, as_version=nbformat.NO_CONVERT)
    assert [c.cell_type for c in nb.cells[-3:]] == ["markdown", "code", "code"]
    assert nb.cells[-2].source == "x = 1"
    prob = problems.resolve_problem("demo", "7.9")
    assert prob["starter_code"] == "x = 1"
    assert problems.check_course("demo") == []


def test_add_exercise_synthesizes_heading(course):
    pid, path = problems.add_exercise(
        "demo", "01", "No heading here.", "**Solution.** Fine.",
    )
    assert pid == "01-2"
    nb = nbformat.read(path, as_version=nbformat.NO_CONVERT)
    assert nb.cells[-2].source.startswith("### [P1.2]")


def test_legacy_heading_backward_compat(course):
    # Legacy `### (PNN.N) Title`, `### Problem N — Title`, and
    # `### Problem NN-N — Title` headings still parse through
    # _heading_title and render verbatim via format_problem.
    assert problems._heading_title("### (P4.2) Title\n\nBody.") == "Title"
    assert problems._heading_title("### Problem 4 — Title\n\nBody.") == "Title"
    assert problems._heading_title("### Problem 13-1 — Title\n\nBody.") == "Title"
    problems.add_exercise(
        "demo", "07", "### Problem 4 — Legacy title\n\nBody.", "**Solution.** Fine.",
        number=4,
    )
    prob = problems.resolve_problem("demo", "7.4")
    assert prob["title"] == "Legacy title"
    out = problems.format_problem(prob)
    assert "### Problem 4 — Legacy title" in out
    assert "Body." in out
    assert problems.check_course("demo") == []


def test_add_exercise_duplicate_raises(course):
    with pytest.raises(ValueError, match="already exists"):
        problems.add_exercise(
            "demo", "01", "Dup.", "**Solution.** No.", number=1,
        )


def test_set_solution_updates(course):
    prob = problems.resolve_problem("demo", "7.3")
    sidx = prob["solution_index"]
    problems.set_solution("demo", "7.3", "**Solution.** New text.")
    nb = nbformat.read(prob["path"], as_version=nbformat.NO_CONVERT)
    assert nb.cells[sidx]["cell_type"] == "code"
    assert obfuscate.deobfuscate(obfuscate.unwrap(nb.cells[sidx]["source"])) == "**Solution.** New text."
    assert problems.check_course("demo") == []


def test_set_solution_creates_for_missing(course):
    # 07-5 does not exist; problem 07-3 has a solution already — add 07-4
    problems.add_exercise(
        "demo", "07", "### [P7.4] Gap\n\nFill it.", "**Solution.** Filled.",
        number=4,
    )
    # replace it via solution-edit
    problems.set_solution("demo", "7.4", "**Solution.** Replaced.")
    prob = problems.resolve_problem("demo", "7.4")
    assert problems.solution_plaintext(prob) == "**Solution.** Replaced."
    assert problems.check_course("demo") == []


# ---------------------------------------------------------------------------
# wt check
# ---------------------------------------------------------------------------

def test_check_clean(course):
    assert problems.check_course("demo") == []


def test_check_warns_plaintext_solution(course):
    nb = nbformat.read(
        problems._chapter_path("demo", "01-foundations"),
        as_version=nbformat.NO_CONVERT,
    )
    for c in nb.cells:
        if "solution" in c.metadata.get("tags", []):
            c.source = "#| echo: false\n#| eval: false\n#| output: false\n# **Solution.** Plaintext leak."
    nbformat.write(nb, problems._chapter_path("demo", "01-foundations"))
    warnings = problems.check_course("demo")
    assert any("01-1 appears to be stored in plaintext" in w for w in warnings)


def test_check_warns_unwrapped_solution(course):
    nb = nbformat.read(
        problems._chapter_path("demo", "02-spectral-theorem"),
        as_version=nbformat.NO_CONVERT,
    )
    for c in nb.cells:
        if "solution" in c.metadata.get("tags", []):
            c.source = obfuscate.obfuscate("**Solution.** Bare.")
    nbformat.write(nb, problems._chapter_path("demo", "02-spectral-theorem"))
    warnings = problems.check_course("demo")
    assert any(
        "02-1 is not wrapped in the `#| echo: false / eval: false / output: false` header" in w
        for w in warnings
    )


def test_check_warns_empty_solution(course):
    nb = nbformat.read(
        problems._chapter_path("demo", "01-foundations"),
        as_version=nbformat.NO_CONVERT,
    )
    for c in nb.cells:
        if "solution" in c.metadata.get("tags", []):
            c.source = obfuscate.wrap("")
    nbformat.write(nb, problems._chapter_path("demo", "01-foundations"))
    warnings = problems.check_course("demo")
    assert any("has an empty body" in w for w in warnings)


def test_check_warns_markdown_solution_cell(course):
    nb = nbformat.read(
        problems._chapter_path("demo", "01-foundations"),
        as_version=nbformat.NO_CONVERT,
    )
    for c in nb.cells:
        if "solution" in c.metadata.get("tags", []):
            c.cell_type = "markdown"
    nbformat.write(nb, problems._chapter_path("demo", "01-foundations"))
    warnings = problems.check_course("demo")
    assert any("solution cell" in w and "markdown" in w for w in warnings)


def test_check_warns_missing_pair(course):
    nb = nbformat.read(
        problems._chapter_path("demo", "01-foundations"),
        as_version=nbformat.NO_CONVERT,
    )
    nb.cells = [c for c in nb.cells if "solution" not in c.metadata.get("tags", [])]
    nbformat.write(nb, problems._chapter_path("demo", "01-foundations"))
    warnings = problems.check_course("demo")
    assert any("problem 01-1 has no solution cell" in w for w in warnings)


def _first_pair_cells(nb):
    prob = sol = None
    for c in nb.cells:
        tags = c.metadata.get("tags", [])
        if "problem" in tags and prob is None:
            prob = c
        elif "solution" in tags and sol is None:
            sol = c
    return prob, sol


def test_check_warns_non_adjacent_pair(course):
    path = problems._chapter_path("demo", "01-foundations")
    nb = nbformat.read(path, as_version=nbformat.NO_CONVERT)
    prob, _ = _first_pair_cells(nb)
    nb.cells.remove(prob)
    nb.cells.append(prob)
    nbformat.write(nb, path)
    warnings = problems.check_course("demo")
    assert any("must sit in consecutive cells" in w and "01-1" in w for w in warnings)


def test_check_warns_non_code_cell_between_pair(course):
    path = problems._chapter_path("demo", "01-foundations")
    nb = nbformat.read(path, as_version=nbformat.NO_CONVERT)
    prob, sol = _first_pair_cells(nb)
    note = nbformat.v4.new_markdown_cell("An aside between problem and solution.")
    nb.cells.insert(nb.cells.index(sol), note)
    nbformat.write(nb, path)
    warnings = problems.check_course("demo")
    assert any("must sit in consecutive cells" in w and "01-1" in w for w in warnings)


def test_check_allows_starter_between_pair(course):
    path = problems._chapter_path("demo", "01-foundations")
    nb = nbformat.read(path, as_version=nbformat.NO_CONVERT)
    prob, sol = _first_pair_cells(nb)
    starter = nbformat.v4.new_code_cell("A = np.eye(3)")
    nb.cells.insert(nb.cells.index(sol), starter)
    nbformat.write(nb, path)
    assert problems.check_course("demo") == []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def test_cli_problem(course):
    result = runner.invoke(cli.app, ["problem", "demo", "7.3"])
    assert result.exit_code == 0
    assert "### [P7.3] Three routes to the projector" in result.output
    assert "Build the projector onto the column space of A three ways." in result.output


def test_cli_solution(course):
    result = runner.invoke(cli.app, ["solution", "demo", "7.3"])
    assert result.exit_code == 0
    assert "**Solution.**" in result.output
    assert "All three routes agree to machine precision." in result.output


def test_cli_solution_raw(course):
    result = runner.invoke(cli.app, ["solution", "demo", "7.3", "--raw"])
    assert result.exit_code == 0
    assert "#| echo: false" in result.output
    assert "All three routes" not in result.output


def test_cli_hint(course):
    result = runner.invoke(cli.app, ["hint", "demo", "7.3"])
    assert result.exit_code == 0
    assert "Hint:" in result.output
    assert "expected" not in result.output


def test_cli_add_exercise(course):
    result = runner.invoke(
        cli.app,
        ["add-exercise", "demo", "02", "--statement", "### [P2.2] CLI\n\nBody.",
         "--starter", "y = 2", "--solution", "**Solution.** From the CLI."],
    )
    assert result.exit_code == 0
    assert "added 02-2" in result.output
    assert problems.check_course("demo") == []


def test_cli_add_exercise_stdin_solution(course):
    result = runner.invoke(
        cli.app,
        ["add-exercise", "demo", "02", "--statement", "### [P2.2] Piped\n\nBody."],
        input="**Solution.** Piped in.",
    )
    assert result.exit_code == 0
    assert problems.solution_plaintext(problems.resolve_problem("demo", "2.2")) == "**Solution.** Piped in."


def test_cli_solution_edit(course):
    result = runner.invoke(
        cli.app, ["solution-edit", "demo", "7.3", "--content", "**Solution.** Updated."]
    )
    assert result.exit_code == 0
    assert problems.solution_plaintext(problems.resolve_problem("demo", "7.3")) == "**Solution.** Updated."


def test_cli_check_clean(course, cli_console):
    result = runner.invoke(cli.app, ["check", "demo"])
    assert result.exit_code == 0
    assert "3 problems, 3 solutions" in cli_console.getvalue()


def test_cli_check_warns(course, cli_console):
    nb = nbformat.read(
        problems._chapter_path("demo", "01-foundations"),
        as_version=nbformat.NO_CONVERT,
    )
    nb.cells = [c for c in nb.cells if "solution" not in c.metadata.get("tags", [])]
    nbformat.write(nb, problems._chapter_path("demo", "01-foundations"))
    result = runner.invoke(cli.app, ["check", "demo"])
    assert result.exit_code == 1
    assert "has no solution cell" in cli_console.getvalue()


def test_cli_missing_course(tmp_path, monkeypatch, cli_console, invoke):
    monkeypatch.chdir(tmp_path)
    assert invoke("problem", "nope", "7.3") == 1
    assert "no chapter notebooks found" in cli_console.getvalue()


def test_cli_add_exercise_requires_a_flag(course, cli_console, invoke):
    # stdin can feed only one of statement/solution; with neither given the
    # command errors instead of writing an empty solution (the old double
    # stdin read would silently produce one).
    assert invoke("add-exercise", "demo", "02") == 1
    assert "stdin" in cli_console.getvalue()
