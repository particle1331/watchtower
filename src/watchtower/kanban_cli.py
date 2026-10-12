"""JSON CLI for the same saved Kanban board used by CMS and HTTP."""
import json
from pathlib import Path
from typing import Any

import typer

from watchtower.services.kanban import KanbanService
from watchtower.services.workspace import ServiceError


def read_todos(path: Path | None) -> list[dict[str, Any]] | None:
    if path is None:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ServiceError(f"Cannot read to-dos JSON from {path}: {error}") from error
    if not isinstance(value, list):
        raise ServiceError("Kanban --todos-file must contain a JSON array of {text, done} items")
    return value


def install(app: typer.Typer) -> None:
    from watchtower.content_cli import emit

    board = typer.Typer(help="Track tasks and next steps as cards linked to validated artifact IDs.", no_args_is_help=True)
    app.add_typer(board, name="kanban")

    @board.command("ls")
    def list_cards(column: str | None = None, query: str = "") -> None:
        """List cards with frontend and VS Code links, plus the current revision."""
        emit(KanbanService().read(column=column, query=query))

    @board.command("add")
    def add(title: str = typer.Option(..., "--title"), description: str = "", notes: str = typer.Option("", "--notes", help="Task-specific Markdown notes."), todos_file: Path | None = typer.Option(None, "--todos-file", help="JSON array of {text, done} items; replaces the checklist."), column: str = "todo", link: list[str] | None = typer.Option(None, "--link"), expected_revision: str | None = typer.Option(None, "--expected-revision")) -> None:
        """Add a task card with optional execution notes and a checklist; repeat --link for each artifact."""
        data: dict[str, Any] = {"title": title, "description": description, "notes": notes, "column": column, "artifact_ids": link or []}
        if (todos := read_todos(todos_file)) is not None:
            data["todos"] = todos
        emit(KanbanService().create(data, expected_revision))

    @board.command("show")
    def show(card_id: str) -> None:
        """Read a card's task notes/checklist and current linked plans and attachments."""
        emit(KanbanService().context(card_id))

    @board.command("update")
    def update(card_id: str, title: str | None = None, description: str | None = None, notes: str | None = typer.Option(None, "--notes", help="Replace the card's task-specific Markdown notes."), clear_notes: bool = typer.Option(False, "--clear-notes", help="Clear the card's task-specific notes."), todos_file: Path | None = typer.Option(None, "--todos-file", help="JSON array of {text, done} items; replaces the checklist."), column: str | None = None, link: list[str] | None = typer.Option(None, "--link"), clear_links: bool = typer.Option(False, "--clear-links"), expected_revision: str | None = typer.Option(None, "--expected-revision")) -> None:
        """Edit card fields and task checklist; links are replaced when supplied."""
        if link and clear_links:
            raise ServiceError("choose --link or --clear-links")
        if notes is not None and clear_notes:
            raise ServiceError("choose --notes or --clear-notes")
        patch: dict[str, Any] = {key: value for key, value in {"title": title, "description": description, "column": column}.items() if value is not None}
        if notes is not None or clear_notes:
            patch["notes"] = notes or ""
        if (todos := read_todos(todos_file)) is not None:
            patch["todos"] = todos
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
