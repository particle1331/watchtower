"""Agent access to entity and card context attachments."""
from pathlib import Path

import typer

from watchtower.services.attachments import (
    MAX_ATTACHMENT_BYTES,
    AttachmentService,
    AttachmentUpload,
)
from watchtower.services.workspace import ServiceError


def install(app: typer.Typer) -> None:
    from watchtower.content_cli import emit
    attachments = typer.Typer(help="Manage private context attachments by artifact ID or card#N.", no_args_is_help=True)
    app.add_typer(attachments, name="attachments")

    @attachments.command("ls")
    def list_files(owner: str | None = typer.Argument(None)) -> None:
        """List paths, metadata, owners and the workspace revision."""
        emit(AttachmentService().read(owner))

    @attachments.command("add")
    def add(owner: str, file: list[Path] = typer.Option(..., "--file", exists=True, dir_okay=False), expected_revision: str | None = typer.Option(None, "--expected-revision")) -> None:
        """Attach files; repeated uploads of identical bytes share storage."""
        uploads = []
        for path in file:
            with path.open("rb") as stream:
                value = stream.read(MAX_ATTACHMENT_BYTES + 1)
            uploads.append(AttachmentUpload(path.name, value))
        emit(AttachmentService().change(owner, uploads=uploads, expected_revision=expected_revision))

    @attachments.command("link")
    def link(owner: str, attachment_id: str, expected_revision: str | None = typer.Option(None, "--expected-revision")) -> None:
        """Reuse an existing attachment on another artifact or card."""
        emit(AttachmentService().change(owner, link=attachment_id, expected_revision=expected_revision))

    @attachments.command("rm")
    def remove(owner: str, attachment_id: str, expected_revision: str | None = typer.Option(None, "--expected-revision")) -> None:
        """Detach a file; archive it when the final reference is removed."""
        if not attachment_id:
            raise ServiceError("Provide an attachment ID.")
        emit(AttachmentService().change(owner, remove=[attachment_id], expected_revision=expected_revision))
