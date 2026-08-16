"""Problem statement and solution access for course problems.json files.

Each course keeps its problems in ``courses/<course>/problems.json``. This
module loads that file, resolves a human-friendly locator to one problem,
and renders the problem statement or its solution as markdown for the
``wt problem`` / ``wt solution`` commands. ``sync_problems`` re-extracts
statements and starter code from the chapter notebooks (the source of truth)
back into the JSON.
"""


import json
from pathlib import Path

import nbformat


def load_problems(course: str) -> dict:
    """Load ``courses/<course>/problems.json`` (relative to cwd)."""
    path = Path("courses") / course / "problems.json"
    if not path.exists():
        raise FileNotFoundError(f"no problems file at {path} for course '{course}'")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _normalize(text: str) -> str:
    """Lowercase and strip non-alphanumerics for fuzzy chapter matching."""
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _chapter_number(stem: str) -> int:
    """Leading integer of a chapter stem, e.g. '07-projection...' -> 7."""
    digits = "".join(ch for ch in stem if ch.isdigit())
    return int(digits) if digits else 0


def _problem_number(problem: dict) -> str:
    """Problem number from the id suffix, e.g. '07-3' -> '3'."""
    return problem["id"].rsplit("-", 1)[-1]


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


def _resolve_chapter(problems: dict, chapter_part: str) -> str:
    """Resolve a chapter locator to a chapter stem.

    Numeric parts match the chapter number exactly ('7' -> chapter 07).
    Non-numeric parts match the normalized stem exactly, then as a substring
    ('projection' -> 07-projection-and-orthogonalization). Raises ValueError
    when nothing matches or the match is ambiguous.
    """
    stems = sorted({p["chapter"] for p in problems["problems"]})
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
            f"no chapter matches '{chapter_part}' in course "
            f"'{problems.get('course', '?')}'. valid chapters: {', '.join(stems)}"
        )
    if len(matches) > 1:
        raise ValueError(
            f"ambiguous chapter '{chapter_part}' matches: {', '.join(matches)}"
        )
    return matches[0]


def resolve_problem(problems: dict, locator: str) -> dict:
    """Locate one problem by chapter + problem number.

    Accepted locator forms:
      - 7.3                                    chapter number + '.' + problem number
      - 07-3                                   full problem id
      - 07 3                                   chapter number + space + problem number
      - 07-projection-and-orthogonalization 3  chapter stem + space + problem number
      - projection 3                           fuzzy chapter name + space + problem number
    """
    chapter_part, problem_part = _split_locator(locator)
    stem = _resolve_chapter(problems, chapter_part)
    if not problem_part.isdigit():
        raise ValueError(f"invalid problem number '{problem_part}' in locator '{locator}'")
    target = int(problem_part)
    for p in problems["problems"]:
        if p["chapter"] == stem and int(_problem_number(p)) == target:
            return p
    ids = sorted(p["id"] for p in problems["problems"] if p["chapter"] == stem)
    raise ValueError(
        f"no problem {problem_part} in chapter '{stem}'. valid ids: {', '.join(ids)}"
    )


def _heading_number(problem: dict) -> str:
    """Problem number for the heading: the id's suffix, e.g. '07-3' -> '3'."""
    return _problem_number(problem)


def format_problem(problem: dict) -> str:
    """Render a problem statement as markdown.

    The statement cell source already carries the ``### Problem N —`` heading
    (``### Problem 13-1 —`` in the application chapters), so it is reused
    verbatim when present; otherwise one is synthesized from the id and title.
    """
    statement = problem.get("statement", "")
    lines = statement.splitlines()
    if lines and lines[0].lstrip().startswith("### Problem"):
        heading = lines[0].strip()
        body = "\n".join(lines[1:]).lstrip("\n")
    else:
        heading = f"### Problem {_heading_number(problem)} — {problem['title']}"
        body = statement
    sections = [heading]
    if body:
        sections.append(body)
    starter = problem.get("starter_code")
    if starter:
        sections.append(f"```python\n{starter}\n```")
    return "\n\n".join(sections)


def format_solution(problem: dict) -> str:
    """Render a problem's solution as markdown."""
    sections = [f"### Problem {_heading_number(problem)} — {problem['title']}"]
    solution = problem.get("solution", {})
    sections.append(f"**Solution.** {solution.get('text', '')}")
    answer = solution.get("answer")
    if answer:
        sections.append(f"**Answer:** {answer}")
    checks = solution.get("checks")
    if checks:
        sections.append(
            "\n".join(
                f"- {c['description']}: expected {c['expected']} ± {c['tolerance']}"
                for c in checks
            )
        )
    code = solution.get("code")
    if code:
        sections.append(f"**Reference code.**\n\n```python\n{code}\n```")
    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# sync-problems: re-extract statements/starter code from the notebooks
# ---------------------------------------------------------------------------

def _extract_statements(path: Path) -> list[tuple[str, str | None]]:
    """Return ``(statement_source, starter_code_or_None)`` per problem-tagged
    cell in the notebook, in cell order.

    A code cell immediately following a statement cell is its starter code.
    """
    nb = nbformat.read(path, as_version=nbformat.NO_CONVERT)
    cells = nb.cells
    out: list[tuple[str, str | None]] = []
    for i, cell in enumerate(cells):
        if "problem" not in cell.metadata.get("tags", []):
            continue
        if cell.cell_type != "markdown":
            raise ValueError(
                f"{path}: problem-tagged cell {i} is {cell.cell_type}, not markdown"
            )
        starter = None
        if i + 1 < len(cells) and cells[i + 1].cell_type == "code":
            starter = cells[i + 1].source
        out.append((cell.source, starter))
    return out


def _heading_problem_number(statement: str) -> str | None:
    """Problem number from a ``### Problem N —`` heading, e.g. '13-1' or '1'."""
    lines = statement.splitlines()
    if not lines:
        return None
    first = lines[0].lstrip()
    if not first.startswith("### Problem"):
        return None
    rest = first[len("### Problem"):].strip()
    if not rest:
        return None
    return rest.split()[0]


def _update_problem(prob: dict, statement: str, starter: str | None) -> bool:
    """Overwrite ``statement`` (and ``starter_code`` for implementation /
    challenge problems) in place. Returns True if either field changed.
    """
    changed = prob.get("statement") != statement
    prob["statement"] = statement
    if prob["type"] in ("implementation", "challenge"):
        if prob.get("starter_code") != starter:
            changed = True
        prob["starter_code"] = starter
    return changed


def sync_problems(course: str) -> list[str]:
    """Re-extract problem statements and starter code from the chapter
    notebooks into ``courses/<course>/problems.json``, preserving solutions.

    The notebooks are the source of truth for statements and starter code;
    problems.json is a derived copy. Problems are matched to the tagged
    statement cells by order (1..N per chapter). All other fields (title,
    type, parts, solution, id, chapter) are preserved exactly.

    Returns human-readable warnings for problems whose statement or starter
    changed (the solution may be stale) and for statements or problems that
    have no counterpart on the other side.
    """
    data = load_problems(course)
    problems_by_chapter: dict[str, list[dict]] = {}
    for p in data["problems"]:
        problems_by_chapter.setdefault(p["chapter"], []).append(p)

    course_dir = Path("courses") / course
    chapters = sorted(course_dir.glob("[0-9][0-9]-*.ipynb"))
    if not chapters:
        raise FileNotFoundError(f"no chapter notebooks found under {course_dir}")

    warnings: list[str] = []
    matched: set[tuple[str, int]] = set()

    for path in chapters:
        stem = path.stem
        statements = _extract_statements(path)
        probs = problems_by_chapter.get(stem, [])
        for i, (statement, starter) in enumerate(statements):
            if i < len(probs):
                prob = probs[i]
                matched.add((stem, i))
                if _update_problem(prob, statement, starter):
                    warnings.append(
                        f"{prob['id']} statement/starter changed — verify the "
                        "solution in problems.json is still accurate"
                    )
            else:
                num = _heading_problem_number(statement) or str(i + 1)
                warnings.append(
                    f"{stem}: problem {num} in notebook has no entry in "
                    "problems.json — add it manually"
                )

    for stem, probs in problems_by_chapter.items():
        for i, prob in enumerate(probs):
            if (stem, i) not in matched:
                warnings.append(
                    f"{prob['id']} in problems.json has no matching problem "
                    f"cell in {stem} notebook"
                )

    with open(course_dir / "problems.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    return warnings