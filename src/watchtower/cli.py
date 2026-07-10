"""Watchtower CLI — Typer application assembling all subcommands."""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import inspect as inspect_mod
from . import scaffold as scaffold_mod
from . import sync as sync_mod
from . import vault as vault_mod

app = typer.Typer(
    name="wt",
    help="Personal notes, writings, and projects system.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
console = Console()


@app.command()
def sync() -> None:
    """Regenerate markdown mirrors from all notebooks."""
    sync_mod.sync_all()
    console.print("[green]synced.[/green]")


@app.command()
def check() -> None:
    """Verify mirrors are in sync with notebooks. Exits 1 on drift."""
    if not sync_mod.check_drift():
        console.print("[red]mirrors are stale. run `wt sync` to regenerate.[/red]")
        raise typer.Exit(1)
    console.print("[green]ok — mirrors in sync.[/green]")


new_app = typer.Typer(name="new", help="Scaffold new artifacts.", no_args_is_help=True)
app.add_typer(new_app)


@new_app.command("note")
def new_note(name: str) -> None:
    """Create notes/src/<name>.ipynb, jupytext-paired to mirror/<name>.md."""
    path = scaffold_mod.new_note(name)
    console.print(f"[green]created {path}[/green]")


@new_app.command("writing")
def new_writing(slug: str) -> None:
    """Create writings/src/<YYYY-MM-DD>-<slug>.ipynb."""
    path = scaffold_mod.new_writing(slug)
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
    """Grep across mirror *.md files only (never notebooks)."""
    out = inspect_mod.find_mirrors(query)
    if out:
        print(out)
    else:
        console.print(f"[yellow]no mirrors match '{query}'.[/yellow]")


@app.command()
def cat(name: str) -> None:
    """Print a mirror's content by note name. The agent reads this, not .ipynb."""
    try:
        print(inspect_mod.cat_mirror(name), end="")
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def ls(tier: str = typer.Argument(..., help="notes | writings | projects")) -> None:
    """List mirrors in a tier."""
    if tier == "notes":
        items = inspect_mod.list_mirrors(Path("notes/mirror"))
    elif tier == "writings":
        items = inspect_mod.list_mirrors(Path("writings/mirror"))
    elif tier == "projects":
        items = [p["name"] for p in inspect_mod.list_projects()]
    else:
        console.print(f"[red]unknown tier: {tier}. try notes|writings|projects.[/red]")
        raise typer.Exit(2)
    if not items:
        console.print(f"[yellow]no {tier} yet.[/yellow]")
        return
    for i in items:
        print(i)


@app.command()
def render(notebook: str) -> None:
    """Render a notebook to PDF (notes/pdf/) and open it."""
    from . import render as render_mod
    pdf = render_mod.render_pdf(notebook)
    console.print(f"[green]rendered {pdf}[/green]")
    _open(pdf)


@app.command()
def preview() -> None:
    """Serve the writings+portfolio Quarto site."""
    from . import render as render_mod
    render_mod.preview_site()


@app.command()
def publish() -> None:
    """Render the site to _site/."""
    from . import render as render_mod
    render_mod.publish_site()
    console.print("[green]published to _site/.[/green]")


def _open(path: Path) -> None:
    import shutil
    opener = shutil.which("open") or shutil.which("xdg-open")
    if opener:
        import subprocess
        subprocess.run([opener, str(path)], check=False)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())