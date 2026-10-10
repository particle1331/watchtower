"""Watchtower CLI — Typer application assembling all subcommands.

Submodules are imported inside each command body, not at module level:
nbformat (pulled in by notebook/problems/convert/...) costs ~1.1s of
jsonschema import on startup, and most commands never touch a notebook.
Function-level imports keep commands like `wt map` at
~0.1s instead of ~1.5s.
"""


import shlex
import sys
from collections.abc import Mapping

import typer
from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table

from .content_cli import (
    AbstractFlag,
    DescriptionFlag,
    ExpectedRevisionFlag,
    InternalNotesFlag,
    IntroductionFlag,
    PlanFileFlag,
    PlannedContentFlag,
    PlannedLabFlag,
    ScopeNotesFlag,
    StartFlag,
    SummaryFlag,
    TagFlag,
    WhatItContainsFlag,
    install,
)

app = typer.Typer(
    name="wt",
    help="Notebook workflows and core tools.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
console = Console()


new_app = typer.Typer(name="new", help="Plan posts, courses, chapters and portfolio entries. Without a catalog, scaffold notebooks instead.", no_args_is_help=True)
app.add_typer(new_app)


def _require_catalog(flags: Mapping[str, object]) -> None:
    """Plan fields need the content catalog; scaffold files cannot hold them, so refuse rather than drop them."""
    given = [flag for flag, value in flags.items() if value]
    if given:
        raise ValueError(f"{', '.join(given)} need an active catalog (backend/data/catalog.yaml); this workspace only scaffolds files")


@new_app.command("post")
def new_post(
    name: str = typer.Argument(..., help="stable name (letters, digits, hyphens); the ID becomes post/NAME"),
    title: str | None = typer.Option(None, "--title", "-t", help="display title (default: derived from NAME)"),
    summary: SummaryFlag = None,
    tag: TagFlag = None,
    plan_file: PlanFileFlag = None,
    internal_notes: InternalNotesFlag = None,
    start: StartFlag = False,
    expected_revision: ExpectedRevisionFlag = None,
    description: DescriptionFlag = None,
    planned_content: PlannedContentFlag = None,
    visibility: str = typer.Option("private", "--visibility", hidden=True),
) -> None:
    """Plan a post without a notebook; --start also creates its draft notebook.

    Plan file sections (## headings, by label or key, any case): Summary, Outline, Audience, Examples and evidence, References, Internal notes. Text before the first heading is an error. A field may come from a flag or a section, not both.
    """
    from .content_cli import active, create_post

    options = {"--summary": summary, "--description": description, "--internal-notes": internal_notes, "--planned-content": planned_content}
    if active():
        create_post(name, title=title, tags=tag, visibility=visibility, options=options, plan_file=plan_file, start=start, expected_revision=expected_revision)
        return
    _require_catalog({**options, "--tag": tag, "--plan-file": plan_file, "--start": start, "--expected-revision": expected_revision})
    from . import scaffold

    path = scaffold.new_post(name, title=title)
    console.print(f"[green]created {path}[/green]")


@new_app.command("course")
def new_course(
    name: str = typer.Argument(..., help="course folder name (e.g. llm)"),
    title: str = typer.Argument(..., help='display title (e.g. "Large Language Models")'),
    summary: SummaryFlag = None,
    plan_file: PlanFileFlag = None,
    internal_notes: InternalNotesFlag = None,
    start: StartFlag = False,
    expected_revision: ExpectedRevisionFlag = None,
    description: DescriptionFlag = None,
    planned_content: PlannedContentFlag = None,
    planned_lab_and_evidence: PlannedLabFlag = None,
) -> None:
    """Plan a course: its contract and home page. Add chapters with new chapter.

    Plan file sections (## headings, by label or key, any case): Card description, Purpose, Audience and prerequisites, Learning outcomes, Running project, Practice and assessment, References, Internal notes. Chapters are managed in the outline, not in the plan file. Text before the first heading is an error.
    """
    from .content_cli import active, create_course

    options = {"--summary": summary, "--description": description, "--internal-notes": internal_notes, "--planned-content": planned_content, "--planned-lab-and-evidence": planned_lab_and_evidence}
    if active():
        create_course(name, title, options=options, plan_file=plan_file, start=start, expected_revision=expected_revision)
        return
    _require_catalog({**options, "--plan-file": plan_file, "--start": start, "--expected-revision": expected_revision})
    from . import scaffold

    path = scaffold.new_course(name, title=title)
    console.print(f"[green]created {path}[/green]")


@new_app.command("chapter")
def new_chapter(
    course: str = typer.Argument(..., help="course folder name (e.g. mlops)"),
    name: str = typer.Argument(..., help="chapter stem (e.g. 02-data-validation)"),
    title: str | None = typer.Option(None, "--title", "-t", help="display title (default: derived from NAME)"),
    section: str | None = typer.Option(None, "--section", "-s", help="section ID or title (default: last section)"),
    toc_title: str | None = typer.Option(None, "--toc-title", help="short navigation title"),
    summary: SummaryFlag = None,
    plan_file: PlanFileFlag = None,
    internal_notes: InternalNotesFlag = None,
    start: StartFlag = False,
    expected_revision: ExpectedRevisionFlag = None,
    description: DescriptionFlag = None,
    planned_content: PlannedContentFlag = None,
    planned_lab_and_evidence: PlannedLabFlag = None,
) -> None:
    """Plan a chapter in a course section without a notebook; --start also creates it.

    Plan file sections (## headings, by label or key, any case): Course table summary, Outline, Practice and evidence, Internal notes. The course table summary is the one-line row text on the course page.
    """
    from .content_cli import active, create_chapter

    options = {"--summary": summary, "--description": description, "--internal-notes": internal_notes, "--planned-content": planned_content, "--planned-lab-and-evidence": planned_lab_and_evidence}
    if active():
        create_chapter(course, name, title=title, section=section, toc_title=toc_title, options=options, plan_file=plan_file, start=start, expected_revision=expected_revision)
        return
    _require_catalog({**options, "--toc-title": toc_title, "--plan-file": plan_file, "--start": start, "--expected-revision": expected_revision})
    from . import scaffold

    path = scaffold.new_course_chapter(course, name, title=title, section=section)
    console.print(f"[green]created {path}[/green]")


@new_app.command("portfolio")
def new_portfolio(
    name: str = typer.Argument(..., help="stable name (letters, digits, hyphens); the ID becomes portfolio/NAME"),
    title: str | None = typer.Option(None, "--title", help="display title (default: derived from NAME)"),
    summary: SummaryFlag = None,
    tag: TagFlag = None,
    figure_path: str | None = typer.Option(None, "--figure-path", help="featured image path under backend/assets/"),
    figure_caption: str | None = typer.Option(None, "--figure-caption", help="caption shown with the featured image"),
    project_path: str | None = typer.Option(None, "--project-path", help="repository-relative code directory (default: projects/NAME)"),
    plan_file: PlanFileFlag = None,
    internal_notes: InternalNotesFlag = None,
    start: StartFlag = False,
    expected_revision: ExpectedRevisionFlag = None,
    description: DescriptionFlag = None,
    abstract: AbstractFlag = None,
    planned_content: PlannedContentFlag = None,
    planned_lab_and_evidence: PlannedLabFlag = None,
    introduction: IntroductionFlag = None,
    what_it_contains: WhatItContainsFlag = None,
    scope_notes: ScopeNotesFlag = None,
) -> None:
    """Plan a portfolio entry; --start also creates its notebook and project code.

    Plan file sections (## headings, by label or key, any case): Abstract, Problem, What it contains, Intended users, Implementation approach, Success criteria, References, Internal notes. Publishing needs the abstract, a featured figure and its caption; drafts may omit them.
    """
    from .content_cli import active, create_portfolio

    if not active():
        raise ValueError("portfolio plans need an active catalog (backend/data/catalog.yaml); run wt migrate first")
    options = {"--summary": summary, "--description": description, "--abstract": abstract, "--internal-notes": internal_notes, "--planned-content": planned_content, "--planned-lab-and-evidence": planned_lab_and_evidence, "--introduction": introduction, "--what-it-contains": what_it_contains, "--scope-notes": scope_notes}
    create_portfolio(name, title=title, tags=tag, figure_path=figure_path, figure_caption=figure_caption, project_path=project_path, options=options, plan_file=plan_file, start=start, expected_revision=expected_revision)


@new_app.command("section")
def new_section(
    course: str = typer.Argument(..., help="course folder name (e.g. mlops)"),
    name: str = typer.Argument(..., help="section name (e.g. 'Local Stack')"),
) -> None:
    """Add a section header to a course's authored outline."""
    from .content_cli import active, emit, slug
    if active():
        from .services.content import ContentService
        service = ContentService()
        key = f"course/{course.removeprefix('course/')}"
        contract = service.read_data(key)
        section_id = slug(name.lower().replace(" ", "-"))
        contract["data"]["toc"].append({"id": section_id, "title": name, "chapters": []})
        emit(service.update_data(key, contract["data"], contract["revision"]))
        return
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


@vault_app.command("rm")
def vault_rm(key: str) -> None:
    """Delete a secret from the OS keyring."""
    from . import vault

    if not vault.delete_secret(key):
        console.print(f"[red]{key} not set.[/red]")
        raise typer.Exit(1)
    console.print(f"[green]deleted {key}.[/green]")


@vault_app.command("ls")
def vault_ls() -> None:
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
def map_cmd(archive: bool = typer.Option(False, "--archive", help="show archived source paths")) -> None:
    """Print registered active knowledge as JSON, or the archive inventory."""
    from . import inspect

    print(inspect.repo_map_json(archive=archive))


@app.command(name="kernels")
def kernels_cmd() -> None:
    """List Jupyter kernels available to ``wt run --kernel``."""
    from . import kernels

    rows = kernels.available_kernel_rows()
    if not rows:
        console.print("[yellow]no Jupyter kernels installed[/yellow]")
        return

    table = Table("name", "language", "display name")
    for name, language, display_name in rows:
        table.add_row(name, language, display_name)
    console.print(table)


@app.command()
def find(query: str, archive: bool = typer.Option(False, "--archive", help="search archived sources")) -> None:
    """Search registered active sources, or archived sources explicitly."""
    from . import inspect

    out = inspect.find_in_src(query, archive=archive)
    if out:
        print(out)
    else:
        console.print(f"[yellow]no sources match '{query}'.[/yellow]")


@app.command(name="context")
def context_cmd(name: str) -> None:
    """Show an artifact's catalog record, course contract, and reading paths."""
    from . import knowledge

    print(knowledge.context_json(name))


@app.command(name="validate")
def validate_cmd() -> None:
    """Check catalog references, course contracts, and unregistered active files."""
    from . import knowledge

    errors = knowledge.validate()
    if errors:
        for error in errors:
            console.print(f"[red]{error}[/red]")
        raise typer.Exit(1)
    console.print("[green]knowledge catalog valid[/green]")


@app.command(name="render-context")
def render_context_cmd() -> None:
    """Generate course-home Markdown includes from active course YAML files."""
    from . import knowledge

    for path in knowledge.render_course_includes():
        print(path)


@app.command(name="sync-site")
def sync_site_cmd() -> None:
    """Sync Quarto render paths and navigation from published catalog records."""
    from . import knowledge

    knowledge.sync_site()
    console.print("[green]site navigation synchronized[/green]")


@app.command(name="publish")
def publish_cmd(name: str = typer.Argument(..., help="artifact ID/path"), expected_revision: str | None = typer.Option(None, "--expected-revision")) -> None:
    """Publish authored content with public visibility for the next deployment."""
    from .content_cli import active, emit
    if active():
        from .services.content import ContentService
        emit(ContentService().publish(name, expected_revision))
        return
    from . import knowledge

    try:
        artifact = knowledge.publish_artifact(name)
    except ValueError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    console.print(f"[green]published {artifact['id']}[/green]")


@app.command(name="register")
def register_cmd(
    kind: str = typer.Argument(..., help="post | course | chapter | portfolio | project"),
    path: str = typer.Argument(..., help="existing relative source path"),
    title: str = typer.Argument(..., help="display title"),
    parent: str | None = typer.Option(None, "--parent", help="registered course ID for a chapter"),
    visibility: str = typer.Option("public", "--visibility", help="public | private"),
    lifecycle: str = typer.Option("draft", "--lifecycle", help="planned | draft | published"),
    summary: str | None = typer.Option(None, "--summary", help="required description for a portfolio entry"),
    relation: list[str] | None = typer.Option(None, "--relation", help="related catalog ID; repeat for multiple links"),
) -> None:
    """Register existing work, deriving its ID from the source path and chapter parent."""
    from pathlib import Path

    from . import knowledge

    source = Path(path)
    name = source.name if kind in {"course", "project"} else source.stem
    if kind == "chapter":
        if not parent:
            raise typer.BadParameter("chapter registration requires --parent", param_hint="--parent")
        artifact_id = f"{parent}/{name}"
    else:
        artifact_id = f"{kind}/{name}"
    knowledge.add_artifact(
        artifact_id, kind, source, title,
        parent=parent, visibility=visibility, lifecycle=lifecycle,
        summary=summary, relations=relation,
    )
    console.print(f"[green]registered {artifact_id}[/green]")


@app.command()
def count(name: str) -> None:
    """Print the number of cells in a notebook."""
    from . import notebook

    n = notebook.count_cells(name)
    print(f"{n} cells")


@app.command()
def cat(
    name: str,
    index: str | None = typer.Option(None, "--index", "-i", help="0-based cell index, or N:M range (Python-style slice; :M and N: also ok)"),
    tag: str | None = typer.Option(None, "--tag", "-t", help="show cells with this tag"),
    label: str | None = typer.Option(None, "--label", "-l", help="show cells with this #| label: pragma"),
    offset: int = typer.Option(0, "--offset", "-o", help="char offset into the cell source (use with --limit)"),
    limit: int | None = typer.Option(None, "--limit", help="max chars per cell source (default: 4096; 0 = unlimited)"),
    with_outputs: bool = typer.Option(False, "--with-outputs", help="also show each code cell's outputs"),
    with_revision: bool = typer.Option(False, "--with-revision", help="include the notebook token for --expected-revision writes"),
    out_offset: int = typer.Option(0, "--out-offset", help="char offset into each output's text body"),
    out_limit: int | None = typer.Option(None, "--out-limit", help="max chars per output body"),
    context: int = typer.Option(0, "--context", "-C", help="include N neighboring cells in this notebook (not course context)"),
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
            context=context, with_revision=with_revision,
        ),
        end="",
    )


@app.command(name="output")
def output_cmd(
    name: str,
    index: int = typer.Option(..., "--index", "-i", help="0-based code-cell index"),
    output_index: int | None = typer.Option(
        None, "--output", "-o", help="only show this output index (default: all)"
    ),
    save_dir: str | None = typer.Option(
        None, "--save-dir", help='directory for extracted image files (default: ROOT_PATH / ".tmp")'
    ),
) -> None:
    """Inspect stored outputs from one cell and save images for visual review.

    Text and error outputs are printed. Image payloads are decoded and written
    to ``ROOT_PATH / ".tmp"`` by default; the resulting paths are printed so an agent
    or image-capable tool can inspect them.
    """
    from . import outputs

    values = outputs.get_cell_outputs(name, index)
    if output_index is not None:
        if output_index < 0 or output_index >= len(values):
            raise ValueError(
                f"cell {index} has {len(values)} outputs; index {output_index} is out of bounds"
            )
        values = [values[output_index]]
    if not values:
        console.print(f"[yellow]cell {index} has no stored outputs[/yellow]")
        return
    for value in values:
        print(f"> cell {value.cell_index} output {value.output_index} [{value.output_type}]")
        if value.text:
            print(value.text)
        for image_path in outputs.save_output_images(name, value, directory=save_dir):
            print(f"image: {image_path}")


@app.command(name="diff")
def diff_cmd(
    name: str,
    base: str = typer.Option("HEAD", "--base", "-b", help="git ref to diff against (default: HEAD)"),
    base_source: str | None = typer.Option(None, "--base-source", help="original repository path when reviewing a moved notebook"),
) -> None:
    """Show a notebook's changes as a markdown diff vs a git ref.

    Both sides are rendered like `wt cat` (JSON-stripped, no outputs;
    solution cells decoded), so the diff shows content changes instead of
    `.ipynb` JSON noise. Prints nothing extra when unchanged.
    """
    from . import notebook

    out = notebook.diff_notebook(name, base=base, base_source=base_source)
    if out is None:
        console.print("[green]no changes[/green]")
    else:
        _print_diff(out)


def _print_diff(out: str) -> None:
    """Print a diff with terminal highlighting when the output supports it."""
    if console.is_terminal and console.color_system and not console.no_color:
        console.print(Syntax(out, "diff", theme="ansi_dark"), end="")
    else:
        print(out)


@app.command()
def ls(
    tier: str = typer.Argument(..., help="posts | courses | portfolio | projects"),
    archive: bool = typer.Option(False, "--archive", help="list the archived tier"),
) -> None:
    """List registered active artifacts or archived source paths."""
    from . import inspect

    if archive:
        inventory = inspect.archive_map()
        if tier not in {"posts", "courses", "portfolio", "projects"}:
            raise ValueError(f"unknown tier: {tier}")
        items = inventory[tier]
    else:
        items = inspect.list_tier(tier)
    if not items:
        console.print(f"[yellow]no {tier} yet.[/yellow]")
        return
    for i in items:
        print(i)


@app.command(name="import")
def import_cmd(
    ipynb: str = typer.Argument(..., help="path to source .ipynb to import"),
    tier: str = typer.Argument(..., help="posts | courses"),
    name: str | None = typer.Argument(
        None,
        help=(
            "for posts: destination name without .ipynb "
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

    For posts: writes to nb/posts/<name>.ipynb.
    For courses: writes to nb/courses/<course>/<chapter>.ipynb and registers
    in the course's authored sidebar outline.
    """
    from .content_cli import active, emit
    if active():
        from pathlib import Path

        from .services.content import ContentService
        source = Path(ipynb)
        if tier == "courses":
            if name is None:
                raise ValueError("course imports require a course slug")
            emit(ContentService().import_notebook(source, "chapter", chapter or source.stem, course=name, section=section))
        elif tier in {"posts", "personal"}:
            emit(ContentService().import_notebook(source, "post" if tier == "posts" else "personal", name or source.stem))
        else:
            raise ValueError("tier must be posts, courses, or personal")
        return
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
    expected_revision: str | None = typer.Option(None, "--expected-revision", help="Notebook token from cat --with-revision."),
) -> None:
    """Replace a notebook cell's source. Preserves outputs/metadata.

    Exactly one of --index / --tag / --label is required. Source comes from
    --content (for one-liners) or stdin (for multi-line). Errors if the
    locator matches zero or multiple cells.
    """
    from . import notebook

    src = content if content is not None else sys.stdin.read()
    out = notebook.edit_cell(name, src, index=index, tag=tag, label=label, expected_revision=expected_revision)
    console.print(f"[green]updated {out}[/green]")


@app.command()
def append_cell(
    name: str,
    cell_type: str = typer.Option("md", "--type", "-t", help="md | code"),
    content: str | None = typer.Option(None, "--content", "-c", help="cell source (if omitted, read from stdin)"),
    expected_revision: str | None = typer.Option(None, "--expected-revision", help="Notebook token from cat --with-revision."),
) -> None:
    """Append a new cell to the end of the notebook."""
    from . import notebook

    src = content if content is not None else sys.stdin.read()
    out = notebook.append_cell(name, src, cell_type=cell_type, expected_revision=expected_revision)
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
    expected_revision: str | None = typer.Option(None, "--expected-revision", help="Notebook token from cat --with-revision."),
) -> None:
    """Insert a new cell above/below a located cell.

    Pass exactly one of --after / --before / --tag / --label. --tag and
    --label insert *below* the matched cell. Source from --content or stdin.
    """
    from . import notebook

    src = content if content is not None else sys.stdin.read()
    out = notebook.insert_cell(
        name, src, after=after, before=before, tag=tag, label=label,
        cell_type=cell_type, expected_revision=expected_revision,
    )
    console.print(f"[green]inserted into {out}[/green]")


@app.command()
def remove_cell(
    name: str,
    index: int | None = typer.Option(None, "--index", "-i", help="0-based cell index"),
    tag: str | None = typer.Option(None, "--tag", "-t", help="remove all cells with this tag"),
    label: str | None = typer.Option(None, "--label", "-l", help="remove cell with this Quarto label"),
    expected_revision: str | None = typer.Option(None, "--expected-revision", help="Notebook token from cat --with-revision."),
) -> None:
    """Remove cells matching the locator. A tag may remove multiple."""
    from . import notebook

    out = notebook.remove_cell(name, index=index, tag=tag, label=label, expected_revision=expected_revision)
    console.print(f"[green]removed from {out}[/green]")


@app.command()
def clear_outputs(
    name: str,
    index: int | None = typer.Option(None, "--index", "-i", help="0-based cell index"),
    tag: str | None = typer.Option(None, "--tag", "-t", help="clear outputs of all cells with this tag"),
    label: str | None = typer.Option(None, "--label", "-l", help="clear outputs of cell with this Quarto label"),
    from_index: int | None = typer.Option(None, "--from", "-f", help="clear outputs of all code cells from this index to the end"),
    expected_revision: str | None = typer.Option(None, "--expected-revision", help="Notebook token from cat --with-revision."),
) -> None:
    """Clear stored outputs of code cells.

    Locator precedence: --from N clears every code cell from index N to the
    end (handy for a trailing section like a problem set); --index / --tag /
    --label clear the matching cells; with no locator, every code cell in the
    notebook is cleared. Markdown cells are skipped.
    """
    from . import notebook

    out = notebook.clear_outputs(
        name, index=index, tag=tag, label=label, from_index=from_index, expected_revision=expected_revision
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
    expected_revision: str | None = typer.Option(None, "--expected-revision", help="Notebook token from cat --with-revision."),
) -> None:
    """Add and/or remove tags on a single cell.

    Exactly one of --index / --tag / --label is required. Without --add or
    --remove, prints current tags.
    """
    from . import notebook

    out = notebook.tag_cell(
        name, index=index, tag=tag, label=label, add=add or None, remove=remove or None, expected_revision=expected_revision
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
    index: int | None = typer.Option(
        None,
        "--index",
        "-i",
        help="run through this cell in a fresh kernel (prior state available)",
    ),
    timeout: int = typer.Option(300, "--timeout", help="per-cell timeout in seconds"),
    kernel: str | None = typer.Option(
        None,
        "--kernel",
        "-k",
        help="kernel name (run `wt kernels`; default: notebook kernelspec, then python3)",
    ),
    expected_revision: str | None = typer.Option(None, "--expected-revision", help="Notebook token from cat --with-revision."),
) -> None:
    """Execute a notebook's code cells in-place, writing outputs back.

    Quarto renders inline outputs without re-running; wt run is the explicit
    re-execution path. Indexed runs (--index) start a fresh kernel and execute
    the notebook prefix through the selected cell, so prior state is available.
    Only the selected cell's outputs are written back.
    """
    from . import execute

    try:
        result = execute.run_notebook(name, index=index, kernel=kernel, timeout=timeout, expected_revision=expected_revision)
    except ValueError as e:
        if kernel is not None and str(e).startswith("kernel '"):
            from . import kernels

            available = kernels.available_kernel_names()
            hint = (
                f" Available kernels: {', '.join(available)}."
                if available
                else " No Jupyter kernels are installed."
            )
            raise ValueError(f"{e}{hint} Run `wt kernels` to list them.") from e
        raise
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


def main() -> None:
    """Run the CLI. User-facing errors print as one red line and exit 1.

    Every command raises ValueError/FileNotFoundError/FileExistsError on
    bad input; catching them here keeps the command bodies free of
    try/except noise.
    """
    try:
        app()
    except (FileNotFoundError, FileExistsError, ValueError) as e:
        from .services.workspace import ServiceError
        if isinstance(e, ServiceError):
            from .content_cli import emit
            emit({"error": e.as_dict(), "status": e.status})
            raise SystemExit(2 if e.status in {409, 412, 428} else 1) from e
        console.print(f"[red]{e}[/red]")
        # SystemExit, not typer.Exit: outside click's standalone mode,
        # typer.Exit would print a traceback.
        raise SystemExit(1) from e


install(app)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
