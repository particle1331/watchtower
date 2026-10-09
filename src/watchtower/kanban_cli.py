"""JSON CLI for the same saved Kanban board used by CMS and HTTP."""
from typing import Any

import typer

from watchtower.services.kanban import KanbanService


def install(app: typer.Typer) -> None:
    from watchtower.content_cli import emit

    board = typer.Typer(help="Track tasks and next steps as cards linked to validated artifact IDs.", no_args_is_help=True)
    app.add_typer(board, name="kanban")

    @board.command("ls")
    def list_cards(column: str | None = None, query: str = "") -> None:
        """List cards with frontend and VS Code links, plus the current revision."""
        emit(KanbanService().read(column=column, query=query))

    @board.command("add")
    def add(title: str = typer.Option(..., "--title"), description: str = "", column: str = "todo", link: list[str] | None = typer.Option(None, "--link"), expected_revision: str | None = typer.Option(None, "--expected-revision")) -> None:
        """Add a task or next step with an automatic ID and card#N reference; repeat --link for each artifact."""
        data: dict[str, Any] = {"title": title, "description": description, "column": column, "artifact_ids": link or []}
        emit(KanbanService().create(data, expected_revision))

    @board.command("show")
    def show(card_id: str) -> None:
        """Read a card with current linked plans, internal notes and attachments."""
        emit(KanbanService().context(card_id))

    @board.command("update")
    def update(card_id: str, title: str | None = None, description: str | None = None, column: str | None = None, link: list[str] | None = typer.Option(None, "--link"), clear_links: bool = typer.Option(False, "--clear-links"), expected_revision: str | None = typer.Option(None, "--expected-revision")) -> None:
        """Edit a card; --link replaces its links, --clear-links removes all links."""
        if link and clear_links:
            from watchtower.services.workspace import ServiceError
            raise ServiceError("choose --link or --clear-links")
        patch: dict[str, Any] = {key: value for key, value in {"title": title, "description": description, "column": column}.items() if value is not None}
        if link is not None or clear_links:
            patch["artifact_ids"] = link or []
        emit(KanbanService().update(card_id, patch, expected_revision))

    @board.command("move")
    def move(card_id: str, column: str, expected_revision: str | None = typer.Option(None, "--expected-revision")) -> None:
        """Move to todo, in-progress, review or done."""
        emit(KanbanService().update(card_id, {"column": column}, expected_revision))

    @board.command("rm")
    def remove(card_id: str, expected_revision: str | None = typer.Option(None, "--expected-revision")) -> None:
        """Remove a card without modifying linked artifacts."""
        emit(KanbanService().remove(card_id, expected_revision))
