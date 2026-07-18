"""Watchtower CLI — Typer application assembling all subcommands."""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import convert as convert_mod
from . import inspect as inspect_mod
from . import render as render_mod
from . import resume as resume_mod
from . import scaffold as scaffold_mod
from . import vault as vault_mod

app = typer.Typer(
    name="wt",
    help="Personal notes, essays, and projects system.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
console = Console()


new_app = typer.Typer(name="new", help="Scaffold new artifacts.", no_args_is_help=True)
app.add_typer(new_app)


@new_app.command("note")
def new_note(name: str) -> None:
    """Create notes/<name>.qmd with a minimal front-matter stub."""
    path = scaffold_mod.new_note(name)
    console.print(f"[green]created {path}[/green]")


@new_app.command("essay")
def new_essay(slug: str) -> None:
    """Create essays/<YYYY-MM-DD>-<slug>.qmd."""
    path = scaffold_mod.new_essay(slug)
    console.print(f"[green]created {path}[/green]")


@new_app.command("project")
def new_project(name: str) -> None:
    """uv init projects/<name> and wire it into the workspace."""
    path = scaffold_mod.new_project(name)
    console.print(f"[green]created {path}[/green]")


vault_app = typer.Typer(name="vault", help="Manage secrets in OS keyring.", no_args_is_help=True)
app.add_typer(vault_app)


@vault_app.command("set")
def vault_set(key: str, value: str) -> None:
    """Store a secret in the OS keyring."""
    vault_mod.set_secret(key, value)
    console.print(f"[green]stored {key}.[/green]")


@vault_app.command("get")
def vault_get(key: str) -> None:
    """Retrieve a secret value."""
    val = vault_mod.get_secret(key)
    if val is None:
        console.print(f"[red]{key} not set.[/red]")
        raise typer.Exit(1)
    console.print(val)


@vault_app.command("list")
def vault_list() -> None:
    """List stored secret keys (no values)."""
    keys = vault_mod.list_keys()
    if not keys:
        console.print("[yellow]no secrets stored.[/yellow]")
        return
    t = Table("key")
    for k in keys:
        t.add_row(k)
    console.print(t)


@vault_app.command("env")
def vault_env() -> None:
    """Emit export lines for all stored secrets. Usage: eval $(wt vault env)."""
    for k, v in vault_mod.all_secrets().items():
        print(f"export {k}={shlex.quote(v)}")


@app.command(name="map")
def map_cmd() -> None:
    """Print repo structure as JSON — agent navigation context."""
    print(inspect_mod.repo_map_json())


@app.command()
def find(query: str) -> None:
    """Grep across .qmd source files only."""
    out = inspect_mod.find_in_src(query)
    if out:
        print(out)
    else:
        console.print(f"[yellow]no sources match '{query}'.[/yellow]")


@app.command()
def cat(name: str) -> None:
    """Print a .qmd source file by stem name."""
    try:
        print(inspect_mod.cat_qmd(name), end="")
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def ls(tier: str = typer.Argument(..., help="notes | essays | learning | projects")) -> None:
    """List source .qmd files in a tier."""
    if tier == "notes":
        items = inspect_mod.list_qmd(Path("notes"))
    elif tier == "essays":
        items = inspect_mod.list_qmd(Path("essays"))
    elif tier == "learning":
        items = inspect_mod.list_qmd(Path("learning"))
    elif tier == "projects":
        items = [p["name"] for p in inspect_mod.list_projects()]
    else:
        console.print(f"[red]unknown tier: {tier}. try notes|essays|learning|projects.[/red]")
        raise typer.Exit(2)
    if not items:
        console.print(f"[yellow]no {tier} yet.[/yellow]")
        return
    for i in items:
        print(i)


@app.command()
def convert(
    ipynb: str = typer.Argument(..., help="path to .ipynb file to convert"),
    dest: str | None = typer.Argument(None, help="destination .qmd path (default: alongside source)"),
) -> None:
    """One-time convert a legacy .ipynb notebook to .qmd (jupytext)."""
    try:
        out = convert_mod.convert_ipynb_to_qmd(ipynb, dest)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from e
    console.print(f"[green]converted -> {out}[/green]")


@app.command()
def render(
    tier_or_path: str = typer.Argument(..., help="tier (notes|essays) or qmd path"),
    name: str | None = typer.Argument(None, help="source name (omit if path given)"),
) -> None:
    """Render a source .qmd to PDF (notes/pdf/) and open it.

    Usage:
      wt render notes test          -> render notes/test.qmd
      wt render essays test         -> render essays/test.qmd
      wt render notes/test.qmd      -> full path
    """
    source = f"{tier_or_path}/{name}.qmd" if name else tier_or_path
    pdf = render_mod.render_pdf(source)
    console.print(f"[green]rendered {pdf}[/green]")
    _open(pdf)


@app.command()
def resume() -> None:
    """Compile assets/resume.tex -> assets/resume.pdf (moderncv)."""
    try:
        pdf = resume_mod.build_resume()
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from e
    console.print(f"[green]resume PDF: {pdf}[/green]")


@app.command()
def docs() -> None:
    """Serve the Quarto site (blocking — previews in browser)."""
    render_mod.preview_site()


def _open(path: Path) -> None:
    import shutil
    opener = shutil.which("open") or shutil.which("xdg-open")
    if opener:
        import subprocess
        subprocess.run([opener, str(path)], check=False)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())