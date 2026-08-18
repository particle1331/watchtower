"""Watchtower CLI — Typer application assembling all subcommands.

Submodules are imported inside each command body, not at module level:
nbformat (pulled in by notebook/problems/convert/...) costs ~1.1s of
jsonschema import on startup, and most commands never touch a notebook.
Function-level imports keep commands like `wt vault list` / `wt map` at
~0.1s instead of ~1.5s.
"""


import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="wt",
    help="Personal notes, articles, courses, and projects system.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
console = Console()


new_app = typer.Typer(name="new", help="Scaffold new artifacts.", no_args_is_help=True)
app.add_typer(new_app)


@new_app.command("note")
def new_note(
    name: str,
    title: str | None = typer.Option(
        None,
        "--title",
        "-t",
        help="display title (default: derived from name)",
    ),
) -> None:
    """Create notes/<name>.ipynb with a minimal frontmatter stub."""
    from . import scaffold

    path = scaffold.new_note(name, title=title)
    console.print(f"[green]created {path}[/green]")


@new_app.command("article")
def new_article(
    name: str,
    title: str | None = typer.Option(
        None,
        "--title",
        "-t",
        help="display title (default: derived from name)",
    ),
) -> None:
    """Create articles/<name>.ipynb with a date and title frontmatter."""
    from . import scaffold

    path = scaffold.new_article(name, title=title)
    console.print(f"[green]created {path}[/green]")


@new_app.command("course")
def new_course(
    name: str = typer.Argument(..., help="course folder name (e.g. llm)"),
    title: str = typer.Argument(..., help='display title (e.g. "Large Language Models")'),
) -> None:
    """Create courses/<name>/ with an index notebook and a first lesson stub."""
    from . import scaffold

    path = scaffold.new_course(name, title=title)
    console.print(f"[green]created {path}[/green]")


@new_app.command("project")
def new_project(name: str) -> None:
    """uv init projects/<name> and wire it into the workspace."""
    from . import scaffold

    path = scaffold.new_project(name)
    console.print(f"[green]created {path}[/green]")


@new_app.command("chapter")
def new_chapter(
    course: str = typer.Argument(..., help="course folder name (e.g. mlops)"),
    name: str = typer.Argument(..., help="chapter stem (e.g. 02-data-validation)"),
    title: str | None = typer.Option(
        None, 
        "--title",
        "-t",
        help="display title (default: derived from name)"
    ),
    section: str | None = typer.Option(
        None,
        "--section",
        "-s",
        help="section name to place this chapter under (default: last section)",
    ),
) -> None:
    """Scaffold courses/<course>/<name>.ipynb and register it in the course sidebar."""
    from . import scaffold

    path = scaffold.new_course_chapter(course, name, title=title, section=section)
    console.print(f"[green]created {path}[/green]")


@new_app.command("section")
def new_section(
    course: str = typer.Argument(..., help="course folder name (e.g. mlops)"),
    name: str = typer.Argument(..., help="section name (e.g. 'Local Stack')"),
) -> None:
    """Add a section header to a course's sidebar in _quarto.yml."""
    from . import scaffold

    scaffold.new_course_section(course, name)
    console.print(f"[green]added section '{name}' to {course}[/green]")


vault_app = typer.Typer(name="vault", help="Manage secrets in OS keyring.", no_args_is_help=True)
app.add_typer(vault_app)


@vault_app.command("set")
def vault_set(key: str, value: str) -> None:
    """Store a secret in the OS keyring."""
    from . import vault

    vault.set_secret(key, value)
    console.print(f"[green]stored {key}.[/green]")


@vault_app.command("get")
def vault_get(key: str) -> None:
    """Retrieve a secret value."""
    from . import vault

    val = vault.get_secret(key)
    if val is None:
        console.print(f"[red]{key} not set.[/red]")
        raise typer.Exit(1)
    console.print(val)


@vault_app.command("delete")
def vault_delete(key: str) -> None:
    """Delete a secret from the OS keyring."""
    from . import vault

    if not vault.delete_secret(key):
        console.print(f"[red]{key} not set.[/red]")
        raise typer.Exit(1)
    console.print(f"[green]deleted {key}.[/green]")


@vault_app.command("list")
def vault_list() -> None:
    """List stored secret keys (no values)."""
    from . import vault

    keys = vault.list_keys()
    if not keys:
        console.print("[yellow]no secrets stored.[/yellow]")
        return
    t = Table("key")
    for k in keys:
        t.add_row(k)
    console.print(t)


@vault_app.command("export")
def vault_export() -> None:
    """Emit export lines for all stored secrets. Usage: eval $(wt vault export)."""
    from . import vault

    for k, v in vault.all_secrets().items():
        print(f"export {k}={shlex.quote(v)}")


@app.command(name="map")
def map_cmd() -> None:
    """Print repo structure as JSON — agent navigation context."""
    from . import inspect

    print(inspect.repo_map_json())


@app.command()
def find(query: str) -> None:
    """Grep across notebook cell sources, reporting cell indices."""
    from . import inspect

    out = inspect.find_in_src(query)
    if out:
        print(out)
    else:
        console.print(f"[yellow]no sources match '{query}'.[/yellow]")


@app.command()
def count(name: str) -> None:
    """Print the number of cells in a notebook."""
    from . import notebook

    n = notebook.count_cells(name)
    print(f"{n} cells")


@app.command()
def problem(course: str, locator: str) -> None:
    """Print a problem statement (plus starter code) from the course notebooks.

    Problems live in the chapter notebooks as `problem`-tagged cells with an
    id tag like '07-3'. Locator forms: '7.3', '07-3', '07 3',
    '07-projection-and-orthogonalization 3', or a fuzzy chapter name like
    'projection 3'.
    """
    from . import problems

    print(problems.format_problem(problems.resolve_problem(course, locator)))


@app.command()
def solution(
    course: str,
    locator: str,
    raw: bool = typer.Option(
        False,
        "--raw",
        help="print the stored encoded cell source instead of the decoded solution",
    ),
) -> None:
    """Print a problem's decoded solution from the course notebooks.

    Solutions are code cells tagged `solution` + the problem id, hidden from
    the rendered site by `#| echo: false / eval: false / output: false`
    options and ROT18-obfuscated; this command decodes them (--raw prints
    the stored source as-is).
    """
    from . import problems

    prob = problems.resolve_problem(course, locator)
    if raw:
        if prob["solution_source"] is None:
            console.print(
                f"[red]no solution cell for {prob['id']} — create one with "
                f"`wt solution-set {course} {locator}`[/red]"
            )
            raise typer.Exit(1)
        print(prob["solution_source"], end="")
        return
    body = problems.solution_plaintext(prob)
    title = prob["title"]
    chapter = int(prob["id"].rsplit("-", 1)[0])
    heading = f"### [P{chapter}.{prob['number']}]"
    if title:
        heading += f" {title}"
    print(f"{heading}\n\n{body}")


@app.command()
def hint(
    course: str,
    locator: str,
    level: int = typer.Option(1, "--level", help="hint level: 1 = checks + first sentence, 2 = full worked text"),
) -> None:
    """Print a progressive hint for a problem, derived from its solution.

    Level 1 shows the checks to satisfy (descriptions only, no expected
    values) and the first sentence of the worked solution; level 2 shows
    the full worked solution text. Never reveals the answer.
    """
    from . import problems

    prob = problems.resolve_problem(course, locator)
    print(problems.hint_text(prob, level=level))


@app.command(name="add-exercise")
def add_exercise(
    course: str,
    locator: str,
    statement: str | None = typer.Option(None, "--statement", "-s", help="plaintext problem statement (markdown; a `### [PNN.N]` heading is added if missing)"),
    starter: str | None = typer.Option(None, "--starter", help="optional starter code cell"),
    solution: str | None = typer.Option(None, "--solution", help="plaintext solution body (encoded on write)"),
    number: int | None = typer.Option(None, "--number", "-n", help="problem number (default: next after the chapter's last problem)"),
) -> None:
    """Append a problem + solution pair to a chapter notebook (encodes on write).

    The statement goes in plaintext (tagged `problem` + id); the solution is
    ROT18-obfuscated into a code cell tagged `solution` + id, with a
    `#| echo: false / eval: false / output: false` header that hides it from
    the rendered site, so plaintext solutions never reach the notebook
    through this path. The problem number defaults to the next one in the
    chapter; `--starter` adds a code cell between statement and solution.
    If exactly one of --statement / --solution is omitted, it is read from
    stdin.
    """
    from . import problems

    if statement is None and solution is None:
        raise ValueError(
            "pass --statement or --solution; stdin can feed only one of them."
        )
    src_stmt = sys.stdin.read() if statement is None else statement
    src_sol = solution if solution is not None else sys.stdin.read()
    pid, out = problems.add_exercise(
        course, locator, src_stmt, src_sol,
        starter=starter, number=number,
    )
    console.print(f"[green]added {pid} to {out}[/green]")


@app.command(name="solution-set")
def solution_set(
    course: str,
    locator: str,
    content: str | None = typer.Option(None, "--content", "-c", help="plaintext markdown solution body (if omitted, read from stdin)"),
) -> None:
    """Create or replace a problem's solution cell (encodes on write).

    Takes the *plaintext* solution body (Solution./Answer:/Checks:/Reference
    code. sections) and stores it ROT18-obfuscated in a code cell tagged
    `solution` + the problem id, with a `#| echo: false / eval: false /
    output: false` header that hides it from the rendered site. Agents
    writing a chapter use this command so plaintext solutions never reach
    the notebook.
    """
    from . import problems

    src = content if content is not None else sys.stdin.read()
    out = problems.set_solution(course, locator, src)
    console.print(f"[green]set solution in {out}[/green]")


@app.command()
def check(course: str) -> None:
    """Validate a course's problem/solution tagging, pairing, and encoding.

    Warns on: problem cells that are not markdown, solution cells that are
    not code, missing or duplicated id tags, solutions without a problem
    pair (and vice versa), solution cells not wrapped in the `#| echo:
    false / eval: false / output: false` header, empty solution bodies,
    and solutions stored in plaintext instead of ROT18-obfuscated. Exits 1
    when anything is wrong.
    """
    from . import problems

    warnings = problems.check_course(course)
    if warnings:
        for w in warnings:
            console.print(f"[yellow]{w}[/yellow]")
        raise typer.Exit(1)
    n_problems, n_solutions = problems.problem_counts(course)
    console.print(
        f"[green]checked {course}: {n_problems} problems, "
        f"{n_solutions} solutions — all tagged and encoded.[/green]"
    )


@app.command()
def cat(
    name: str,
    index: str | None = typer.Option(None, "--index", "-i", help="0-based cell index, or N:M range (Python-style slice; :M and N: also ok)"),
    tag: str | None = typer.Option(None, "--tag", "-t", help="show cells with this tag"),
    label: str | None = typer.Option(None, "--label", "-l", help="show cells with this #| label: pragma"),
    offset: int = typer.Option(0, "--offset", "-o", help="char offset into the cell source (use with --limit)"),
    limit: int | None = typer.Option(None, "--limit", help="max chars per cell source (default: 4096; 0 = unlimited)"),
    with_outputs: bool = typer.Option(False, "--with-outputs", help="also show each code cell's outputs"),
    out_offset: int = typer.Option(0, "--out-offset", help="char offset into each output's text body"),
    out_limit: int | None = typer.Option(None, "--out-limit", help="max chars per output body"),
    context: int = typer.Option(0, "--context", "-C", help="include N cells before the first match and after the last (marked `context` in headers)"),
    decode: bool = typer.Option(False, "--decode", help="decode solution-tagged cells to plaintext (spoiler opt-in)"),
) -> None:
    """Print notebook cell sources as markdown (JSON-stripped)."""
    from . import notebook

    # Default read limit protects agent context windows; 0 = no limit.
    effective_limit: int | None = None
    if limit == 0:
        effective_limit = None
    elif limit is not None:
        effective_limit = limit
    else:
        effective_limit = notebook.DEFAULT_READ_LIMIT
    print(
        notebook.cat_notebook(
            name, index=index, tag=tag, label=label,
            offset=offset, limit=effective_limit,
            with_outputs=with_outputs,
            out_offset=out_offset, out_limit=out_limit,
            context=context, decode_solutions=decode,
        ),
        end="",
    )


@app.command(name="diff")
def diff_cmd(
    name: str,
    base: str = typer.Option("HEAD", "--base", "-b", help="git ref to diff against (default: HEAD)"),
) -> None:
    """Show a notebook's changes as a markdown diff vs a git ref.

    Both sides are rendered like `wt cat` (JSON-stripped, no outputs;
    solution cells decoded), so the diff shows content changes instead of
    `.ipynb` JSON noise. Prints nothing extra when unchanged.
    """
    from . import notebook

    out = notebook.diff_notebook(name, base=base)
    if out is None:
        console.print("[green]no changes[/green]")
    else:
        print(out)


@app.command()
def ls(tier: str = typer.Argument(..., help="notes | articles | courses | projects")) -> None:
    """List source `.ipynb` notebooks in a tier."""
    from . import inspect

    if tier == "notes":
        items = inspect.list_ipynb(Path("notes"))
    elif tier == "articles":
        items = inspect.list_ipynb(Path("articles"))
    elif tier == "courses":
        items = inspect.list_ipynb(Path("courses"))
    elif tier == "projects":
        items = [p["name"] for p in inspect.list_projects()]
    else:
        console.print(f"[red]unknown tier: {tier}. try notes|articles|courses|projects.[/red]")
        raise typer.Exit(2)
    if not items:
        console.print(f"[yellow]no {tier} yet.[/yellow]")
        return
    for i in items:
        print(i)


@app.command(name="import")
def import_cmd(
    ipynb: str = typer.Argument(..., help="path to source .ipynb to import"),
    tier: str = typer.Argument(..., help="notes | articles | courses"),
    name: str | None = typer.Argument(
        None,
        help=(
            "for notes|articles: destination name without .ipynb "
            "(default: source name); for courses: course slug (required)"
        ),
    ),
    chapter: str | None = typer.Argument(
        None,
        help=(
            "for courses: chapter name without .ipynb "
            "(default: source name); ignored for flat tiers"
        ),
    ),
    section: str | None = typer.Option(
        None,
        "--section",
        "-s",
        help="section to place chapter under (default: last section, courses only)",
    ),
) -> None:
    """Import an external notebook into a content tier (preserves outputs).

    For notes/articles: writes to <tier>/<name>.ipynb.
    For courses: writes to courses/<course>/<chapter>.ipynb and registers
    in the course's sidebar in _quarto.yml.
    """
    from . import convert

    if tier == "courses":
        if name is None:
            raise ValueError(
                "tier=courses requires a course slug positional "
                "(e.g. `wt import x.ipynb courses llm`)"
            )
        out = convert.import_chapter(
            ipynb, name, chapter=chapter, section=section
        )
    else:
        if section is not None:
            raise ValueError(
                f"--section is only valid when tier=courses, got tier={tier}"
            )
        if chapter is not None:
            raise ValueError(
                f"chapter positional is only valid when tier=courses, got tier={tier}"
            )
        out = convert.import_notebook(ipynb, tier, name)
    console.print(f"[green]imported -> {out}[/green]")


@app.command()
def edit_cell(
    name: str,
    index: int | None = typer.Option(None, "--index", "-i", help="0-based cell index"),
    tag: str | None = typer.Option(None, "--tag", "-t", help="cell tag to match (must be unique)"),
    label: str | None = typer.Option(None, "--label", "-l", help="Quarto `#| label:` to match (must be unique)"),
    content: str | None = typer.Option(None, "--content", "-c", help="new source string (if omitted, read from stdin)"),
) -> None:
    """Replace a notebook cell's source. Preserves outputs/metadata.

    Exactly one of --index / --tag / --label is required. Source comes from
    --content (for one-liners) or stdin (for multi-line). Errors if the
    locator matches zero or multiple cells.
    """
    from . import notebook

    src = content if content is not None else sys.stdin.read()
    out = notebook.edit_cell(name, src, index=index, tag=tag, label=label)
    console.print(f"[green]updated {out}[/green]")


@app.command()
def append_cell(
    name: str,
    cell_type: str = typer.Option("md", "--type", "-t", help="md | code"),
    content: str | None = typer.Option(None, "--content", "-c", help="cell source (if omitted, read from stdin)"),
) -> None:
    """Append a new cell to the end of the notebook."""
    from . import notebook

    src = content if content is not None else sys.stdin.read()
    out = notebook.append_cell(name, src, cell_type=cell_type)
    console.print(f"[green]appended to {out}[/green]")


@app.command()
def insert_cell(
    name: str,
    cell_type: str = typer.Option("md", "--type", "-t", help="md | code"),
    after: int | None = typer.Option(None, "--after", "-a", help="insert below this 0-based index"),
    before: int | None = typer.Option(None, "--before", "-b", help="insert above this 0-based index"),
    tag: str | None = typer.Option(None, "--tag", help="insert below the cell with this tag (must be unique)"),
    label: str | None = typer.Option(None, "--label", help="insert below the cell with this Quarto label (must be unique)"),
    content: str | None = typer.Option(None, "--content", "-c", help="cell source (if omitted, read from stdin)"),
) -> None:
    """Insert a new cell above/below a located cell.

    Pass exactly one of --after / --before / --tag / --label. --tag and
    --label insert *below* the matched cell. Source from --content or stdin.
    """
    from . import notebook

    src = content if content is not None else sys.stdin.read()
    out = notebook.insert_cell(
        name, src, after=after, before=before, tag=tag, label=label,
        cell_type=cell_type,
    )
    console.print(f"[green]inserted into {out}[/green]")


@app.command()
def remove_cell(
    name: str,
    index: int | None = typer.Option(None, "--index", "-i", help="0-based cell index"),
    tag: str | None = typer.Option(None, "--tag", "-t", help="remove all cells with this tag"),
    label: str | None = typer.Option(None, "--label", "-l", help="remove cell with this Quarto label"),
) -> None:
    """Remove cells matching the locator. A tag may remove multiple."""
    from . import notebook

    out = notebook.remove_cell(name, index=index, tag=tag, label=label)
    console.print(f"[green]removed from {out}[/green]")


@app.command()
def clear_outputs(
    name: str,
    index: int | None = typer.Option(None, "--index", "-i", help="0-based cell index"),
    tag: str | None = typer.Option(None, "--tag", "-t", help="clear outputs of all cells with this tag"),
    label: str | None = typer.Option(None, "--label", "-l", help="clear outputs of cell with this Quarto label"),
    from_index: int | None = typer.Option(None, "--from", "-f", help="clear outputs of all code cells from this index to the end"),
) -> None:
    """Clear stored outputs of code cells.

    Locator precedence: --from N clears every code cell from index N to the
    end (handy for a trailing section like a problem set); --index / --tag /
    --label clear the matching cells; with no locator, every code cell in the
    notebook is cleared. Markdown cells are skipped.
    """
    from . import notebook

    out = notebook.clear_outputs(
        name, index=index, tag=tag, label=label, from_index=from_index
    )
    console.print(f"[green]cleared outputs in {out}[/green]")


@app.command()
def tag(
    name: str,
    index: int | None = typer.Option(None, "--index", "-i", help="0-based cell index"),
    tag: str | None = typer.Option(None, "--tag", "-t", help="cell tag to match (must be unique)"),
    label: str | None = typer.Option(None, "--label", "-l", help="Quarto `#| label:` to match (must be unique)"),
    add: list[str] = typer.Option([], "--add", "-a", help="tag to add (may be repeated)"),
    remove: list[str] = typer.Option([], "--remove", "-r", help="tag to remove (may be repeated)"),
) -> None:
    """Add and/or remove tags on a single cell.

    Exactly one of --index / --tag / --label is required. Without --add or
    --remove, prints current tags.
    """
    from . import notebook

    out = notebook.tag_cell(
        name, index=index, tag=tag, label=label, add=add or None, remove=remove or None
    )
    if isinstance(out, list):
        if out:
            for t in out:
                print(t)
        else:
            console.print("[yellow](no tags)[/yellow]")
    else:
        console.print(f"[green]tagged {out}[/green]")


@app.command()
def run(
    name: str,
    index: int | None = typer.Option(None, "--index", "-i", help="run only this cell in a fresh kernel"),
    timeout: int = typer.Option(300, "--timeout", help="per-cell timeout in seconds"),
    kernel: str | None = typer.Option(None, "--kernel", "-k", help="kernel name (default: python3)"),
) -> None:
    """Execute a notebook's code cells in-place, writing outputs back.

    Quarto renders inline outputs without re-running; wt run is the explicit
    re-execution path. Single-cell runs (--index) start a fresh kernel, so
    state from other cells does not carry over.
    """
    from . import execute

    result = execute.run_notebook(name, index=index, kernel=kernel, timeout=timeout)
    if result["ran"] == 0 and index is None:
        console.print("[green]no code cells to run[/green]")
    else:
        console.print(
            f"[green]executed {result['ran']} cells ({len(result['errors'])} errors)[/green]"
        )
    for err in result["errors"]:
        evalue = err["evalue"]
        if len(evalue) > 300:
            evalue = f"{evalue[:300]}..."
        console.print(f"[red]cell {err['index']} [{err['ename']}]: {evalue}[/red]")
    if result["errors"]:
        raise typer.Exit(1)


@app.command(name="render")
def render_cmd(
    tier_or_path: str = typer.Argument(..., help="tier (notes|articles) or ipynb path"),
    name: str | None = typer.Argument(None, help="source name (omit if path given)"),
) -> None:
    """Render a source .ipynb to PDF (notes/pdf/ or articles/pdf/) and open it.

    Usage:
      wt render notes test          -> render notes/test.ipynb
      wt render articles test       -> render articles/test.ipynb
      wt render notes/test.ipynb    -> full path
    """
    from . import render

    source = f"{tier_or_path}/{name}.ipynb" if name else tier_or_path
    pdf = render.render_pdf(source)
    console.print(f"[green]rendered {pdf}[/green]")
    _open(pdf)


@app.command(name="resume")
def resume_cmd() -> None:
    """Render assets/resume.yaml -> assets/resume.tex + index.ipynb, then pdflatex -> assets/resume.pdf."""
    from . import resume

    pdf_path, index_path = resume.build_resume()
    console.print(f"[green]resume PDF: {pdf_path}[/green]")
    console.print(f"[green]home page: {index_path}[/green]")


@app.command()
def docs() -> None:
    """Serve the Quarto site (blocking — previews in browser)."""
    from . import render

    render.preview_site()


def _open(path: Path) -> None:
    opener = shutil.which("open") or shutil.which("xdg-open")
    if opener:
        subprocess.run([opener, str(path)], check=False)


def main() -> None:
    """Run the CLI. User-facing errors print as one red line and exit 1.

    Every command raises ValueError/FileNotFoundError/FileExistsError on
    bad input; catching them here keeps the command bodies free of
    try/except noise.
    """
    try:
        app()
    except (FileNotFoundError, FileExistsError, ValueError) as e:
        console.print(f"[red]{e}[/red]")
        # SystemExit, not typer.Exit: outside click's standalone mode,
        # typer.Exit would print a traceback.
        raise SystemExit(1) from e


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
