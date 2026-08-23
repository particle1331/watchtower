"""Problem statement and solution access for course chapter notebooks.

Each course keeps problems and solutions as tagged cells in its chapter
notebooks — there is no ``problems.json`` anymore.

A problem statement is a markdown cell tagged ``problem`` plus its id tag
(e.g. ``07-3``); the code cell immediately after it is the starter code
(none for theory problems). The matching solution is the code cell tagged
``solution`` plus the same id tag, placed right after the starter (or the
statement when there is no starter). The cell source starts with Quarto
options that hide it from the rendered site (``#| echo: false``,
``#| eval: false``, ``#| output: false``) followed by the ROT18-obfuscated
body with each non-empty line prefixed ``# `` (see ``obfuscate``), so it is
unreadable at a glance in JupyterLab; ``wt solution`` / ``wt hint`` decode on
read, ``wt solution-edit`` encodes on write, and ``wt check`` validates the
pairing and the encoding.

The problem id doubles as the locator: chapter number + '-' + problem
number, e.g. ``07-3`` is problem 3 of chapter 7. ``wt problem cla 7.3`` and
``wt problem cla 07-3`` both resolve to it.
"""


import re
from pathlib import Path

import nbformat

from . import obfuscate
from .notebook import cell_tags, check_source_limit, read_notebook

#: A problem id tag: chapter number + '-' + problem number, e.g. '07-3'.
ID_RE = re.compile(r"^\d{1,3}-\d+$")

#: Markers that identify a *plaintext* solution body (their ROT18 forms
#: appear in encoded cells, so their presence in a decode means the cell
#: was never obfuscated).
PLAINTEXT_MARKERS = ("**Solution.**", "**Answer:**", "**Checks:**", "**Reference code.**")


def problem_counts(course: str) -> tuple[int, int]:
    """Return (problem cells, solution cells) across a course's chapters."""
    n_problems = n_solutions = 0
    for path in chapter_notebooks(course):
        for cell in read_notebook(path)["cells"]:
            tags = cell_tags(cell)
            if "problem" in tags:
                n_problems += 1
            if "solution" in tags:
                n_solutions += 1
    return n_problems, n_solutions


def chapter_notebooks(course: str) -> list[Path]:
    """Sorted chapter notebooks ``courses/<course>/NN-*.ipynb``."""
    course_dir = Path("courses") / course
    chapters = sorted(course_dir.glob("[0-9][0-9]-*.ipynb"))
    if not chapters:
        raise FileNotFoundError(
            f"no chapter notebooks found under {course_dir} (course '{course}')"
        )
    return chapters


def _normalize(text: str) -> str:
    """Lowercase and strip non-alphanumerics for fuzzy chapter matching."""
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _chapter_number(stem: str) -> int:
    """Leading integer of a chapter stem, e.g. '07-projection...' -> 7."""
    digits = "".join(ch for ch in stem if ch.isdigit())
    return int(digits) if digits else 0


def _split_locator(locator: str) -> tuple[str, str]:
    """Split a locator into (chapter_part, problem_part)."""
    if " " in locator:
        parts = locator.split()
        if len(parts) != 2:
            raise ValueError(f"invalid locator '{locator}': expected '<chapter> <problem>'")
        return parts[0], parts[1]
    if "." in locator:
        parts = locator.split(".")
        if len(parts) != 2:
            raise ValueError(f"invalid locator '{locator}': expected '<chapter>.<problem>'")
        return parts[0], parts[1]
    if "-" in locator:
        parts = locator.split("-", 1)
        if len(parts) != 2:
            raise ValueError(f"invalid locator '{locator}': expected '<chapter>-<problem>'")
        return parts[0], parts[1]
    raise ValueError(
        f"invalid locator '{locator}': use e.g. '7.3', '07-3', '07 3', "
        "'07-projection-and-orthogonalization 3', or 'projection 3'"
    )


def _resolve_chapter(course: str, chapter_part: str) -> str:
    """Resolve a chapter locator to a chapter stem.

    Numeric parts match the chapter number exactly ('7' -> chapter 07).
    Non-numeric parts match the normalized stem exactly, then as a substring
    ('projection' -> 07-projection-and-orthogonalization). Raises ValueError
    when nothing matches or the match is ambiguous.
    """
    stems = [p.stem for p in chapter_notebooks(course)]
    norm = _normalize(chapter_part)
    if not norm:
        raise ValueError(f"empty chapter in locator '{chapter_part}'")
    if norm.isdigit():
        target = int(norm)
        matches = [s for s in stems if _chapter_number(s) == target]
    else:
        matches = [s for s in stems if _normalize(s) == norm]
        if not matches:
            matches = [s for s in stems if norm in _normalize(s)]
    if not matches:
        raise ValueError(
            f"no chapter matches '{chapter_part}' in course '{course}'. "
            f"valid chapters: {', '.join(stems)}"
        )
    if len(matches) > 1:
        raise ValueError(
            f"ambiguous chapter '{chapter_part}' matches: {', '.join(matches)}"
        )
    return matches[0]


def _chapter_path(course: str, stem: str) -> Path:
    return Path("courses") / course / f"{stem}.ipynb"


def _id_tags(cell: nbformat.NotebookNode) -> list[str]:
    """Problem/solution id tags on a cell (the tags matching NN-K)."""
    return [t for t in cell_tags(cell) if ID_RE.match(t)]


def _tagged_indices(
    nb: nbformat.NotebookNode, *, required: set[str]
) -> list[int]:
    """Cell indices whose tags include every tag in ``required``."""
    return [i for i, c in enumerate(nb["cells"]) if required <= set(cell_tags(c))]


def _unique_or_none(nb: nbformat.NotebookNode, required: set[str], what: str) -> int | None:
    """The single cell index tagged with ``required``, or None if absent.
    Errors when more than one cell matches.
    """
    idxs = _tagged_indices(nb, required=required)
    if not idxs:
        return None
    if len(idxs) > 1:
        raise ValueError(
            f"ambiguous: {len(idxs)} cells tagged {sorted(required)} "
            f"(indices {', '.join(str(i) for i in idxs)})."
        )
    return idxs[0]


def _list_ids(nb: nbformat.NotebookNode) -> list[str]:
    """Problem ids in the notebook, in cell order, for error messages."""
    return [
        _id_tags(c)[0]
        for c in nb["cells"]
        if "problem" in cell_tags(c) and _id_tags(c)
    ]


def _heading_title(statement: str) -> str | None:
    """Title from a problem heading, else None.

    Recognizes the canonical ``### [PNN.N] Title`` format plus the legacy
    ``### (PNN.N) Title``, ``### Prob. NN.N. Title`` and
    ``### Problem N — Title`` / ``### Problem NN-N — Title`` formats.
    """
    lines = statement.splitlines()
    if not lines:
        return None
    first = lines[0].lstrip()
    if first.startswith("### [P"):
        rest = first[len("### [P"):].strip()
        if "]" in rest:
            return rest.split("]", 1)[1].strip()
        return None
    if first.startswith("### (P"):
        rest = first[len("### (P"):].strip()
        if ")" in rest:
            return rest.split(")", 1)[1].strip()
        return None
    if first.startswith("### Prob."):
        rest = first[len("### Prob."):].strip()
        parts = rest.split(".", 2)
        if len(parts) == 3:
            return parts[2].strip()
        return None
    if first.startswith("### Problem"):
        rest = first[len("### Problem"):].strip()
        parts = rest.split("—", 1)
        if len(parts) == 2:
            return parts[1].strip()
        return None
    return None


def resolve_problem(course: str, locator: str) -> dict:
    """Locate one problem in the course's chapter notebooks.

    Accepted locator forms:
      - 7.3                                    chapter number + '.' + problem number
      - 07-3                                   full problem id
      - 07 3                                   chapter number + space + problem number
      - 07-projection-and-orthogonalization 3  chapter stem + space + problem number
      - projection 3                           fuzzy chapter name + space + problem number

    Returns a dict with the statement, starter code, and (when present) the
    stored solution cell source and its index.
    """
    chapter_part, problem_part = _split_locator(locator)
    stem = _resolve_chapter(course, chapter_part)
    if not problem_part.isdigit():
        raise ValueError(
            f"invalid problem number '{problem_part}' in locator '{locator}'"
        )
    path = _chapter_path(course, stem)
    nb = read_notebook(path)
    pid = f"{_chapter_number(stem):02d}-{int(problem_part)}"
    pidx = _unique_or_none(nb, {"problem", pid}, "problem")
    if pidx is None:
        ids = _list_ids(nb)
        raise ValueError(
            f"no problem {pid} in chapter '{stem}'. valid ids: {', '.join(ids) or 'none'}"
        )
    cell = nb["cells"][pidx]
    statement = cell.get("source", "")
    starter_idx = pidx + 1
    starter = None
    if starter_idx < len(nb["cells"]):
        candidate = nb["cells"][starter_idx]
        if candidate["cell_type"] == "code" and "solution" not in cell_tags(candidate):
            starter = candidate.get("source", "")
    sidx = _unique_or_none(nb, {"solution", pid}, "solution")
    return {
        "course": course,
        "chapter": stem,
        "path": path,
        "id": pid,
        "number": int(problem_part),
        "title": _heading_title(statement),
        "statement": statement,
        "starter_code": starter,
        "solution_index": sidx,
        "solution_source": nb["cells"][sidx].get("source", "") if sidx is not None else None,
    }


def format_problem(problem: dict) -> str:
    """Render a problem statement as markdown.

    The statement cell source already carries the canonical ``### [PNN.N]
    Title`` heading (or the legacy ``### (PNN.N) Title`` / ``### Prob. NN.N.
    Title`` / ``### Problem N — Title`` / ``### Problem NN-N — Title``
    headings), so it is reused verbatim when present; otherwise one is
    synthesized from the chapter, number, and the heading's title.
    """
    statement = problem["statement"]
    lines = statement.splitlines()
    if lines and lines[0].lstrip().startswith(("### Problem", "### Prob.", "### (P", "### [P")):
        heading = lines[0].strip()
        body = "\n".join(lines[1:]).lstrip("\n")
    else:
        chapter = int(problem["id"].rsplit("-", 1)[0])
        heading = f"### [P{chapter}.{problem['number']}]"
        title = problem.get("title")
        if title:
            heading += f" {title}"
        body = statement
    sections = [heading]
    if body:
        sections.append(body)
    starter = problem.get("starter_code")
    if starter:
        sections.append(f"```python\n{starter}\n```")
    return "\n\n".join(sections)


def format_solution_body(solution: dict) -> str:
    """Plaintext markdown for a solution dict, without a heading.

    This is the canonical solution body: the agent writes it via
    ``wt solution-edit`` (which encodes it) and it is what a decode yields.
    Mirrors the section markers used by ``wt hint`` and ``wt check``.
    """
    sections: list[str] = []
    text = solution.get("text")
    if text:
        sections.append(f"**Solution.** {text}")
    answer = solution.get("answer")
    if answer:
        sections.append(f"**Answer:** {answer}")
    checks = solution.get("checks")
    if checks:
        sections.append(
            "**Checks:**\n"
            + "\n".join(
                f"- {c['description']}: expected {c['expected']} ± {c['tolerance']}"
                for c in checks
            )
        )
    code = solution.get("code")
    if code:
        sections.append(f"**Reference code.**\n\n```python\n{code}\n```")
    return "\n\n".join(sections)


def decode_solution_source(source: str) -> str:
    """Decode a stored solution cell source (wrapper stripped) to plaintext."""
    return obfuscate.deobfuscate(obfuscate.unwrap(source))


def solution_plaintext(problem: dict) -> str:
    """Decoded plaintext solution body for a resolved problem."""
    if problem["solution_source"] is None:
        raise ValueError(
            f"no solution cell for {problem['id']} — create one with "
            f"`wt solution-edit {problem['course']} {problem['id']}`"
        )
    return decode_solution_source(problem["solution_source"])


# ---------------------------------------------------------------------------
# hint: progressive reveals from the decoded solution
# ---------------------------------------------------------------------------

def _split_sections(body: str) -> dict[str, str]:
    """Split a decoded solution body into text/answer/checks/code sections.

    Checks keeps only the description of each check line (the expected
    values are stripped, so a hint never leaks them).
    """
    markers = [
        ("text", "**Solution.**"),
        ("answer", "**Answer:**"),
        ("checks", "**Checks:**"),
        ("code", "**Reference code.**"),
    ]
    sections: dict[str, str] = {}
    for name, marker in markers:
        start = body.find(marker)
        if start == -1:
            continue
        rest = body[start + len(marker):]
        # section ends at the next marker
        end = len(rest)
        for _, next_marker in markers:
            if next_marker == marker:
                continue
            pos = rest.find(next_marker)
            if pos != -1:
                end = min(end, pos)
        sections[name] = rest[:end].strip("\n")
    if "checks" in sections:
        descs = []
        for line in sections["checks"].splitlines():
            line = line.strip().lstrip("- ").strip()
            if line:
                descs.append(line.split(": expected", 1)[0].strip())
        sections["checks"] = "\n".join(descs)
    return sections


def _first_sentence(text: str) -> str:
    """First sentence of a paragraph, floored at ~40 chars so the hint is
    actually informative."""
    flat = " ".join(text.split())
    sentence = flat.split(". ", 1)[0].strip(".")
    if len(sentence) < 40:
        return flat[:160] + ("…" if len(flat) > 160 else "")
    return sentence + "."


def hint_text(problem: dict, level: int = 1) -> str:
    """A progressive hint derived from the decoded solution.

    Level 1: the checks to satisfy (descriptions only, no expected values)
    plus the first sentence of the worked solution. Level 2: the full worked
    solution text (no answer, checks, or code). Never reveals the answer.
    """
    if level not in (1, 2):
        raise ValueError(f"hint level must be 1 or 2, got {level}")
    body = solution_plaintext(problem)
    sections = _split_sections(body)
    parts: list[str] = []
    if level == 1:
        checks = sections.get("checks")
        if checks:
            parts.append("Checks to satisfy:\n" + "\n".join(f"- {ln}" for ln in checks.splitlines()))
        text = sections.get("text")
        if text:
            parts.append(f"Hint: {_first_sentence(text)}")
        if not parts:
            return "(no hint available)"
    else:
        text = sections.get("text")
        if not text:
            return "(no worked solution text)"
        parts.append(text)
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# writes
# ---------------------------------------------------------------------------

def _next_problem_number(path: Path) -> int:
    """Next problem number in a chapter: max existing id number + 1."""
    nb = read_notebook(path)
    numbers = [
        int(_id_tags(c)[0].rsplit("-", 1)[1])
        for c in nb["cells"]
        if "problem" in cell_tags(c) and _id_tags(c)
    ]
    return max(numbers, default=0) + 1


def add_exercise(
    course: str,
    chapter_part: str,
    statement: str,
    solution: str,
    starter: str | None = None,
    number: int | None = None,
) -> tuple[str, Path]:
    """Append a new problem + solution pair to a chapter notebook.

    ``chapter_part`` is a chapter locator ('7', '07', 'projection'). The
    problem number defaults to the next one after the chapter's existing
    problems; the id tag (e.g. '07-6') is derived from it.

    The statement is stored plaintext (tagged ``problem`` + id); the
    solution is ROT18-encoded into a code cell tagged ``solution`` + id,
    with a ``#| echo: false / eval: false / output: false`` header that
    hides it from the rendered site, so plaintext solutions can never reach
    the notebook through this path. An optional starter code cell is inserted
    between them. Returns (id, path).
    """
    stem = _resolve_chapter(course, chapter_part)
    path = _chapter_path(course, stem)
    num = _chapter_number(stem)
    problem_number = number if number is not None else _next_problem_number(path)
    if problem_number < 1:
        raise ValueError(f"problem number must be >= 1, got {problem_number}")
    pid = f"{num:02d}-{problem_number}"
    check_source_limit(statement)
    check_source_limit(solution)
    if starter:
        check_source_limit(starter)

    lines = statement.splitlines()
    if not lines or not lines[0].lstrip().startswith(("### Problem", "### Prob.", "### (P", "### [P")):
        statement = f"### [P{num}.{problem_number}]\n\n{statement.lstrip()}"

    nb = read_notebook(path)
    if _unique_or_none(nb, {"problem", pid}, "problem") is not None:
        raise ValueError(
            f"problem {pid} already exists in chapter '{stem}' — "
            f"use `wt solution-edit` to edit its solution instead"
        )
    stmt_cell = nbformat.v4.new_markdown_cell(statement)
    stmt_cell.metadata["tags"] = ["problem", pid]
    nb["cells"].append(stmt_cell)
    if starter:
        nb["cells"].append(nbformat.v4.new_code_cell(starter))
    sol_cell = nbformat.v4.new_code_cell(obfuscate.wrap(solution))
    sol_cell.metadata["tags"] = ["solution", pid]
    nb["cells"].append(sol_cell)
    nbformat.write(nb, path)
    return pid, path


def set_solution(course: str, locator: str, content: str) -> Path:
    """Create or replace the solution cell for a problem.

    ``content`` is the *plaintext* markdown body (no wrapper, no encoding);
    it is ROT18-obfuscated into a code cell tagged ``solution`` + the problem
    id, with a ``#| echo: false / eval: false / output: false`` header that
    hides it from the rendered site, so plaintext never reaches the notebook.
    If the problem has a starter code cell, the solution is inserted right
    after it; otherwise right after the statement.
    """
    chapter_part, problem_part = _split_locator(locator)
    stem = _resolve_chapter(course, chapter_part)
    if not problem_part.isdigit():
        raise ValueError(
            f"invalid problem number '{problem_part}' in locator '{locator}'"
        )
    path = _chapter_path(course, stem)
    nb = read_notebook(path)
    pid = f"{_chapter_number(stem):02d}-{int(problem_part)}"
    pidx = _unique_or_none(nb, {"problem", pid}, "problem")
    if pidx is None:
        ids = _list_ids(nb)
        raise ValueError(
            f"no problem {pid} in chapter '{stem}'. valid ids: {', '.join(ids) or 'none'}"
        )
    check_source_limit(content)
    encoded = obfuscate.wrap(content)
    sidx = _unique_or_none(nb, {"solution", pid}, "solution")
    if sidx is None:
        # Insert after the starter code cell, or after the statement when
        # there is none (same heuristic as resolve_problem).
        position = pidx + 1
        if position < len(nb["cells"]) and nb["cells"][position]["cell_type"] == "code":
            position += 1
        cell = nbformat.v4.new_code_cell(encoded)
        cell.metadata["tags"] = ["solution", pid]
        nb["cells"].insert(position, cell)
    else:
        nb["cells"][sidx]["source"] = encoded
        tags = nb["cells"][sidx].setdefault("metadata", {}).setdefault("tags", [])
        for t in ("solution", pid):
            if t not in tags:
                tags.append(t)
    nbformat.write(nb, path)
    return path


# ---------------------------------------------------------------------------
# wt check: validate tagging, pairing, and encoding
# ---------------------------------------------------------------------------

def check_course(course: str) -> list[str]:
    """Validate a course's problem/solution cells. Returns warnings.

    Checks per chapter: problem cells are markdown and solution cells are
    code, both carry an id tag matching ``<chapter>-<n>``, ids are unique,
    every problem has a solution pair (and vice versa), solution cells start
    with the ``#| echo: false / eval: false / output: false`` header, and
    the body decodes to something that was actually obfuscated (no plaintext
    commits).
    """
    warnings: list[str] = []
    for path in chapter_notebooks(course):
        stem = path.stem
        num = _chapter_number(stem)
        nb = read_notebook(path)
        problems: dict[str, int] = {}
        solutions: dict[str, int] = {}
        for i, cell in enumerate(nb["cells"]):
            tags = cell_tags(cell)
            role = "problem" if "problem" in tags else ("solution" if "solution" in tags else None)
            if role is None:
                continue
            expected = "markdown" if role == "problem" else "code"
            if cell["cell_type"] != expected:
                warnings.append(
                    f"{stem}: {role} cell {i} is {cell['cell_type']}, not {expected}"
                )
                continue
            ids = _id_tags(cell)
            if not ids:
                warnings.append(
                    f"{stem}: {role} cell {i} has no id tag (expected '<chapter>-<n>', e.g. '{num:02d}-1')"
                )
                continue
            if len(ids) > 1:
                warnings.append(f"{stem}: {role} cell {i} has multiple id tags: {', '.join(ids)}")
                continue
            pid = ids[0]
            if pid.rsplit("-", 1)[0] != f"{num:02d}":
                warnings.append(
                    f"{stem}: {pid} id tag does not match chapter number {num:02d}"
                )
            bucket = problems if role == "problem" else solutions
            if pid in bucket:
                warnings.append(f"{stem}: duplicate {role} id {pid} (cells {bucket[pid]} and {i})")
            else:
                bucket[pid] = i
        for pid in sorted(set(problems) - set(solutions)):
            warnings.append(f"{stem}: problem {pid} has no solution cell (tag it `solution` + {pid})")
        for pid in sorted(set(solutions) - set(problems)):
            warnings.append(f"{stem}: solution {pid} has no problem cell (orphan)")
        for pid, i in solutions.items():
            source = nb["cells"][i].get("source", "")
            if not obfuscate.is_wrapped(source):
                warnings.append(
                    f"{stem}: solution {pid} is not wrapped in the "
                    "`#| echo: false / eval: false / output: false` header"
                )
            if not obfuscate.unwrap(source).strip():
                warnings.append(f"{stem}: solution {pid} has an empty body")
            if any(marker in source for marker in PLAINTEXT_MARKERS):
                warnings.append(
                    f"{stem}: solution {pid} appears to be stored in plaintext "
                    "(found the solution markers unencoded — re-encode with "
                    "`wt solution-edit`)"
                )
    return warnings
